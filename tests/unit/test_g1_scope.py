import asyncio
import json
from types import SimpleNamespace

import pytest

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian, Budget, ModelFailure
from insurance_audit.models.mock import MockProvider
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import AuditContext, AuditRequest, Condition, Finding, JudgeOutput
from insurance_audit.service import AuditService
from insurance_audit.workflow import resolve_condition_ids, text_sources, verify


@pytest.fixture(scope="module")
def corpus():
    return Corpus(Settings(_env_file=None, audit_mock=True))


def finding_for(card, values, applicability="applicable", finding="no_violation"):
    return Finding(
        rule_id=card["rule_id"],
        applicability=applicability,
        finding=finding,
        reason="测试触发条件与活动范围。",
        condition_results=[
            Condition(condition=c, met=v, evidence_ids=[])
            for c, v in zip(card["trigger_conditions"], values)
        ],
        evidence=[],
        article_ids=[],
        missing_facts=[],
    )


@pytest.mark.parametrize(
    "applicability", ["applicable", "needs_context", "external_verification_required"]
)
def test_false_necessary_condition_is_not_unknown(corpus, applicability):
    card = dict(corpus.rules["marketing_truthful_and_not_misleading"])
    card["trigger_conditions"] = ["activity is present", "subject condition"]
    f = finding_for(card, [False, None], applicability, "uncertain")
    row, review, violation = verify(f, card, [], corpus, AuditRequest(), True)
    assert row.status == "not_applicable" and row.finding == "no_violation"
    assert review is None and violation is None


def test_unknown_conditions_and_contradictory_violation_do_not_pass(corpus):
    card = corpus.rules["marketing_truthful_and_not_misleading"]
    for met, finding in [(None, "no_violation"), (False, "violation")]:
        f = finding_for(card, [met], finding=finding)
        row, review, violation = verify(f, card, [], corpus, AuditRequest(), True)
        assert row.status == "needs_context" and review.blocking and violation is None


def test_external_license_cannot_be_invented_and_out_of_scope_does_not_block(corpus):
    card = corpus.rules["licensed_insurance_and_marketing_subject"]
    f = finding_for(card, [True], finding="violation")
    row, review, violation = verify(f, card, [], corpus, AuditRequest(), True)
    assert row.status == "external_verification_required" and review.blocking and violation is None
    internal_card = {**card, "checkability": "out_of_scope"}
    f.applicability, f.finding = "out_of_scope", "uncertain"
    row, review, violation = verify(f, internal_card, [], corpus, AuditRequest(), True)
    assert row.status == "out_of_scope" and review is None and violation is None


def test_missing_disclosure_requires_complete_readable_material(corpus):
    card = corpus.rules["identify_insurance_product_and_provider"]
    f = finding_for(card, [True], finding="violation")
    f.article_ids = card["article_ids"][:1]
    f.absence_disclosure = "承保机构名称"
    sources = text_sources("某保险产品介绍")
    for completeness, readable, expected in [
        ("complete", True, True),
        ("partial", True, False),
        ("unknown", True, False),
        ("complete", False, False),
    ]:
        req = AuditRequest(
            text=sources[0].text, context=AuditContext(material_completeness=completeness)
        )
        _row, _review, violation = verify(f, card, sources, corpus, req, readable)
        assert (violation is not None) == expected


@pytest.mark.asyncio
async def test_missing_or_duplicate_rules_fail_even_when_all_other_rules_pass(corpus):
    cards, articles = next(corpus.batches(6))
    from insurance_audit.workflow import judge_messages

    sources = text_sources("完整教育材料")
    req = AuditRequest(text=sources[0].text, context=AuditContext(material_completeness="complete"))
    raw = await MockProvider().call(
        "text", judge_messages(req, sources, cards, articles, True, []), Budget()
    )
    result = JudgeOutput.model_validate_json(raw)
    result.findings.pop()
    with pytest.raises(ValueError, match="Missing"):
        resolve_condition_ids(result, cards, sources)
    result.findings.append(result.findings[0])
    with pytest.raises(ValueError, match="duplicate"):
        resolve_condition_ids(result, cards, sources)


@pytest.mark.asyncio
async def test_text_batch_timeout_retains_valid_violation_and_otherwise_fails(corpus):
    class FailedBatch(MockProvider):
        async def call(self, kind, messages, budget, **kwargs):
            cards = json.loads(messages[1]["content"])["rules"]
            if any(c["rule_id"] == "marketing_message_optout" for c in cards):
                raise ModelFailure("budget_exhausted", "模拟批次超时")
            return await super().call(kind, messages, budget, **kwargs)

    service = AuditService(corpus.settings, corpus, FailedBatch())
    for text, expected in [("监管部门担保收益", "partial"), ("普通文字", "failed")]:
        result = await service.review(
            AuditRequest(
                text=text,
                depth="strict",
                context=AuditContext(material_completeness="complete"),
            )
        )
        assert result.status == expected
        assert len(result.coverage.rules) == len(corpus.rules)
        assert any(r.status == "failed" for r in result.coverage.rules)


@pytest.mark.asyncio
async def test_all_nonapplicable_ratios_are_null(corpus):
    result = await AuditService(corpus.settings, corpus, MockProvider()).review(
        AuditRequest(
            text="不含模拟违规词的完整材料",
            depth="strict",
            context=AuditContext(material_completeness="complete"),
        )
    )
    assert result.decision == "compliant" and result.coverage.eligible == 0
    assert result.coverage.coverage_ratio is None and result.coverage.resolved_ratio is None


@pytest.mark.asyncio
async def test_single_call_deadline_is_enforced_without_exhausting_total_budget():
    async def slow(**kwargs):
        await asyncio.sleep(10)

    provider = Bailian(
        Settings(_env_file=None, audit_mock=True, model_timeout_seconds=0.01, model_max_retries=0),
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=slow))),
    )
    budget = Budget(seconds=2)
    with pytest.raises(ModelFailure) as error:
        await provider.call("text", [], budget)
    assert error.value.code == "model_unavailable"
    assert budget.attempts == 1 and budget.remaining() > 1
