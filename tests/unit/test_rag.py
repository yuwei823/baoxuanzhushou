import json
from types import SimpleNamespace

import pytest

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian, Budget, ModelFailure
from insurance_audit.models.mock import MockProvider
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import AuditRequest
from insurance_audit.service import AuditService
from insurance_audit.vector_index import build_index, load_index, normalize
from insurance_audit.workflow import judge_messages, text_sources


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
    assert provider.calls == 18 and report["article_count"] == 172
    assert (await build_index(corpus, settings, provider))["status"] == "reused"
    assert provider.calls == 18
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
        supplied = {a["article_id"]: a["original_text"] for a in payload["articles"]}
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
