"""Resumable P0 pipeline. Discovery is automatic; legal review is an explicit gate."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from insurance_audit.corpus.extract import SUPPORTED, extract
from insurance_audit.corpus.ingest import parse_units, sha256, snapshot_manifest, write_jsonl
from insurance_audit.corpus.review import apply_review, publish_snapshot, semantic_digest
from insurance_audit.corpus.validate import validate_corpus

REGISTRY = "data/extracted/extraction-registry.json"
FILES = (
    "documents.jsonl",
    "articles.jsonl",
    "chunks.jsonl",
    "rule_cards.jsonl",
    "article-review-ledger.jsonl",
)


def now():
    return datetime.now(UTC).isoformat()


def read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".pending")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


@contextmanager
def lock(root: Path, name="pipeline.lock"):
    """OS lock is released even on crash; an abandoned PID file never blocks restart."""
    path = root / "data/runtime" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def initial_state(root):
    manifests = [read(p) for p in (root / "data/corpus").glob("*/manifest.json")]
    published = [m for m in manifests if m.get("publication_status") == "published"]
    base = max(published, key=lambda m: m.get("published_at_utc", ""), default={})
    return {
        "schema_version": 1,
        "base_ruleset": base.get("ruleset_id"),
        "observations": {},
        "versions": {},
        "candidates": {},
        "last_run": None,
    }


def build_proposal(root, state, versions):
    """Copy the published base plus new files into an isolated unreviewed candidate."""
    seed = json.dumps([state["base_ruleset"], sorted(v["source_sha256"] for v in versions)])
    ruleset = "candidate-" + hashlib.sha256(seed.encode()).hexdigest()[:20]
    output = root / "data/corpus" / ruleset
    if (output / "manifest.json").exists():
        state["candidates"].setdefault(
            ruleset,
            {"status": "needs_review", "base_ruleset": state["base_ruleset"], "created_at": now()},
        )
        return ruleset
    rows = {name: [] for name in FILES}
    base = state["base_ruleset"]
    if base:
        if not validate_corpus(root, base)["release_ready"]:
            raise ValueError("Published base failed integrity validation")
        baseline = root / "data/corpus" / base
        for name in FILES:
            rows[name] = [
                json.loads(line)
                for line in (baseline / name).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        for doc in rows["documents.jsonl"]:
            for field in ("snapshot_source_path", "snapshot_extraction_path"):
                original = root / doc[field]
                target = output / original.parent.name / (doc["document_id"] + original.suffix)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
                doc[field] = target.relative_to(root).as_posix()
    output.mkdir(parents=True, exist_ok=True)
    for version in versions:
        stage = root / version["artifact_dir"]
        doc = read(stage / "document.json")
        rows["documents.jsonl"].append(doc)
        articles = [
            json.loads(line)
            for line in (stage / "articles.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        rows["articles.jsonl"].extend(articles)
        rows["chunks.jsonl"].extend(
            {
                "chunk_id": a["article_id"],
                "article_id": a["article_id"],
                "document_id": a["document_id"],
                "text": a["original_text"],
                "chapter": a["chapter"],
            }
            for a in articles
        )
        rows["article-review-ledger.jsonl"].extend(
            {
                "article_id": a["article_id"],
                "rule_ids": [],
                "classification_status": "pending_review",
                "checkability": None,
                "exclusion_reason": None,
                "verified": False,
            }
            for a in articles
        )
    for name, records in rows.items():
        for row in records:
            if name in {"documents.jsonl", "rule_cards.jsonl", "article-review-ledger.jsonl"}:
                row["ruleset_id"] = ruleset
        write_jsonl(output / name, records)
    snapshot_manifest(root, output, ruleset)
    save(
        output / "review-template.json",
        {
            "ruleset_id": ruleset,
            "reviewer": {"type": None, "id": None, "is_legal_expert": False},
            "method": "REPLACE after checking local text, effective status, mappings and conflicts",
            "base_ruleset": base,
            "documents": {
                d["document_id"]: {
                    "source_sha256": d["source_sha256"],
                    "extraction_sha256": d["extraction_sha256"],
                }
                for d in rows["documents.jsonl"]
            },
            "articles": {
                a["article_id"]: {
                    "text_sha256": a["text_sha256"],
                    "scope": next(
                        e
                        for e in rows["article-review-ledger.jsonl"]
                        if e["article_id"] == a["article_id"]
                    ),
                }
                for a in rows["articles.jsonl"]
            },
            "rules": {
                c["rule_id"]: {"digest": semantic_digest(c)} for c in rows["rule_cards.jsonl"]
            },
        },
    )
    save(
        output / "pipeline-context.json",
        {
            "base_ruleset": base,
            "new_sources": [v["document_id"] for v in versions],
            "required_review": [
                "local text and source version",
                "effective date and scope",
                "replacement/conflicts with base documents",
                "rules and exceptions",
                "full ledger",
            ],
            "publication_approval": "After full review and strict validation, write review-approval.json with approved=true, ruleset_id and manifest_sha256",
        },
    )
    state["candidates"][ruleset] = {
        "status": "needs_review",
        "base_ruleset": base,
        "created_at": now(),
    }
    return ruleset


def process_source(root, path, digest):
    directory = root / "data/pipeline/sources" / digest
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / ("source" + path.suffix.lower())
    shutil.copyfile(path, snapshot)
    if sha256(snapshot) != digest or sha256(path) != digest:
        raise ValueError("Source changed during snapshot copy; will retry the new version")
    units, tool = extract(snapshot, directory)
    extraction = directory / "extraction.json"
    save(extraction, units)
    rows = parse_units(units, pdf=path.suffix.lower() == ".pdf")
    did = "local_" + digest[:24]
    articles = []
    for number, row in enumerate(rows, 1):
        text = "\n".join(row["parts"]).strip()
        if not text:
            raise ValueError("Empty article body")
        articles.append(
            {
                "article_id": f"{did}::art_{number:03d}",
                "document_id": did,
                "article_no": number,
                "article_label": row["label"],
                "chapter": row["chapter"],
                "original_text": text,
                "normalized_text": " ".join(text.split()),
                "source_locator": row["locator"],
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "verified": False,
            }
        )
    document = {
        "document_id": did,
        "title": path.stem,
        "source_path": path.relative_to(root).as_posix(),
        "source_sha256": digest,
        "document_status": "unknown",
        "source_type": "unknown",
        "published_on": None,
        "effective_on": None,
        "official_source_url": None,
        "ruleset_id": None,
        "extraction_path": extraction.relative_to(root).as_posix(),
        "extraction_sha256": sha256(extraction),
        "extraction_method": tool["tool"],
        "extraction_version": tool["tool_version"],
        "snapshot_source_path": snapshot.relative_to(root).as_posix(),
        "snapshot_extraction_path": extraction.relative_to(root).as_posix(),
        "legal_text_verified": False,
        "valid_from": None,
        "valid_to": None,
    }
    save(directory / "document.json", document)
    write_jsonl(directory / "articles.jsonl", articles)
    return {
        "document_id": did,
        "source_path": document["source_path"],
        "source_sha256": digest,
        "artifact_dir": directory.relative_to(root).as_posix(),
        "extraction_sha256": sha256(extraction),
        "tool": tool,
        "article_count": len(articles),
        "status": "extracted",
        "processed_at": now(),
    }


def resume_candidates(root, state):
    for ruleset, entry in state["candidates"].items():
        if entry["status"] == "published":
            continue
        directory = root / "data/corpus" / ruleset
        approval = read(directory / "review-approval.json", {})
        if not approval.get("approved"):
            continue
        try:
            manifest = read(directory / "manifest.json")
            if manifest.get("publication_status") != "published":
                if approval.get("ruleset_id") != ruleset or approval.get(
                    "manifest_sha256"
                ) != sha256(directory / "manifest.json"):
                    raise ValueError("Review approval does not match current manifest")
                if entry["base_ruleset"] != state["base_ruleset"]:
                    raise ValueError(
                        "Published base changed: rebase and review candidate before publication"
                    )
            report = validate_corpus(root, ruleset)
            save(directory / "validation.json", report)
            if not report["release_ready"]:
                raise ValueError(
                    f"Review gate: {len(report['issues'])} issues; see validation.json"
                )
            publish_snapshot(root, ruleset)
            entry.update(status="published", published_at=now(), error=None)
            state["base_ruleset"] = ruleset
        except (OSError, ValueError, KeyError, TypeError) as error:
            entry.update(status="review_blocked", error=str(error))


def run_once(root: Path, *, settle_seconds=5.0, retry=False):
    root = root.resolve()
    with lock(root):
        registry = read(root / REGISTRY, {})
        state = registry.setdefault("pipeline", initial_state(root))
        before = copy.deepcopy(state)
        catalog = read(root / "data/sources/catalog.json", {"sources": []})
        registered = {s["source_path"].replace("\\", "/"): s for s in catalog["sources"]}
        ready = []
        present = set()
        for path in sorted((root / "法律法规").rglob("*")):
            if not path.is_file() or path.name.startswith(("~$", ".")):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(
                (root / "法律法规").resolve()
            ):
                continue
            relative = path.relative_to(root).as_posix()
            present.add(relative)
            try:
                digest = sha256(path)
                previous = state["observations"].get(relative, {})
                if previous.get("sha256") != digest:
                    state["observations"][relative] = {"sha256": digest, "first_seen": time.time()}
                observed = state["observations"][relative]
                observed["present"] = True
                source = registered.get(relative, {})
                version = state["versions"].get(digest)
                # User-deferred/reference files stay deferred, even when their bytes change.
                if (
                    source.get("workflow_status") == "extraction_deferred_by_user"
                    or source.get("membership") == "reference_only"
                ):
                    observed["status"] = source.get("workflow_status", "reference_only")
                    continue
                if source.get("source_sha256") == digest and source.get("membership") == "include":
                    observed["status"] = "registered_existing"
                    continue
                if path.suffix.lower() not in SUPPORTED:
                    observed["status"] = "unsupported"
                    continue
                if time.time() - observed["first_seen"] < settle_seconds:
                    observed["status"] = "settling"
                    continue
                if version and not (retry and version["status"] == "failed"):
                    observed["status"] = version["status"]
                    if version["status"] == "extracted" and not version.get("candidate"):
                        ready.append(version)
                    continue
                version = process_source(root, path, digest)
                state["versions"][digest] = version
                observed["status"] = "extracted"
                ready.append(version)
            except Exception as error:  # noqa: BLE001 -- isolate one file; persist its failure
                observed = state["observations"].setdefault(relative, {})
                observed.update(status="failed", error=str(error))
                if observed.get("sha256"):
                    state["versions"][observed["sha256"]] = {
                        "status": "failed",
                        "source_path": relative,
                        "error": str(error),
                        "failed_at": now(),
                    }
        for path, observation in state["observations"].items():
            if path not in present:
                observation["present"] = False
        if ready:
            # Register candidates explicitly, never give them effective/legal verified status.
            for version in {v["source_sha256"]: v for v in ready}.values():
                doc = read(root / version["artifact_dir"] / "document.json")
                if not any(s["document_id"] == doc["document_id"] for s in catalog["sources"]):
                    catalog["sources"].append(
                        {**doc, "membership": "candidate", "verification_status": "pending_review"}
                    )
            save(root / "data/sources/catalog.json", catalog)
            ruleset = build_proposal(
                root, state, list({v["source_sha256"]: v for v in ready}.values())
            )
            for version in ready:
                version.update(candidate=ruleset, status="needs_review")
            save(root / "data/corpus" / ruleset / "validation.json", validate_corpus(root, ruleset))
        resume_candidates(root, state)
        state["last_run"] = now()
        state["pid"] = os.getpid()
        registry["pipeline"] = state
        from insurance_audit.corpus.registry import rebuild

        rebuild(root, state)
        return {
            "base_ruleset": state["base_ruleset"],
            "observed_files": len(present),
            "new_candidates": 1 if ready else 0,
            "candidates": state["candidates"],
            "changed": before.get("versions") != state["versions"],
        }


def seal_review(root: Path, ruleset: str):
    """Explicit completion by a reviewer, never invoked on raw file discovery."""
    from insurance_audit.corpus.ingest import confined

    with lock(root):
        directory = confined(root, "data/corpus/" + ruleset)
        if read(directory / "manifest.json", {}).get("publication_status") == "published":
            raise ValueError("Published snapshot cannot be resealed")
        evidence = read(directory / "review.json", {})
        reviewer = evidence.get("reviewer", {})
        if reviewer.get("type") not in {
            "implementation_agent",
            "human",
            "legal_expert",
        } or not reviewer.get("id"):
            raise ValueError("A completed, attributable review.json is required")
        if not evidence.get("method") or evidence["method"].startswith("REPLACE"):
            raise ValueError("Describe the actual completed review method")
        docs = [
            json.loads(line)
            for line in (directory / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        catalog = read(root / "data/sources/catalog.json")
        for doc in docs:
            if doc["document_status"] != "effective" or not doc.get("effective_on"):
                raise ValueError("Document status and effective date require review")
            source = next(s for s in catalog["sources"] if s["document_id"] == doc["document_id"])
            if source["source_sha256"] != doc["source_sha256"]:
                raise ValueError("Reviewed source hash differs from catalog")
            source.update(
                {k: doc[k] for k in ("title", "document_status", "effective_on", "source_type")}
            )
            source["membership"] = "include"
        apply_review(root, ruleset)
        save(root / "data/sources/catalog.json", catalog)
        result = validate_corpus(root, ruleset)
        save(directory / "validation.json", result)
        if not result["release_ready"]:
            raise ValueError(
                f"Review incomplete: {len(result['issues'])} issues; see validation.json"
            )
        save(
            directory / "review-approval.json",
            {
                "approved": True,
                "ruleset_id": ruleset,
                "manifest_sha256": sha256(directory / "manifest.json"),
                "reviewer": reviewer,
                "at": now(),
            },
        )
        return {"ruleset_id": ruleset, "status": "approved_waiting_for_pipeline"}


def watch(root: Path, *, interval=5.0):
    if interval < 1:
        raise ValueError("Watch interval must be at least one second")
    with lock(root, "watcher.lock"):
        control = root / "data/runtime"
        stop = control / "pipeline.stop"
        stop.unlink(missing_ok=True)
        save(control / "pipeline-watcher.json", {"pid": os.getpid(), "started_at": now()})
        while not stop.exists():
            try:
                result = run_once(root, settle_seconds=interval)
                save(
                    control / "pipeline-health.json",
                    {"status": "running", "last_scan": now(), **result},
                )
            except Exception as error:  # noqa: BLE001 -- keep watcher alive, expose health failure
                save(
                    control / "pipeline-health.json",
                    {"status": "error", "last_scan": now(), "error": str(error)},
                )
            time.sleep(interval)
        save(control / "pipeline-health.json", {"status": "stopped", "at": now()})


def start(root: Path, interval=5.0):
    import sys

    if interval < 1:
        raise ValueError("Watch interval must be at least one second")
    try:
        with lock(root, "watcher.lock"):
            pass
    except OSError:
        return {
            "status": "already_running",
            "watcher": read(root / "data/runtime/pipeline-watcher.json", {}),
        }
    runtime = root / "data/runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "pipeline.log").open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "insurance_audit.cli",
                "pipeline",
                "watch",
                "--root",
                str(root),
                "--interval",
                str(interval),
            ],
            cwd=root,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    return {"started_pid": process.pid, "health_file": str(runtime / "pipeline-health.json")}
