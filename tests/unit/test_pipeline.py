import json

import pytest

from insurance_audit.corpus import pipeline as flow
from insurance_audit.corpus.ingest import sha256, write_jsonl
from insurance_audit.corpus.review import semantic_digest


@pytest.fixture
def root(tmp_path):
    (tmp_path / "法律法规").mkdir()
    flow.save(tmp_path / "data/sources/catalog.json", {"sources": []})
    return tmp_path


def drop(root, name="测试法规.txt", text="第一条 不得作虚假宣传。\n第二条 本规定即日起施行。"):
    path = root / "法律法规" / name
    path.write_text(text, encoding="utf-8")
    return path


def state(root):
    return flow.read(root / flow.REGISTRY)["pipeline"]


def run(root, **kwargs):
    return flow.run_once(root, settle_seconds=0, **kwargs)


def test_discovery_waits_for_stability_and_repeated_scan_is_idempotent(root):
    drop(root)
    flow.run_once(root, settle_seconds=5)
    assert not state(root)["versions"]
    run(root)
    first = state(root)
    assert len(first["versions"]) == len(first["candidates"]) == 1
    candidate = next(iter(first["candidates"]))
    manifest = root / "data/corpus" / candidate / "manifest.json"
    digest = sha256(manifest)
    run(root)
    assert sha256(manifest) == digest
    assert state(root)["versions"] == first["versions"]


def test_same_bytes_different_name_are_processed_once(root):
    drop(root)
    drop(root, "重复.txt")
    run(root)
    assert len(state(root)["versions"]) == 1


def test_new_bytes_preserve_old_version_and_old_snapshot(root):
    path = drop(root)
    run(root)
    first = next(iter(state(root)["versions"].values()))
    snapshot = root / first["artifact_dir"] / "source.txt"
    digest = sha256(snapshot)
    path.write_text("第一条 不得隐瞒风险。", encoding="utf-8")
    run(root)
    assert len(state(root)["versions"]) == 2
    assert sha256(snapshot) == digest


def test_failure_is_isolated_and_not_retried_on_every_poll(root):
    drop(root, "坏文件.txt", "第一条 A\n第三条 C")
    drop(root)
    run(root)
    versions = state(root)["versions"]
    assert {v["status"] for v in versions.values()} == {"failed", "needs_review"}
    run(root)
    assert versions == state(root)["versions"]


def test_user_deferred_source_is_not_processed_even_when_changed(root):
    path = drop(root)
    flow.save(
        root / "data/sources/catalog.json",
        {
            "sources": [
                {
                    "document_id": "deferred",
                    "title": "Deferred test source",
                    "source_path": path.relative_to(root).as_posix(),
                    "workflow_status": "extraction_deferred_by_user",
                    "source_sha256": "old",
                }
            ]
        },
    )
    run(root)
    assert not state(root)["versions"]


def test_deleted_source_does_not_delete_history(root):
    path = drop(root)
    run(root)
    path.unlink()
    run(root)
    assert state(root)["versions"]
    assert not next(iter(state(root)["observations"].values()))["present"]


def test_unreviewed_file_cannot_publish_or_seal(root):
    drop(root)
    run(root)
    ruleset = next(iter(state(root)["candidates"]))
    with pytest.raises(ValueError, match="attributable"):
        flow.seal_review(root, ruleset)
    directory = root / "data/corpus" / ruleset
    flow.save(
        directory / "review-approval.json",
        {
            "approved": True,
            "ruleset_id": ruleset,
            "manifest_sha256": sha256(directory / "manifest.json"),
        },
    )
    run(root)
    assert state(root)["candidates"][ruleset]["status"] == "review_blocked"


def prepare_review(root):
    """Synthetic test review only: proves the gate protocol, not legal accuracy."""
    ruleset = next(iter(state(root)["candidates"]))
    directory = root / "data/corpus" / ruleset
    doc = json.loads((directory / "documents.jsonl").read_text(encoding="utf-8"))
    doc.update(document_status="effective", effective_on="2020-01-01", source_type="test")
    write_jsonl(directory / "documents.jsonl", [doc])
    evidence = flow.read(directory / "review-template.json")
    aids = list(evidence["articles"])
    card = {
        "rule_id": "fixture_rule",
        "article_ids": [aids[0]],
        "category": "test",
        "ruleset_id": ruleset,
        "verified": False,
        "checkability": "content_checkable",
        "coverage_group": "test",
        "interpretation_note": "test fixture",
        "prohibited_or_required_behavior": "false advertising prohibited",
    }
    for key in (
        "subject_scope",
        "channel_scope",
        "product_scope",
        "trigger_conditions",
        "exceptions",
        "required_facts",
    ):
        card[key] = ["test"]
    write_jsonl(directory / "rule_cards.jsonl", [card])
    evidence.update(
        reviewer={"type": "implementation_agent", "id": "test-fixture"},
        method="Synthetic fixture review for automated protocol test",
    )
    for aid, record in evidence["articles"].items():
        record["scope"].update(
            classification_status="reviewed",
            verified=True,
            checkability="content_checkable" if aid == aids[0] else "out_of_scope",
            rule_ids=["fixture_rule"] if aid == aids[0] else [],
            exclusion_reason="test",
        )
    evidence["rules"] = {"fixture_rule": {"digest": semantic_digest(card)}}
    flow.save(directory / "review.json", evidence)
    return ruleset


def test_reviewed_candidate_resumes_and_publishes_automatically(root):
    drop(root)
    run(root)
    ruleset = prepare_review(root)
    flow.seal_review(root, ruleset)
    run(root)
    assert state(root)["candidates"][ruleset]["status"] == "published"
    assert state(root)["base_ruleset"] == ruleset
    run(root)
    assert len(state(root)["candidates"]) == 1


def test_post_approval_modification_blocks_publication(root):
    drop(root)
    run(root)
    ruleset = prepare_review(root)
    flow.seal_review(root, ruleset)
    path = root / "data/corpus" / ruleset / "manifest.json"
    manifest = flow.read(path)
    manifest["scope"] = "modified after approval"
    flow.save(path, manifest)
    run(root)
    assert state(root)["candidates"][ruleset]["status"] == "review_blocked"


def test_second_generation_carries_published_base(root):
    drop(root)
    run(root)
    ruleset = prepare_review(root)
    flow.seal_review(root, ruleset)
    run(root)
    drop(root, "新增.txt", "第一条 新义务。")
    run(root)
    new = next(k for k in state(root)["candidates"] if k != ruleset)
    docs = (root / "data/corpus" / new / "documents.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(docs) == 2
    assert state(root)["candidates"][new]["base_ruleset"] == ruleset


def test_failed_version_retries_only_on_request(root, monkeypatch):
    path = drop(root)
    actual = flow.extract
    attempts = []

    def unavailable(*args):
        attempts.append(1)
        raise OSError("temporary extractor failure")

    monkeypatch.setattr(flow, "extract", unavailable)
    run(root)
    run(root)
    assert len(attempts) == 1
    monkeypatch.setattr(flow, "extract", actual)
    run(root, retry=True)
    assert state(root)["versions"][sha256(path)]["status"] == "needs_review"


def test_docx_extractor_reads_paragraphs(root):
    import zipfile

    path = root / "法律法规/测试.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第一条 测试原文。</w:t></w:r></w:p></w:body></w:document>',
        )
    run(root)
    version = next(iter(state(root)["versions"].values()))
    assert version["article_count"] == 1
    assert "DOCX" in version["tool"]["tool"]


def test_pdf_pipeline_uses_real_local_source(root):
    import shutil
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "法律法规/金融产品网络营销管理办法.pdf"
    shutil.copyfile(source, root / "法律法规/正式文本.pdf")
    run(root)
    version = next(iter(state(root)["versions"].values()))
    assert version["article_count"] == 39
    assert version["tool"]["tool_version"]
    assert version["status"] == "needs_review"


def test_future_effective_date_is_not_published(root):
    drop(root)
    run(root)
    ruleset = prepare_review(root)
    path = root / "data/corpus" / ruleset / "documents.jsonl"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["effective_on"] = "2999-01-01"
    write_jsonl(path, [doc])
    with pytest.raises(ValueError, match="Review incomplete"):
        flow.seal_review(root, ruleset)
