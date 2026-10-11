"""Hash-bound review evidence and explicit immutable snapshot publication."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from insurance_audit.corpus.ingest import confined, snapshot_manifest, write_jsonl

REVIEW_FIELDS = {"verified", "verification_status", "reviewer_type", "review_record"}


def semantic_digest(record: dict) -> str:
    payload = {k: v for k, v in record.items() if k not in REVIEW_FIELDS}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def apply_review(root: Path, ruleset_id: str) -> None:
    output = confined(root, f"data/corpus/{ruleset_id}")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("publication_status") == "published":
        raise ValueError("Published snapshot is immutable")
    evidence = json.loads((output / "review.json").read_text(encoding="utf-8"))
    if evidence["ruleset_id"] != ruleset_id:
        raise ValueError("Review ruleset mismatch")
    rows = {
        name: [
            json.loads(line)
            for line in (output / name).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for name in ("documents.jsonl", "articles.jsonl", "rule_cards.jsonl")
    }
    if set(evidence["articles"]) != {a["article_id"] for a in rows["articles.jsonl"]}:
        raise ValueError("Review must cover the exact article set")
    if set(evidence["rules"]) != {c["rule_id"] for c in rows["rule_cards.jsonl"]}:
        raise ValueError("Review must cover the exact rule set")
    for doc in rows["documents.jsonl"]:
        review = evidence["documents"][doc["document_id"]]
        if (
            review["source_sha256"] != doc["source_sha256"]
            or review["extraction_sha256"] != doc["extraction_sha256"]
        ):
            raise ValueError("Source differs from reviewed evidence")
        doc["legal_text_verified"] = True
        doc["reviewer_type"] = evidence["reviewer"]["type"]
    for article in rows["articles.jsonl"]:
        if evidence["articles"][article["article_id"]]["text_sha256"] != article["text_sha256"]:
            raise ValueError("Article differs from reviewed text")
        article["verified"] = True
        article["reviewer_type"] = evidence["reviewer"]["type"]
    for card in rows["rule_cards.jsonl"]:
        if evidence["rules"][card["rule_id"]]["digest"] != semantic_digest(card):
            raise ValueError("Rule differs from reviewed mapping")
        card["verified"] = True
        card["verification_status"] = "reviewed_source_mapping"
        card["reviewer_type"] = evidence["reviewer"]["type"]
    ledger = [review["scope"] for review in evidence["articles"].values()]
    for name, content in rows.items():
        write_jsonl(output / name, content)
    write_jsonl(output / "article-review-ledger.jsonl", ledger)
    snapshot_manifest(root, output, ruleset_id)


def publish_snapshot(root: Path, ruleset_id: str) -> dict:
    from insurance_audit.corpus.validate import validate_corpus

    result = validate_corpus(root, ruleset_id)
    if not result["release_ready"]:
        raise ValueError(f"Publication blocked: {len(result['issues'])} validation issues")
    output = confined(root, f"data/corpus/{ruleset_id}")
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("publication_status") != "published":
        manifest["publication_status"] = "published"
        manifest["published_at_utc"] = datetime.now(UTC).isoformat()
        reviewer = json.loads((output / "review.json").read_text(encoding="utf-8"))["reviewer"]
        manifest["review_basis"] = reviewer["type"] + "_local_source_review"
        manifest["production_legal_certification"] = False
        temporary = output / "manifest.pending.json"
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(manifest_path)
    return manifest
