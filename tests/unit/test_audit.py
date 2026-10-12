import asyncio
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError
from PIL import Image

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian, Budget, ModelFailure, structured
from insurance_audit.models.mock import MockProvider
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import (
    AuditContext,
    AuditRequest,
    JudgeOutput,
    ReviewItem,
    VisionOutput,
)
from insurance_audit.service import AuditService, aggregate
from insurance_audit.uploads import InputError, validate_image
from insurance_audit.workflow import (
    JUDGE_RULE_FIELDS,
    citation_repair_context,
    judge_messages,
    resolve_condition_ids,
    text_sources,
    validate_findings,
    verify,
)


@pytest.fixture(scope="module")
def settings():
    return Settings(_env_file=None, audit_mock=True)


@pytest.fixture(scope="module")
def corpus(settings):
    return Corpus(settings)


def png(size=(16, 16)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "violations,reviews,errors,expected",
    [
        ([1], [], [], ("completed", "non_compliant", "no")),
        (
            [],
            [ReviewItem(type="context", reason="unknown")],
            [],
            ("completed", "needs_review", None),
        ),
        ([], [], [], ("completed", "compliant", "yes")),
        ([1], [], [1], ("partial", "non_compliant", "no")),
        ([], [], [1], ("failed", None, None)),
    ],
)
def test_aggregation(violations, reviews, errors, expected):
    assert aggregate(violations, reviews, errors) == expected


def test_image_validation_does_not_trust_mime_and_rejects_corruption():
    with pytest.raises(InputError):
        validate_image(png(), "image_1", "image/jpeg")
    with pytest.raises(InputError):
        validate_image(b"not-an-image", "image_1", "image/png")
    with pytest.raises(InputError) as error:
        validate_image(png((5000, 4001)), "image_1", "image/png")
    assert error.value.status == 413


@pytest.mark.asyncio
async def test_all_rules_covered_and_unicode_offsets_verified(settings, corpus):
    text = "🙂\n监管部门担保收益"
    result = await AuditService(settings, corpus, MockProvider()).review(
        AuditRequest(
            text=text, context=AuditContext(channel="internet", material_completeness="complete")
        )
    )
    assert result.decision == "non_compliant"
    assert len(result.coverage.rules) == len(corpus.rules)
    e = result.violations[0].evidence[0]
    assert text[e.start : e.end] == e.quote
    assert e.start == 2  # Unicode code points, not UTF-16 code units.
    assert (
        result.violations[0].citations[0].original_text
        == corpus.articles[result.violations[0].citations[0].article_id]["original_text"]
    )


@pytest.mark.asyncio
async def test_failed_image_does_not_become_text_only_compliant(settings, corpus):
    class FailedVision(MockProvider):
        async def call(self, kind, *args, **kwargs):
            if kind == "vision":
                raise ModelFailure("model_unavailable", "test")
            return await super().call(kind, *args, **kwargs)

    req = AuditRequest(text="教育材料", context=AuditContext(material_completeness="complete"))
    result = await AuditService(settings, corpus, FailedVision()).review(
        req, [validate_image(png(), "image_1")]
    )
    assert result.status == "failed" and result.decision is None
    req.text = "监管部门担保收益"
    result = await AuditService(settings, corpus, FailedVision()).review(
        req, [validate_image(png(), "image_1")]
    )
    assert result.status == "partial" and result.decision == "non_compliant"


@pytest.mark.asyncio
async def test_unreadable_image_is_business_review_not_technical_error(settings, corpus):
    req = AuditRequest(text="教育材料", context=AuditContext(material_completeness="complete"))
    result = await AuditService(settings, corpus, MockProvider()).review(
        req, [validate_image(png(), "image_1")]
    )
    assert result.status == "completed" and result.decision == "needs_review"
    assert not result.errors


@pytest.mark.asyncio
async def test_five_image_order_and_supplementary_text(settings, corpus):
    class Vision(MockProvider):
        async def call(self, kind, messages, budget, **kwargs):
            if kind == "vision":
                budget.consume()
                marker = messages[1]["content"][0]["text"]
                await asyncio.sleep(0.001 if "image_5" in marker else 0.005)
                return json.dumps(
                    {
                        "text_blocks": [{"text": marker}],
                        "visual_observations": [],
                        "unreadable_regions": [],
                        "extraction_warnings": [],
                    }
                )
            return await super().call(kind, messages, budget, **kwargs)

    images = [validate_image(png(), f"image_{i}") for i in range(1, 6)]
    result = await AuditService(settings, corpus, Vision()).review(
        AuditRequest(text="补充文字"), images
    )
    assert [i.image_id for i in result.images] == [f"image_{i}" for i in range(1, 6)]
    assert len([s for s in result.sources if s.source_type == "image_text"]) == 5


@pytest.mark.asyncio
async def test_invalid_json_only_repaired_once():
    class Invalid:
        async def call(self, kind, messages, budget, **kwargs):
            budget.consume()
            return "not json"

    budget = Budget()
    with pytest.raises(ModelFailure, match="一次修复"):
        await structured(Invalid(), "vision", [], VisionOutput, budget)
    assert budget.attempts == 2


@pytest.mark.asyncio
async def test_fabricated_citation_and_evidence_are_rejected(settings, corpus):
    cards = [corpus.rules["no_regulatory_guarantee_or_filing_endorsement"]]
    sources = text_sources("监管部门担保收益")
    request = AuditRequest(text=sources[0].text)
    messages = judge_messages(request, sources, cards, {}, True, [])
    output = JudgeOutput.model_validate_json(await MockProvider().call("text", messages, Budget()))
    output.findings[0].article_ids = ["fake::article"]
    with pytest.raises(ValueError, match="Citation"):
        validate_findings(output, cards, sources)
    output.findings[0].article_ids = cards[0]["article_ids"][:1]
    output.findings[0].evidence[0].quote = "伪造的证据"
    with pytest.raises(ValueError, match="Evidence"):
        validate_findings(output, cards, sources)


@pytest.mark.asyncio
async def test_partial_material_cannot_prove_missing_disclosure(settings, corpus):
    card = corpus.rules["no_regulatory_guarantee_or_filing_endorsement"]
    sources = text_sources("监管部门担保收益")
    request = AuditRequest(text=sources[0].text)
    messages = judge_messages(request, sources, [card], {}, True, [])
    output = JudgeOutput.model_validate_json(await MockProvider().call("text", messages, Budget()))
    finding = output.findings[0]
    finding.absence_disclosure = "缺失披露"
    row, review, violation = verify(finding, card, sources, corpus, request, True)
    assert row.status == "needs_context" and review and violation is None


def test_retrieval_uses_tail_and_batch_union_is_complete(corpus):
    sources = text_sources("普通文字" * 150 + "\n互联网保险业务监管办法 风险提示 分红")
    assert corpus.retrieve(sources)
    batches = list(corpus.batches(6))
    assert {c["rule_id"] for cards, _ in batches for c in cards} == set(corpus.rules)
    for cards, articles in batches:
        for card in cards:
            assert set(card["article_ids"] + card["supporting_article_ids"]) <= set(articles)


def test_compact_prompt_preserves_full_articles_and_rule_conditions(corpus):
    request = AuditRequest(text="保险知识科普")
    for cards, articles in corpus.batches(6):
        payload = json.loads(
            judge_messages(request, text_sources(request.text), cards, articles, True, [])[1][
                "content"
            ]
        )
        assert payload["rules"] == [{k: c[k] for k in JUDGE_RULE_FIELDS if k in c} for c in cards]
        # Citable articles carry their full text under rule_articles...
        supplied = {
            a["article_id"]: a for group in payload["rule_articles"] for a in group["articles"]
        }
        for card in cards:
            for aid in card["article_ids"]:
                assert supplied[aid]["original_text"] == articles[aid]["original_text"]
                assert "normalized_text" not in supplied[aid]
                assert "text_sha256" not in supplied[aid]
        # ...and `articles` holds only the remaining context, so nothing repeats.
        assert {a["article_id"] for a in payload["articles"]}.isdisjoint(supplied)
        for article in payload["articles"]:
            assert article["original_text"] == articles[article["article_id"]]["original_text"]
            assert "normalized_text" not in article
            assert "text_sha256" not in article


def test_prompt_lists_per_rule_citation_allowlist_and_trigger_guidance(corpus):
    request = AuditRequest(text="保险知识科普")
    sources = text_sources(request.text)
    for cards, articles in corpus.batches(6):
        payload = json.loads(
            judge_messages(request, sources, cards, articles, True, [])[1]["content"]
        )
        assert set(payload["allowed_citations"]) == {c["rule_id"] for c in cards}
        for card in cards:
            assert payload["allowed_citations"][card["rule_id"]] == {
                aid: articles[aid]["article_label"] for aid in card["article_ids"]
            }
        supplied = {
            a["article_id"]: a for group in payload["rule_articles"] for a in group["articles"]
        }
        for card in cards:
            for aid in card["article_ids"]:
                assert card["rule_id"] in [
                    g["rule_id"] for g in payload["rule_articles"] if aid in g["article_ids"]
                ]
        for aid in articles:
            if aid in supplied:
                continue
            assert supplied.get(aid) is None
    payload = json.loads(
        judge_messages(
            AuditRequest(text="教育问答"),
            text_sources("教育问答"),
            list(corpus.rules.values()),
            corpus.articles,
            True,
            [],
        )[1]["content"]
    )
    assert set(payload["trigger_guidance"]) == {
        "approved_marketing_content_use",
        "internet_platform_operating_conditions",
    }
    assert all(guidance for guidance in payload["trigger_guidance"].values())


@pytest.mark.asyncio
async def test_repair_attempt_receives_per_rule_citation_allowlist(corpus):
    class CiteWrongThenRight:
        def __init__(self):
            self.calls = []

        async def call(self, kind, messages, budget, **kwargs):
            budget.consume()
            self.calls.append(messages)
            payload = json.loads(messages[1]["content"])
            cards = payload["rules"]
            bad = len(self.calls) == 1
            findings = []
            for card in cards:
                findings.append(
                    {
                        "rule_id": card["rule_id"],
                        "applicability": "not_applicable",
                        "finding": "no_violation",
                        "reason": "测试逐规则引用白名单。",
                        "condition_results": [
                            {"condition": cond, "met": False, "evidence_ids": []}
                            for cond in card["trigger_conditions"]
                        ],
                        "evidence": [],
                        "article_ids": ["wrong::article"] if bad else [],
                        "absence_disclosure": None,
                        "missing_facts": [],
                        "model_confidence": None,
                    }
                )
            return json.dumps({"findings": findings}, ensure_ascii=False)

    cards, articles = next(corpus.batches(6))
    sources = text_sources("中性教育材料")
    messages = judge_messages(
        AuditRequest(text=sources[0].text), sources, cards, articles, True, []
    )
    provider = CiteWrongThenRight()
    value = await structured(
        provider,
        "text",
        messages,
        JudgeOutput,
        Budget(),
        validate=lambda v: resolve_condition_ids(v, cards, sources),
        repair_context=citation_repair_context(cards, articles),
    )
    assert len(provider.calls) == 2
    repair = provider.calls[1][-1]["content"]
    assert "wrong::article" not in repair
    for card in cards:
        assert card["rule_id"] in repair
        for aid in card["article_ids"]:
            assert aid in repair
    assert value.findings and all(not f.article_ids for f in value.findings)


class Client:
    def __init__(self, create):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    async def close(self):
        pass


def response():
    return SimpleNamespace(
        usage=None,
        model="actual-test-model",
        choices=[
            SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"ok":true}'))
        ],
    )


@pytest.mark.asyncio
async def test_process_concurrency_and_cancel_release_slots():
    active = peak = 0

    async def create(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.02)
            return response()
        finally:
            active -= 1

    settings = Settings(_env_file=None, audit_mock=True)
    provider = Bailian(settings, Client(create))
    # Launch more calls than the cap so the semaphore is actually saturated.
    calls = settings.model_concurrency + 3
    await asyncio.gather(*(provider.call("text", [], Budget()) for _ in range(calls)))
    # The cap is the configured concurrency, not a hardcoded number, and every
    # slot must be released once the calls finish.
    assert peak == settings.model_concurrency and active == 0
    task = asyncio.create_task(provider.call("text", [], Budget()))
    await asyncio.sleep(0.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0


@pytest.mark.asyncio
async def test_auth_error_never_retries_and_retry_after_obeys_budget():
    calls = 0
    status = 401

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        r = httpx.Response(
            status,
            request=httpx.Request("POST", "https://example.invalid"),
            headers={"Retry-After": "10"},
        )
        raise APIStatusError("SECRET never leak", response=r, body={})

    provider = Bailian(Settings(_env_file=None, audit_mock=True), Client(create))
    with pytest.raises(ModelFailure) as error:
        await provider.call("text", [], Budget())
    assert calls == 1 and "SECRET" not in str(error.value)
    status = 429
    with pytest.raises(ModelFailure) as error:
        await provider.call("text", [], Budget(seconds=1))
    assert error.value.code == "budget_exhausted" and calls == 2


@pytest.mark.asyncio
async def test_queue_wait_counts_toward_overall_deadline():
    async def create(**kwargs):
        return response()

    provider = Bailian(
        Settings(_env_file=None, audit_mock=True, model_concurrency=1), Client(create)
    )
    await provider.gate.acquire()
    budget = Budget(seconds=0.01)
    try:
        with pytest.raises(ModelFailure) as error:
            await provider.call("text", [], budget)
        assert error.value.code == "budget_exhausted" and budget.attempts == 0
    finally:
        provider.gate.release()


@pytest.mark.asyncio
async def test_text_thinking_override_does_not_change_vision_calls():
    requests = []

    async def create(**kwargs):
        requests.append(kwargs)
        return response()

    provider = Bailian(
        Settings(_env_file=None, audit_mock=True, bailian_text_enable_thinking=False),
        Client(create),
    )
    budget = Budget()
    await provider.call("text", [], budget)
    await provider.call("vision", [], budget)
    assert requests[0]["extra_body"] == {"enable_thinking": False}
    assert "extra_body" not in requests[1]
    assert budget.calls[0]["enable_thinking"] is False
    assert all(c["actual_model"] == "actual-test-model" for c in budget.calls)

    provider.settings.bailian_text_enable_thinking = None
    await provider.call("text", [], Budget())
    assert "extra_body" not in requests[2]


@pytest.mark.asyncio
async def test_attempt_limit_does_not_drop_unchecked_rules(corpus):
    settings = Settings(_env_file=None, audit_mock=True, audit_max_model_attempts=1)
    result = await AuditService(settings, corpus, MockProvider()).review(AuditRequest(text="测试"))
    assert result.status == "failed"
    assert result.coverage.total == len(corpus.rules)
    assert any(r.status == "failed" for r in result.coverage.rules)
