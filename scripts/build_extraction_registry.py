"""Build the canonical source-to-extraction registry for the local rules corpus."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT / "data" / "extracted"
CATALOG_PATH = ROOT / "data" / "sources" / "catalog.json"
REGISTRY_PATH = EXTRACTED / "extraction-registry.json"


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(path: Path) -> dict:
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256(path) if path.is_file() else None,
    }


def source_stem(source_path: str) -> str:
    return Path(source_path).stem


def build_registry() -> dict:
    catalog = read_json(CATALOG_PATH, {"catalog_version": None, "sources": []})
    doc_log = read_json(EXTRACTED / "doc-extraction.json", [])
    pdf_log = read_json(EXTRACTED / "金融产品网络营销管理办法.metadata.json", {})
    audit = read_json(EXTRACTED / "source-audit.json", {})
    attempts = read_json(EXTRACTED / "extraction-attempts.json", {}).get("attempts", [])
    parse_summary = read_json(
        ROOT / "data" / "corpus" / "official-v1-2026-10-11" / "parse-summary.json", {}
    )
    cards_path = ROOT / "data" / "corpus" / "official-v1-2026-10-11" / "rule_cards.jsonl"
    rule_cards = (
        [json.loads(line) for line in cards_path.read_text(encoding="utf-8").splitlines()]
        if cards_path.is_file() else []
    )
    by_doc_log = {Path(record.get("source", "")).name: record for record in doc_log}
    by_attempt = {}
    for attempt in attempts:
        by_attempt.setdefault(attempt["document_id"], []).append(attempt)

    entries = []
    for source in catalog["sources"]:
        source_path = source["source_path"]
        name = Path(source_path).name
        stem = source_stem(source_path)
        source_file = ROOT / source_path
        actual_source_hash = sha256(source_file) if source_file.is_file() else None
        doc_record = by_doc_log.get(name)
        if source_file.suffix.lower() == ".pdf" and pdf_log.get("source"):
            pdf_matches = Path(pdf_log["source"]).name == name
        else:
            pdf_matches = False

        outputs = []
        extractor = None
        tool_version = None
        extraction_metadata = {}
        if doc_record:
            extractor = doc_record.get("extractor")
            tool_version = doc_record.get("version")
            extraction_metadata = {
                key: doc_record.get(key)
                for key in ("characters", "paragraphs", "verified")
            }
            outputs = [
                artifact(EXTRACTED / f"{stem}.txt"),
                artifact(EXTRACTED / f"{stem}.paragraphs.json"),
            ]
        elif pdf_matches:
            extractor = pdf_log.get("extractor")
            tool_version = pdf_log.get("pymupdf_version")
            extraction_metadata = {
                "page_count": pdf_log.get("pdf_page_count"),
                "pdf_metadata": pdf_log.get("metadata"),
                "extracted_page_char_counts": pdf_log.get("extracted_page_char_counts"),
                "verified": pdf_log.get("verified", False),
            }
            outputs = [
                artifact(EXTRACTED / f"{stem}.txt"),
                artifact(EXTRACTED / f"{stem}.pages.json"),
                artifact(EXTRACTED / f"{stem}.metadata.json"),
            ]

        missing_outputs = [item["path"] for item in outputs if not item["exists"]]
        source_hash_matches = bool(
            source_file.is_file()
            and actual_source_hash == source.get("source_sha256")
        )
        if source.get("membership") == "reference_only":
            extraction_status = "not_selected"
        elif not outputs and by_attempt.get(source["document_id"]):
            extraction_status = "failed"
        elif missing_outputs:
            extraction_status = "failed" if by_attempt.get(source["document_id"]) else "pending"
        elif outputs:
            extraction_status = "extracted"
        else:
            extraction_status = "pending"

        audit_record = None
        for candidate in audit.get("records", []):
            label = candidate.get("source_extract", candidate.get("source", ""))
            if stem in label:
                audit_record = candidate
                break

        attempts_for_source = by_attempt.get(source["document_id"], [])
        if attempts_for_source and not extractor:
            latest_attempt = attempts_for_source[-1]
            extractor = latest_attempt.get("tool")
            tool_version = latest_attempt.get("tool_version")
        corpus_count = parse_summary.get("by_document", {}).get(source["document_id"], 0)
        entries.append(
            {
                "document_id": source["document_id"],
                "title": source["title"],
                "source": {
                    "path": source_path.replace("\\", "/"),
                    "exists": source_file.is_file(),
                    "size_bytes": source_file.stat().st_size if source_file.is_file() else None,
                    "sha256_expected": source.get("source_sha256"),
                    "sha256_actual": actual_source_hash,
                    "sha256_matches_catalog": source_hash_matches,
                    "source_type": source.get("source_type"),
                    "document_status": source.get("document_status"),
                    "membership": source.get("membership"),
                    "published_on": source.get("published_on"),
                    "effective_on": source.get("effective_on"),
                    "last_amended_on": source.get("last_amended_on"),
                    "official_source_url": source.get("official_source_url"),
                },
                "extraction": {
                    "status": extraction_status,
                    "tool": extractor,
                    "tool_version": tool_version,
                    "metadata": extraction_metadata,
                    "outputs": outputs,
                    "missing_outputs": missing_outputs,
                    "attempts": attempts_for_source,
                },
                "validation": {
                    "source_hash": "passed" if source_hash_matches else "failed",
                    "structure": (
                        "passed" if audit_record and audit_record.get("ordered_unique_contiguous")
                        else "not_run"
                    ),
                    "article_marker_count": (
                        audit_record.get("article_heading_count") if audit_record else None
                    ),
                    "legal_text": "not_verified",
                    "rule_mapping": "not_completed",
                    "corpus_article_count": corpus_count,
                },
            }
        )

    status_values = [entry["validation"]["source_hash"] for entry in entries]
    corpus_dir = ROOT / "data" / "corpus" / "official-v1-2026-10-11"
    corpus_files = [
        corpus_dir / "documents.jsonl",
        corpus_dir / "articles.jsonl",
        corpus_dir / "chunks.jsonl",
        corpus_dir / "rule_cards.jsonl",
        corpus_dir / "parse-summary.json",
    ]
    result = {
        "registry_schema_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "generated_by": "scripts/build_extraction_registry.py",
        "ruleset_id": "official-v1-2026-10-11",
        "ruleset_status": "candidate_unpublished",
        "catalog_version": catalog.get("catalog_version"),
        "source_count": len(entries),
        "source_hashes_all_match": all(value == "passed" for value in status_values),
        "legal_text_verified": False,
        "ruleset_published": False,
        "corpus": {
            "article_count": parse_summary.get("article_count"),
            "rule_card_count": len(rule_cards),
            "verified_rule_card_count": sum(bool(card.get("verified")) for card in rule_cards),
            "by_document": parse_summary.get("by_document", {}),
            "parser": "scripts/parse_official_articles.py",
            "status": "candidate_unverified" if parse_summary else "not_built",
            "artifacts": [artifact(path) for path in corpus_files],
        },
        "documents": entries,
    }
    REGISTRY_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = build_registry()
    print(f"Wrote {REGISTRY_PATH.relative_to(ROOT)} ({result['source_count']} sources)")
