import json
from argparse import Namespace
from pathlib import Path

import pytest

from insurance_audit.evaluation.metrics import metrics
from insurance_audit.evaluation.runner import load_samples, run


def row(truth, decision, status="completed", gold=None, predicted=False):
    return {
        "sample": {
            "expected_decision": truth,
            "label_status": "provisional",
            "expected_categories": gold,
            "expected_article_ids": gold,
        },
        "response": {
            "status": status,
            "decision": decision,
            "violations": [
                {"type": "x", "citations": [{"article_id": "x", "original_text": "原文"}]}
            ]
            if predicted
            else [],
            "meta": {"latency_ms": 10},
            "errors": [],
        },
    }


def test_partial_and_failure_stay_in_denominators():
    rows = [
        row("non_compliant", "non_compliant", "partial", predicted=True),
        row("non_compliant", "needs_review"),
        row("compliant", None, "failed"),
        row("compliant", "compliant"),
    ]
    m = metrics(rows)
    assert m["automatic_coverage"]["value"] == 0.25
    assert m["automatic_accuracy"]["value"] == 1
    assert m["technical_failure_rate_including_partial"]["value"] == 0.5
    assert m["violation_recall"]["value"] == 0
    assert m["valid_violation_detection_recall_including_partial"]["value"] == 0.5
    assert sum(sum(r.values()) for r in m["confusion_matrix"].values()) == 4


def test_null_labels_not_empty_gold_and_original_match():
    m = metrics([row("non_compliant", "non_compliant", gold=None, predicted=True)])
    assert m["type_micro_f1"]["value"] is None
    assert m["article_precision"]["value"] is None
    m = metrics(
        [row("non_compliant", "non_compliant", gold=["x"], predicted=True)],
        {"x": {"original_text": "原文"}},
    )
    assert m["type_micro_f1"]["value"] == 1
    assert m["article_recall"]["value"] == 1
    assert m["citation_original_match"]["value"] == 1
    m = metrics([row("compliant", "non_compliant", gold=[], predicted=True)], {})
    assert m["article_precision"]["value"] == 0
    assert m["unknown_articles"] == 1
    assert m["citation_original_match"]["value"] == 0


def test_zero_denominators_and_manual_macro_f1():
    assert metrics([])["automatic_accuracy"]["value"] is None
    assert metrics([])["macro_f1"] is None
    m = metrics(
        [
            row("compliant", "compliant"),
            row("compliant", "needs_review"),
            row("needs_review", "needs_review"),
            row("non_compliant", "non_compliant"),
        ]
    )
    assert m["macro_f1"] == pytest.approx(7 / 9)


def test_split_leakage_rejected(tmp_path):
    sample = {
        "sample_id": "1",
        "group_id": "same",
        "split": "dev",
        "text": "a",
        "expected_decision": "needs_review",
        "annotation_reason": "draft",
        "provenance": "test",
    }
    (tmp_path / "dev.jsonl").write_text(json.dumps(sample), encoding="utf-8")
    (tmp_path / "test.jsonl").write_text(
        json.dumps(dict(sample, split="test", sample_id="2", text="b")), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="group leakage"):
        load_samples(tmp_path / "dev.jsonl", "dev")


@pytest.mark.asyncio
async def test_historical_replay_preserves_real_metadata_without_provider(tmp_path, monkeypatch):
    from insurance_audit.models.bailian import Bailian

    def forbidden(*args, **kwargs):
        raise AssertionError("Replay must not create API provider")

    monkeypatch.setattr(Bailian, "__init__", forbidden)
    args = Namespace(
        samples=Path("data/eval/dev.jsonl"),
        split="dev",
        variant="hybrid",
        out=tmp_path / "replay",
        replay=Path("reports/g1-live-acceptance-v1.5.json"),
        mock=False,
    )
    result = await run(args)
    assert result["metrics"]["samples"] == 5
    assert result["metrics"]["automatic_coverage"]["value"] == 0.6
    assert result["metadata"]["run_complete"]
    with pytest.raises(ValueError, match="empty output"):
        await run(args)
