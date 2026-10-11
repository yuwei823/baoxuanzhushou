"""One inventory joining source versions, extraction artifacts and corpus snapshots."""

import json
from datetime import UTC, datetime
from pathlib import Path

from insurance_audit.corpus.ingest import sha256


def rebuild(root: Path, state=None):
    from insurance_audit.corpus.pipeline import REGISTRY, read, save

    old = read(root / REGISTRY, {})
    state = state if state is not None else old.get("pipeline")
    catalog = read(root / "data/sources/catalog.json", {"sources": []})
    manifests = [(p, read(p)) for p in (root / "data/corpus").glob("*/manifest.json")]
    published = [(p, m) for p, m in manifests if m.get("publication_status") == "published"]
    latest = max(
        published, key=lambda item: item[1].get("published_at_utc", ""), default=(None, {})
    )
    active = (state or {}).get("base_ruleset") or latest[1].get("ruleset_id")
    snapshots = []
    by_document = {}
    for path, manifest in manifests:
        directory = path.parent
        docs_path = directory / "documents.jsonl"
        docs = (
            [json.loads(line) for line in docs_path.read_text(encoding="utf-8").splitlines()]
            if docs_path.exists()
            else []
        )
        snapshots.append(
            {
                "ruleset_id": manifest["ruleset_id"],
                "status": manifest["publication_status"],
                "manifest_path": path.relative_to(root).as_posix(),
                "manifest_sha256": sha256(path),
                "artifacts": manifest.get("artifacts", {}),
                "document_ids": [d["document_id"] for d in docs],
            }
        )
        for doc in docs:
            previous = by_document.get(doc["document_id"])
            if previous is None or manifest["ruleset_id"] == active:
                by_document[doc["document_id"]] = doc
    old_entries = {d["document_id"]: d for d in old.get("documents", [])}
    entries = []
    for source in catalog["sources"]:
        did = source["document_id"]
        path = root / source["source_path"]
        actual = sha256(path) if path.is_file() else None
        doc = by_document.get(did, {})
        historical = old_entries.get(did, {})
        extraction = historical.get("extraction", {}).copy()
        if doc:
            extract_path = root / doc["snapshot_extraction_path"]
            extraction.update(
                status="extracted",
                tool=doc["extraction_method"],
                tool_version=doc["extraction_version"],
                outputs=[
                    {
                        "path": doc["snapshot_extraction_path"],
                        "exists": extract_path.is_file(),
                        "sha256": sha256(extract_path) if extract_path.is_file() else None,
                        "expected_sha256": doc["extraction_sha256"],
                    }
                ],
            )
        entries.append(
            {
                "document_id": did,
                "title": source["title"],
                "source": {
                    "path": source["source_path"],
                    "exists": path.is_file(),
                    "sha256_expected": source["source_sha256"],
                    "sha256_actual": actual,
                    "sha256_matches_catalog": actual == source["source_sha256"],
                    "document_status": source.get("document_status"),
                    "membership": source.get("membership"),
                    "source_type": source.get("source_type"),
                    "effective_on": source.get("effective_on"),
                },
                "extraction": extraction,
                "validation": {
                    "source_hash": "passed"
                    if actual == source["source_sha256"]
                    else "changed_or_missing",
                    "legal_text": "reviewed" if doc.get("legal_text_verified") else "not_verified",
                    "reviewer_type": doc.get("reviewer_type"),
                    "rule_mapping": "reviewed"
                    if doc.get("legal_text_verified")
                    else "pending_review",
                    "workflow_status": source.get("workflow_status", source.get("membership")),
                    "previous_checks": historical.get("validation", {}).get("previous_checks")
                    or {
                        k: v
                        for k, v in historical.get("validation", {}).items()
                        if k in {"structure", "article_marker_count", "corpus_article_count"}
                    },
                },
                "snapshots": [s["ruleset_id"] for s in snapshots if did in s["document_ids"]],
            }
        )
    active_docs = [
        by_document[did]
        for s in snapshots
        if s["ruleset_id"] == active
        for did in s["document_ids"]
    ]
    result = {
        "registry_schema_version": "2.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "generated_by": "insurance_audit.corpus.registry",
        "ruleset_id": active,
        "ruleset_status": "published" if active else "not_published",
        "ruleset_published": bool(active),
        "source_count": len(entries),
        "source_hashes_all_match": all(e["source"]["sha256_matches_catalog"] for e in entries),
        "legal_text_verified": bool(active_docs)
        and all(d.get("legal_text_verified") for d in active_docs),
        "documents": entries,
        "snapshots": snapshots,
    }
    if state is not None:
        result["pipeline"] = state
    save(root / REGISTRY, result)
    return result
