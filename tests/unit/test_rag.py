import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian, Budget, ModelFailure
from insurance_audit.models.mock import MockProvider
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import AuditRequest, JudgeOutput
from insurance_audit.service import AuditService
from insurance_audit.vector_index import build_index, load_index, normalize
from insurance_audit.workflow import judge_messages, resolve_condition_ids, text_sources


@pytest.fixture
def corpus():
    return Corpus(Settings(_env_file=None))


@pytest.mark.asyncio
async def test_index_build_reuse_and_tamper_rejection(corpus, tmp_path):
    settings = Settings(_env_file=None, project_root=tmp_path, embedding_dimensions=2)

    class Embeddings:
        calls = 0

        async def embed(self, texts, budget):
            self.calls += 1
            budget.consume()
            return [[1, 2] for _ in texts]

    provider = Embeddings()
    report = await build_index(corpus, settings, provider)
    expected_calls = -(-len(corpus.ids) // 10)
    assert provider.calls == expected_calls and report["article_count"] == len(corpus.ids)
    assert (await build_index(corpus, settings, provider))["status"] == "reused"
    assert provider.calls == expected_calls
    from pathlib import Path

    path = Path(report["path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["vectors"][0][0] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="哈希"):
        load_index(corpus, settings)
    settings.embedding_dimensions = 3
    with pytest.raises(FileNotFoundError):
        load_index(corpus, settings)


@pytest.mark.parametrize("vector", [[0, 0], [1], [float("nan"), 0], [True, 1]])
def test_invalid_vectors_rejected(vector):
    with pytest.raises(ValueError):
        normalize(vector, 2)


def test_non_ascii_api_key_is_not_considered_configured():
    settings = Settings(
        _env_file=None,
        dashscope_api_key="你的key",
        bailian_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    assert settings.configured is False


@pytest.mark.asyncio
async def test_embedding_reorders_and_records_usage():
    async def create(**kwargs):
        assert kwargs["dimensions"] == 2 and kwargs["model"] == "text-embedding-v4"
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0, 1]),
                SimpleNamespace(index=0, embedding=[1, 0]),
            ],
            usage=SimpleNamespace(prompt_tokens=2, total_tokens=2),
            model="text-embedding-v4",
        )

    settings = Settings(
        _env_file=None,
        embedding_dimensions=2,
        dashscope_api_key="test",
        bailian_base_url="https://example.invalid",
    )
    provider = Bailian(settings, SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    budget = Budget()
    assert await provider.embed(["first", "second"], budget) == [[1, 0], [0, 1]]
    assert budget.attempts == 1 and budget.tokens["total_tokens"] == 2


@pytest.mark.asyncio
async def test_hybrid_search_full_text_and_recalled_originals_in_prompt(corpus):
    corpus.settings.retrieval_mode = "hybrid"
    corpus.settings.embedding_dimensions = 2
    corpus.vectors = [[1, 0] for _ in corpus.ids]

    class Embeddings:
        async def embed(self, texts, budget):
            budget.consume()
            return [[1, 0] for _ in texts]

    sources = text_sources("普通内容" * 150 + "\n监管部门担保收益")
    hits, trace = await corpus.search(sources, Embeddings(), Budget())
    assert any(t["start"] >= 512 for t in trace)
    assert all(t["vector"] and len(t["selected"]) <= 8 for t in trace)
    seen = set()
    for cards, articles in corpus.batches(6, hits):
        seen.update(c["rule_id"] for c in cards)
        payload = json.loads(
            judge_messages(
                AuditRequest(text="测试"),
                sources,
                cards,
                corpus.context_articles(articles, hits),
                True,
                hits,
            )[1]["content"]
        )
        supplied = {
            a["article_id"]: a["original_text"]
            for group in payload["rule_articles"]
            for a in group["articles"]
        }
        supplied.update({a["article_id"]: a["original_text"] for a in payload["articles"]})
        assert all(supplied[aid] == corpus.articles[aid]["original_text"] for aid in hits)
    assert seen == set(corpus.rules)


@pytest.mark.asyncio
async def test_hybrid_failure_cannot_silently_fall_back(corpus):
    corpus.settings.retrieval_mode = "hybrid"
    corpus.vectors = [[1, 0] for _ in corpus.ids]

    class Broken(MockProvider):
        async def embed(self, texts, budget):
            raise ModelFailure("embedding_unavailable", "failed")

        async def call(self, *args, **kwargs):
            pytest.fail("Judgment must not run after failed required retrieval")

    result = await AuditService(corpus.settings, corpus, Broken()).review(AuditRequest(text="文案"))
    assert result.status == "failed" and result.decision is None
    assert len(result.coverage.rules) == len(corpus.rules)
    assert all(r.status == "failed" for r in result.coverage.rules)


@pytest.mark.asyncio
async def test_hybrid_search_only_labels_returned_vector_as_invalid(corpus):
    corpus.settings.retrieval_mode = "hybrid"
    corpus.settings.embedding_dimensions = 2
    corpus.vectors = [[1, 0] for _ in corpus.ids]

    class InvalidVector:
        async def embed(self, texts, budget):
            return [[1] for _ in texts]

    with pytest.raises(ModelFailure) as captured:
        await corpus.search(text_sources("测试文案"), InvalidVector(), Budget())

    assert captured.value.code == "invalid_embedding_output"


@pytest.mark.asyncio
async def test_none_context_mode_skips_rag_search_entirely(corpus):
    corpus.settings.rag_batch_context_mode = "none"

    async def unexpected_search(*args, **kwargs):
        pytest.fail("RAG search must not run when context mode is none")

    corpus.search = unexpected_search
    result = await AuditService(corpus.settings, corpus, MockProvider()).review(
        AuditRequest(text="普通保险知识介绍", depth="strict")
    )

    assert result.meta["retrieval_executed"] is False
    assert result.meta["retrieval_trace"] == []
    assert result.meta["retrieved_article_ids"] == []
    assert all(not row["retrieved_article_ids"] for row in result.meta["context_trace"])
    assert all(not row["dropped_retrieved_article_ids"] for row in result.meta["context_trace"])


@pytest.mark.asyncio
async def test_long_material_prunes_optional_retrieval_context_instead_of_failing():
    settings = Settings(
        _env_file=None,
        audit_mock=True,
        retrieval_mode="bm25",
        batch_rule_count=4,
        batch_max_characters=90000,
    )
    corpus = Corpus(settings)

    async def retrieve_every_article(sources, provider, budget):
        # Reproduce the former worst case: many short material sections made
        # the union of per-section top-eight hits approach the whole corpus.
        return list(corpus.articles), []

    corpus.search = retrieve_every_article
    material = (
        Path(__file__).parents[1] / "fixtures" / "context_budget_marketing.txt"
    ).read_text(encoding="utf-8")
    result = await AuditService(settings, corpus, MockProvider()).review(
        AuditRequest(
            text=material,
            depth="strict",
            context={
                "channel": "internet",
                "publisher_type": "insurance_institution",
                "product_type": "insurance",
                "material_completeness": "complete",
            },
        )
    )

    assert not any(error.code == "context_budget_exceeded" for error in result.errors)
    assert len(result.coverage.rules) == len(corpus.rules) == 46
    assert all(
        row["prompt_characters"] <= settings.batch_max_characters
        for row in result.meta["context_trace"]
    )
    assert any(row["dropped_retrieved_article_ids"] for row in result.meta["context_trace"])
    for row in result.meta["context_trace"]:
        required = {
            aid
            for rule_id in row["rule_ids"]
            for aid in (
                corpus.rules[rule_id]["article_ids"]
                + corpus.rules[rule_id].get("supporting_article_ids", [])
            )
        }
        assert required <= set(row["article_ids"])
        assert set(row["retrieved_article_ids"]) | set(
            row["dropped_retrieved_article_ids"]
        ) == set(corpus.articles)


@pytest.mark.asyncio
async def test_depth_selects_retrieved_rules_or_full_baseline(corpus):
    selected_rule_id = next(iter(corpus.rules))
    selected_article_id = corpus.rules[selected_rule_id]["article_ids"][0]

    async def one_article(*args, **kwargs):
        return [selected_article_id], [{"query": "测试", "hits": [selected_article_id]}]

    corpus.search = one_article
    simple = await AuditService(corpus.settings, corpus, MockProvider()).review(
        AuditRequest(
            text="普通保险知识介绍",
            depth="concise",
            context={"material_completeness": "complete"},
        )
    )
    complete = await AuditService(corpus.settings, corpus, MockProvider()).review(
        AuditRequest(
            text="普通保险知识介绍",
            depth="strict",
            context={"material_completeness": "complete"},
        )
    )

    expected = {
        rule_id
        for rule_id, card in corpus.rules.items()
        if selected_article_id
        in card["article_ids"] + card.get("supporting_article_ids", [])
    }
    assert set(simple.meta["selected_rule_ids"]) == expected
    assert len(simple.meta["omitted_rule_ids"]) == len(corpus.rules) - len(expected)
    assert sum(r.status == "not_reviewed" for r in simple.coverage.rules) == len(
        simple.meta["omitted_rule_ids"]
    )
    assert simple.decision == "needs_review"
    assert complete.meta["rule_selection_mode"] == "all"
    assert len(complete.meta["selected_rule_ids"]) == len(corpus.rules)
    assert complete.meta["omitted_rule_ids"] == []
    assert not any(r.status == "not_reviewed" for r in complete.coverage.rules)


def test_targeted_batch_context_keeps_mandatory_law_and_caps_optional_hits(corpus):
    retrieved = list(corpus.articles)
    batches = list(corpus.batches(4, retrieved))
    selections = []
    for cards, mandatory in batches[:3]:
        context, selected, dropped = corpus.budgeted_context_articles(
            mandatory, retrieved, cards, "targeted", 4
        )
        mandatory_hits = set(mandatory) & set(retrieved)
        optional_selected = set(selected) - mandatory_hits
        assert set(mandatory) <= set(context)
        assert len(optional_selected) <= 4
        assert set(selected) | set(dropped) == set(retrieved)
        assert not (set(selected) & set(dropped))
        selections.append(optional_selected)

    # Different rule batches should not receive the same global context copy.
    assert len({frozenset(selection) for selection in selections}) > 1


def test_global_batch_context_remains_available_for_ab_comparison(corpus):
    cards, mandatory = next(corpus.batches(4, corpus.articles))
    retrieved = list(corpus.articles)
    targeted, targeted_ids, _ = corpus.budgeted_context_articles(
        mandatory, retrieved, cards, "targeted", 8
    )
    global_context, global_ids, _ = corpus.budgeted_context_articles(
        mandatory, retrieved, cards, "global", 8
    )
    assert set(mandatory) <= set(targeted)
    assert set(mandatory) <= set(global_context)
    assert len(targeted_ids) < len(global_ids)


@pytest.mark.asyncio
async def test_condition_ids_resolve_but_unknown_and_duplicates_fail(corpus):
    card = corpus.rules["marketing_truthful_and_not_misleading"]
    request = AuditRequest(text="测试")
    sources = text_sources(request.text)
    output = JudgeOutput.model_validate_json(
        await MockProvider().call(
            "text", judge_messages(request, sources, [card], {}, True, []), Budget()
        )
    )
    for i, condition in enumerate(output.findings[0].condition_results, 1):
        condition.condition = f"c{i}"
    resolve_condition_ids(output, [card], sources)
    assert [c.condition for c in output.findings[0].condition_results] == card["trigger_conditions"]
    output.findings[0].condition_results[0].condition = "c999"
    with pytest.raises(ValueError, match="Condition coverage"):
        resolve_condition_ids(output, [card], sources)
    output.findings[0].condition_results[0].condition = "c1"
    output.findings[0].condition_results.append(
        output.findings[0].condition_results[0].model_copy()
    )
    with pytest.raises(ValueError, match="Condition coverage"):
        resolve_condition_ids(output, [card], sources)
