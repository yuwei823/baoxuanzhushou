import json
from pathlib import Path

import pytest

from insurance_audit.corpus.ingest import article_number, parse_units, snapshot_manifest
from insurance_audit.corpus.validate import validate_corpus


def test_chapters_are_not_appended_to_previous_article():
    rows = parse_units(["第一章 总则\r第一条 原文。\r第二章 营销\r第二条 例外。"])
    assert rows[0]["parts"] == ["原文。"]
    assert rows[0]["chapter"] == "第一章 总则"
    assert rows[1]["chapter"] == "第二章 营销"


def test_web_footer_is_not_law_but_exception_is_retained():
    rows = parse_units(
        [
            (
                "第一条 主体义务。\n政府部门为公共利益要求的除外。\n"
                "中国人民银行有关负责人就《金融产品网络营销管理办法》答记者问\n"
                "https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=1\n"
                "手机扫一扫打开此页"
            )
        ],
        pdf=True,
    )
    assert rows[0]["parts"] == ["主体义务。", "政府部门为公共利益要求的除外。"]


@pytest.mark.parametrize("text", ["第一条 A\n第三条 C", "第一条 A\n第一条 B", "第二条 B\n第一条 A"])
def test_numbering_gaps_duplicates_and_reordering_are_rejected(text):
    with pytest.raises(ValueError, match="numbering"):
        parse_units([text])


@pytest.mark.parametrize(
    "label,number", [("第十条", 10), ("第二十五条", 25), ("第一百零一条", 101)]
)
def test_real_number_is_taken_from_label(label, number):
    assert article_number(label) == number


@pytest.fixture
def candidate(tmp_path):
    """Copy the current corpus only; corruption never touches project artifacts."""
    import shutil

    root = Path(__file__).resolve().parents[2]
    for folder in ("data/corpus", "data/sources", "data/extracted", "法律法规"):
        shutil.copytree(root / folder, tmp_path / folder)
    manifest_path = tmp_path / "data/corpus/official-v1-2026-10-11/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publication_status"] = "candidate"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, "official-v1-2026-10-11"


def mutate(root, ruleset, filename, transform, *, rehash=False):
    output = root / "data/corpus" / ruleset
    path = output / filename
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    transform(rows)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    if rehash:
        snapshot_manifest(root, output, ruleset)


def test_missing_rule_reference_is_rejected_even_after_manifest_rehash(candidate):
    root, ruleset = candidate
    mutate(
        root,
        ruleset,
        "rule_cards.jsonl",
        lambda rows: rows[0]["article_ids"].append("invented::art_999"),
        rehash=True,
    )
    codes = {i["code"] for i in validate_corpus(root, ruleset)["issues"]}
    assert "invalid_rule_reference" in codes


def test_content_damage_is_detected_by_manifest_and_text_hash(candidate):
    root, ruleset = candidate
    mutate(root, ruleset, "articles.jsonl", lambda rows: rows[0].update(original_text="DAMAGED"))
    codes = {i["code"] for i in validate_corpus(root, ruleset)["issues"]}
    assert "artifact_hash_mismatch" in codes
    assert "article_hash_mismatch" in codes


def test_unreviewed_source_does_not_become_release_ready(candidate):
    root, ruleset = candidate
    mutate(
        root,
        ruleset,
        "documents.jsonl",
        lambda rows: rows[0].update(legal_text_verified=False),
        rehash=True,
    )
    result = validate_corpus(root, ruleset)
    assert not result["release_ready"]
    assert "unreviewed_document" in {i["code"] for i in result["issues"]}


def test_draft_in_official_ruleset_is_rejected(candidate):
    root, ruleset = candidate
    mutate(
        root,
        ruleset,
        "documents.jsonl",
        lambda rows: rows[0].update(document_status="draft"),
        rehash=True,
    )
    result = validate_corpus(root, ruleset)
    assert "version_mixed" in {i["code"] for i in result["issues"]}


def test_changed_rule_cannot_bypass_review_with_verified_flag_and_rehash(candidate):
    root, ruleset = candidate
    mutate(
        root,
        ruleset,
        "rule_cards.jsonl",
        lambda rows: rows[0].update(
            prohibited_or_required_behavior="Invented prohibition", verified=True
        ),
        rehash=True,
    )
    assert "review_rule_changed" in {i["code"] for i in validate_corpus(root, ruleset)["issues"]}


def test_missing_article_ledger_is_rejected(candidate):
    root, ruleset = candidate
    mutate(root, ruleset, "article-review-ledger.jsonl", lambda rows: rows.pop(), rehash=True)
    assert "ledger_coverage" in {i["code"] for i in validate_corpus(root, ruleset)["issues"]}


def test_source_snapshot_damage_is_rejected(candidate):
    root, ruleset = candidate
    output = root / "data/corpus" / ruleset
    doc = json.loads((output / "documents.jsonl").read_text(encoding="utf-8").splitlines()[0])
    (root / doc["snapshot_source_path"]).write_bytes(b"damaged")
    assert "source_hash_mismatch" in {i["code"] for i in validate_corpus(root, ruleset)["issues"]}


def test_publication_is_immutable_and_idempotent(candidate):
    from insurance_audit.corpus.ingest import build_candidate
    from insurance_audit.corpus.review import publish_snapshot

    root, ruleset = candidate
    first = publish_snapshot(root, ruleset)
    assert first["publication_status"] == "published"
    assert publish_snapshot(root, ruleset) == first
    with pytest.raises(ValueError, match="cannot be overwritten"):
        build_candidate(root, root / "data/extracted/official-source-manifest.json", ruleset)
    with pytest.raises(ValueError, match="immutable"):
        snapshot_manifest(root, root / "data/corpus" / ruleset, ruleset)


def test_invalid_manifest_artifacts_returns_failure(candidate):
    root, ruleset = candidate
    path = root / "data/corpus" / ruleset / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["artifacts"] = None
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert not validate_corpus(root, ruleset)["structural_valid"]


def test_manifest_source_hash_must_match_document(candidate):
    root, ruleset = candidate
    path = root / "data/corpus" / ruleset / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["sources"][0]["source_sha256"] = "invented"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "manifest_source_mismatch" in {
        i["code"] for i in validate_corpus(root, ruleset)["issues"]
    }
