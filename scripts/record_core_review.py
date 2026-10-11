"""Record this implementation agent's completed review of the 50/39/83 local texts.

Review scope decisions and obligation recipes are explicit in core_rule_review_data.
This operation never reviews arbitrary new documents and does not publish the corpus.
"""

import json
from pathlib import Path

from core_rule_review_data import PREFIXES, SCOPE_GROUPS, ref

from insurance_audit.corpus.ingest import parse_units
from insurance_audit.corpus.review import apply_review, semantic_digest

ROOT = Path(__file__).resolve().parents[1]
RULESET = "official-v1-2026-10-11"
OUTPUT = ROOT / "data/corpus" / RULESET


def read(name):
    return [
        json.loads(line)
        for line in (OUTPUT / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def record_review():
    if (
        json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8")).get("publication_status")
        == "published"
    ):
        raise ValueError("Published review evidence cannot be overwritten")
    documents = read("documents.jsonl")
    articles = read("articles.jsonl")
    cards = read("rule_cards.jsonl")
    if {d["document_id"] for d in documents} != set(PREFIXES.values()):
        raise ValueError("This review covers only the three explicitly reviewed core documents")
    classification = {}
    for code, groups in SCOPE_GROUPS.items():
        numbers = [n for _, nums, _ in groups for n in nums]
        expected = {"S": 50, "F": 39, "I": 83}[code]
        if len(numbers) != expected or set(numbers) != set(range(1, expected + 1)):
            raise ValueError("Review classification coverage differs from the reviewed source")
        for checkability, nums, reason in groups:
            for number in nums:
                classification[ref(f"{code}{number}")] = (checkability, reason)
    if set(classification) != {a["article_id"] for a in articles}:
        raise ValueError("Reviewed article set differs")
    reconstructed = {}
    for doc in documents:
        extract = ROOT / doc["snapshot_extraction_path"]
        rows = parse_units(
            json.loads(extract.read_text(encoding="utf-8")), pdf=doc["source_path"].endswith(".pdf")
        )
        reconstructed.update(
            {
                f"{doc['document_id']}::art_{index:03d}": "\n".join(row["parts"]).strip()
                for index, row in enumerate(rows, 1)
            }
        )
    for article in articles:
        if reconstructed[article["article_id"]] != article["original_text"]:
            raise ValueError("Article does not reconstruct from its preserved extraction")
    record = {
        "ruleset_id": RULESET,
        "reviewed_on": "2026-10-11",
        "reviewer": {"type": "implementation_agent", "id": "codex", "is_legal_expert": False},
        "method": "Read all 172 local extracted articles; check source reconstruction, "
        "subjects, channels, exact obligations, exceptions and scope exclusions.",
        "scope": "Only the three core local regulations; insurance law deferred by user.",
        "evidence_report": "reports/core-p0-review.md",
        "documents": {},
        "articles": {},
        "rules": {},
    }
    for doc in documents:
        record["documents"][doc["document_id"]] = {
            "source_sha256": doc["source_sha256"],
            "extraction_sha256": doc["extraction_sha256"],
            "status": "reviewed_local_extraction",
            "official_check": "metadata_and_sample_only",
        }
    for article in articles:
        aid = article["article_id"]
        checkability, reason = classification[aid]
        rule_ids = sorted(c["rule_id"] for c in cards if aid in c["article_ids"])
        if checkability != "out_of_scope" and not rule_ids:
            raise ValueError(f"Eligible obligation lacks a rule card: {aid}")
        scope = {
            "article_id": aid,
            "ruleset_id": RULESET,
            "rule_ids": rule_ids,
            "classification_status": "reviewed",
            "checkability": checkability,
            "exclusion_reason": reason if checkability == "out_of_scope" else None,
            "scope_note": reason,
            "verified": True,
            "reviewer_type": "implementation_agent",
        }
        record["articles"][aid] = {"text_sha256": article["text_sha256"], "scope": scope}
    for card in cards:
        record["rules"][card["rule_id"]] = {
            "digest": semantic_digest(card),
            "status": "reviewed_source_mapping",
            "note": "Distinct clause subjects and exceptions preserved; external facts and "
            "cross-referenced advertising rules remain unresolved at audit time.",
        }
    (OUTPUT / "review.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    apply_review(ROOT, RULESET)
    print(f"Recorded hash-bound agent review: {len(articles)} articles, {len(cards)} rule cards")


if __name__ == "__main__":
    record_review()
