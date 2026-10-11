"""Validate corpus integrity separately from legal review and release readiness."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from insurance_audit.corpus.ingest import article_number, confined, sha256
from insurance_audit.corpus.review import semantic_digest

FILES = (
    "documents.jsonl",
    "articles.jsonl",
    "chunks.jsonl",
    "rule_cards.jsonl",
    "article-review-ledger.jsonl",
)
CHECKABILITY = {"content_checkable", "context_required", "external_verification", "out_of_scope"}


def validate_corpus(root: Path, ruleset_id: str) -> dict:
    issues = []

    def issue(code: str, location: str, detail: str, *, gate: bool = False) -> None:
        issues.append(
            {
                "code": code,
                "location": location,
                "detail": detail,
                "kind": "review_gate" if gate else "integrity_error",
            }
        )

    output = confined(root, f"data/corpus/{ruleset_id}")
    records = {}
    for name in FILES:
        try:
            rows = [
                json.loads(line)
                for line in (output / name).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not rows or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Expected nonempty JSONL objects")
            records[name] = rows
        except (OSError, ValueError) as error:
            issue("invalid_file", name, str(error))
            records[name] = []
    try:
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise TypeError("Expected manifest object")
    except (OSError, ValueError, TypeError) as error:
        manifest = {}
        issue("invalid_manifest", "manifest.json", str(error))
    if manifest.get("ruleset_id") != ruleset_id:
        issue("ruleset_mismatch", "manifest.json", "Requested and declared IDs differ")
    if not isinstance(manifest.get("artifacts"), dict):
        issue("invalid_manifest", "manifest.json", "Artifacts must be an object")
        manifest["artifacts"] = {}
    for name in FILES:
        if (output / name).is_file() and manifest.get("artifacts", {}).get(name) != sha256(
            output / name
        ):
            issue("artifact_hash_mismatch", name, "Content differs from snapshot manifest")

    def index(rows: list[dict], key: str, required: tuple[str, ...], filename: str) -> dict:
        indexed = {}
        for row_number, row in enumerate(rows, 1):
            location = f"{filename}:{row_number}"
            if any(field not in row or row[field] is None for field in required):
                issue("missing_field", location, f"Required: {required}")
            identifier = row.get(key)
            if not isinstance(identifier, str) or not identifier:
                issue("invalid_id", location, key)
                continue
            if identifier in indexed:
                issue("duplicate_id", location, identifier)
            indexed[identifier] = row
        return indexed

    docs = index(
        records[FILES[0]],
        "document_id",
        (
            "document_id",
            "title",
            "source_path",
            "source_sha256",
            "document_status",
            "ruleset_id",
            "extraction_path",
            "extraction_sha256",
            "extraction_method",
            "extraction_version",
        ),
        FILES[0],
    )
    articles = index(
        records[FILES[1]],
        "article_id",
        (
            "article_id",
            "document_id",
            "article_no",
            "article_label",
            "original_text",
            "normalized_text",
            "source_locator",
            "text_sha256",
            "verified",
        ),
        FILES[1],
    )
    chunks = index(
        records[FILES[2]], "chunk_id", ("chunk_id", "article_id", "document_id", "text"), FILES[2]
    )
    cards = index(
        records[FILES[3]],
        "rule_id",
        (
            "rule_id",
            "article_ids",
            "category",
            "subject_scope",
            "channel_scope",
            "product_scope",
            "trigger_conditions",
            "prohibited_or_required_behavior",
            "exceptions",
            "required_facts",
            "checkability",
            "coverage_group",
            "interpretation_note",
            "verified",
            "ruleset_id",
        ),
        FILES[3],
    )
    ledger = index(
        records[FILES[4]],
        "article_id",
        ("article_id", "ruleset_id", "rule_ids", "classification_status", "verified"),
        FILES[4],
    )
    declared_sources = manifest.get("sources")
    if not isinstance(declared_sources, list) or any(
        not isinstance(source, dict) for source in declared_sources
    ):
        issue("invalid_manifest_sources", "manifest.json", "Sources must be objects")
    else:
        source_ids = [source.get("document_id") for source in declared_sources]
        if any(not isinstance(did, str) for did in source_ids) or sorted(source_ids) != sorted(
            docs
        ):
            issue("manifest_source_coverage", "manifest.json", "Sources differ from document set")
        for source in declared_sources:
            did = source.get("document_id")
            if isinstance(did, str) and did in docs:
                for field, value in source.items():
                    if docs[did].get(field) != value:
                        issue("manifest_source_mismatch", did, field)
    try:
        catalog = json.loads((root / "data/sources/catalog.json").read_text(encoding="utf-8"))
        sources = {s["document_id"]: s for s in catalog["sources"]}
    except (OSError, ValueError, KeyError, TypeError) as error:
        sources = {}
        issue("invalid_source_catalog", "catalog.json", str(error))
    for did, doc in docs.items():
        source = sources.get(did, {})
        if source.get("membership") != "include":
            issue("unregistered_source", did, "Not explicitly included")
        for field in ("source_path", "source_sha256", "document_status", "title"):
            if doc.get(field) != source.get(field):
                issue("source_metadata_mismatch", did, field)
        if doc.get("ruleset_id") != ruleset_id:
            issue("ruleset_mismatch", did, "Wrong document ruleset")
        if (
            manifest.get("ruleset_mode") == "official_snapshot"
            and doc.get("document_status") != "effective"
        ):
            issue("version_mixed", did, "Official snapshot contains a non-effective source")
        for path_field, hash_field in (
            ("snapshot_source_path", "source_sha256"),
            ("snapshot_extraction_path", "extraction_sha256"),
        ):
            try:
                path = confined(root, doc.get(path_field, ""))
                if not path.is_file() or sha256(path) != doc.get(hash_field):
                    issue("source_hash_mismatch", did, path_field)
            except (OSError, ValueError, TypeError) as error:
                issue("invalid_source_path", did, str(error))
        if doc.get("legal_text_verified") is not True:
            issue("unreviewed_document", did, "Source text review missing", gate=True)
        if manifest.get("ruleset_mode") == "official_snapshot":
            try:
                effective = datetime.strptime(doc["effective_on"], "%Y-%m-%d").date()
                today = datetime.now(timezone(timedelta(hours=8))).date()
                if effective > today:
                    issue("not_yet_effective", did, "Effective date is in the future")
            except (KeyError, TypeError, ValueError):
                issue("invalid_effective_date", did, "Reviewed effective date required", gate=True)

    for aid, article in articles.items():
        text = article.get("original_text")
        if not isinstance(text, str) or not text.strip():
            issue("empty_article", aid, "Missing original text")
            continue
        if article.get("document_id") not in docs:
            issue("missing_document", aid, str(article.get("document_id")))
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != article.get("text_sha256"):
            issue("article_hash_mismatch", aid, "Original text hash differs")
        if article.get("normalized_text") != " ".join(text.split()):
            issue("normalization_mismatch", aid, "Normalized text does not match original")
        try:
            number = article_number(article.get("article_label", ""))
            if (
                type(article.get("article_no")) is not int
                or number != article["article_no"]
                or aid != f"{article.get('document_id')}::art_{number:03d}"
            ):
                issue("article_id_mismatch", aid, "Label, number and ID differ")
        except (ValueError, TypeError, AttributeError) as error:
            issue("invalid_article_label", aid, str(error))
        if not isinstance(article.get("source_locator"), dict) or not article["source_locator"]:
            issue("missing_locator", aid, "No source location")
        if article.get("verified") is not True:
            issue("unreviewed_article", aid, "Text review missing", gate=True)
    for did in docs:
        numbers = [a.get("article_no") for a in articles.values() if a.get("document_id") == did]
        if (
            not numbers
            or any(type(n) is not int for n in numbers)
            or sorted(numbers) != list(range(1, len(numbers) + 1))
        ):
            issue("article_sequence", did, "Missing, duplicate or invalid article numbers")
    covered = set()
    for cid, chunk in chunks.items():
        article = articles.get(chunk.get("article_id"))
        if article is None:
            issue("missing_parent_article", cid, "Dangling chunk reference")
        elif chunk.get("text") != article.get("original_text") or chunk.get(
            "document_id"
        ) != article.get("document_id"):
            issue("chunk_parent_mismatch", cid, "Whole-article chunk differs from parent")
        covered.add(chunk.get("article_id"))
    if covered != set(articles):
        issue("chunk_coverage", FILES[2], "Chunks do not cover exactly the article set")
    for rid, card in cards.items():
        references = card.get("article_ids")
        if (
            not isinstance(references, list)
            or not references
            or any(not isinstance(ref, str) or ref not in articles for ref in references)
        ):
            issue("invalid_rule_reference", rid, "Missing or dangling article ID")
        if card.get("checkability") not in CHECKABILITY:
            issue("invalid_checkability", rid, str(card.get("checkability")))
        supporting = card.get("supporting_article_ids", [])
        if not isinstance(supporting, list) or any(
            not isinstance(ref, str) or ref not in articles for ref in supporting
        ):
            issue("invalid_scope_reference", rid, "Missing definition/scope/exception article")
        for field in (
            "subject_scope",
            "channel_scope",
            "product_scope",
            "trigger_conditions",
            "required_facts",
            "exceptions",
        ):
            if (
                not isinstance(card.get(field), list)
                or not card[field]
                or any(not isinstance(value, str) or not value.strip() for value in card[field])
            ):
                issue("invalid_rule_field", rid, field)
        if card.get("ruleset_id") != ruleset_id:
            issue("ruleset_mismatch", rid, "Wrong rule ruleset")
        if card.get("verified") is not True:
            issue("unreviewed_rule", rid, "Legal mapping review missing", gate=True)
    if set(ledger) != set(articles):
        issue("ledger_coverage", FILES[4], "Every article must have exactly one review entry")
    for aid, entry in ledger.items():
        expected = sorted(
            rid
            for rid, c in cards.items()
            if isinstance(c.get("article_ids"), list) and aid in c["article_ids"]
        )
        if entry.get("rule_ids") != expected:
            issue("ledger_rule_mismatch", aid, "Ledger and cards disagree")
        if entry.get("ruleset_id") != ruleset_id:
            issue("ruleset_mismatch", aid, "Wrong ledger ruleset")
        if (
            entry.get("verified") is not True
            or entry.get("checkability") not in CHECKABILITY
            or entry.get("classification_status") != "reviewed"
        ):
            issue("unclassified_article", aid, "Review/classification incomplete", gate=True)
        if entry.get("checkability") == "out_of_scope" and not entry.get("exclusion_reason"):
            issue("missing_exclusion_reason", aid, "Excluded article needs a reason")
        if entry.get("checkability") in CHECKABILITY - {"out_of_scope"} and not expected:
            issue("missing_obligation_mapping", aid, "In-scope article has no rule card")
    try:
        review_path = output / "review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if manifest.get("artifacts", {}).get("review.json") != sha256(review_path):
            issue("review_hash_mismatch", "review.json", "Review evidence was changed")
        if review["ruleset_id"] != ruleset_id:
            issue("ruleset_mismatch", "review.json", "Wrong review ruleset")
        if review["reviewer"]["type"] not in {"implementation_agent", "human", "legal_expert"}:
            issue("invalid_reviewer", "review.json", "Reviewer type must be explicit")
        if (
            set(review["documents"]) != set(docs)
            or set(review["articles"]) != set(articles)
            or set(review["rules"]) != set(cards)
        ):
            issue("review_coverage", "review.json", "Review does not cover the exact corpus")
        for did, doc in docs.items():
            record = review["documents"].get(did, {})
            if record.get("source_sha256") != doc.get("source_sha256") or record.get(
                "extraction_sha256"
            ) != doc.get("extraction_sha256"):
                issue("review_source_changed", did, "Source differs from reviewed content")
        for aid, article in articles.items():
            record = review["articles"].get(aid, {})
            if record.get("text_sha256") != article.get("text_sha256"):
                issue("review_text_changed", aid, "Article differs from reviewed text")
            if record.get("scope") != ledger.get(aid):
                issue("review_scope_changed", aid, "Classification differs from review")
        for rid, card in cards.items():
            if review["rules"].get(rid, {}).get("digest") != semantic_digest(card):
                issue("review_rule_changed", rid, "Rule differs from reviewed mapping")
    except FileNotFoundError:
        issue("missing_review_record", "review.json", "No hash-bound review evidence", gate=True)
    except (OSError, ValueError, TypeError, KeyError) as error:
        issue("invalid_review_record", "review.json", str(error))
    integrity = [i for i in issues if i["kind"] == "integrity_error"]
    gates = [i for i in issues if i["kind"] == "review_gate"]
    return {
        "ruleset_id": ruleset_id,
        "structural_valid": not integrity,
        "release_ready": not issues,
        "integrity_error_count": len(integrity),
        "review_gate_count": len(gates),
        "counts": {
            "documents": len(docs),
            "articles": len(articles),
            "chunks": len(chunks),
            "rules": len(cards),
            "ledger": len(ledger),
        },
        "issues": issues,
    }


def write_report(report: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
