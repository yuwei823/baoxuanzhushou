import json
import logging
import math
from functools import lru_cache
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from insurance_audit.corpus.ingest import confined, sha256
from insurance_audit.corpus.validate import validate_corpus
from insurance_audit.models.bailian import ModelFailure
from insurance_audit.vector_index import load_index, normalize

jieba.setLogLevel(logging.ERROR)


@lru_cache(maxsize=8)
def corpus_release_ready(root: str, ruleset_id: str) -> bool:
    """Cache the release gate per (root, ruleset).

    A published snapshot is immutable, so re-validating on every Corpus
    construction only repeats the same full-file hashing. Callers that mutate
    corpus files must call validate_corpus directly (or invalidate this cache).
    """
    return validate_corpus(Path(root), ruleset_id)["release_ready"]


def related_rule_ids(rules, retrieved_article_ids):
    """Map retrieved law articles to rule cards without treating hits as violations."""
    hits = set(retrieved_article_ids)
    return [
        rule_id
        for rule_id, card in rules.items()
        if hits.intersection(card["article_ids"] + card.get("supporting_article_ids", []))
    ]


class Corpus:
    def __init__(self, settings, require_index=True):
        self.settings = settings
        root, ruleset = settings.project_root.resolve(), settings.ruleset_id
        path = confined(root, "data/corpus/" + ruleset)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("publication_status") != "published" or not corpus_release_ready(
            str(root), ruleset
        ):
            raise ValueError("语料尚未发布或未通过完整性校验。")
        self.manifest, self.hash = manifest, sha256(path / "manifest.json")
        self.documents = self.load(path, "documents.jsonl", "document_id")
        self.articles = self.load(path, "articles.jsonl", "article_id")
        self.rules = self.load(path, "rule_cards.jsonl", "rule_id")
        # Cap on carried article text per batch so a merged group cannot blow the
        # prompt budget; the judge prompt itself adds rule cards and material.
        self.article_budget = max(1000, settings.batch_max_characters // 3)
        self.ids = list(self.articles)
        self.article_positions = {aid: index for index, aid in enumerate(self.ids)}
        self.index = BM25Okapi(
            [list(jieba.cut(self.articles[aid]["original_text"])) for aid in self.ids]
        )
        self.vector_manifest, self.vectors = None, None
        if settings.retrieval_mode == "hybrid" and require_index:
            self.vector_manifest, self.vectors = load_index(self, settings)

    async def search(self, sources, provider, budget):
        queries = [
            (s.source_id, start, s.text[start : start + 512])
            for s in sources
            for start in range(0, len(s.text), 512)
        ]
        vectors = []
        if self.settings.retrieval_mode == "hybrid":
            if self.vectors is None:
                raise ModelFailure("index_not_ready", "匹配当前规则版本的向量索引未就绪。")
            for start in range(0, len(queries), 10):
                batch = queries[start : start + 10]
                # Provider failures must retain their real error code. In
                # particular, UnicodeEncodeError is a ValueError subclass; the
                # previous broad try block mislabeled a malformed API key as an
                # invalid embedding vector.
                rows = await provider.embed([q[2] for q in batch], budget)
                if len(rows) != len(batch):
                    raise ModelFailure("invalid_embedding_output", "查询向量数量不匹配。")
                try:
                    normalized = [
                        normalize(vector, self.settings.embedding_dimensions)
                        for vector in rows
                    ]
                except ValueError as error:
                    raise ModelFailure(
                        "invalid_embedding_output", "查询向量未通过校验。"
                    ) from error
                vectors.extend(normalized)
        # Keep a global relevance order across all material segments.  The old
        # implementation returned an alphabetically sorted union of every
        # segment's top eight hits.  Long, line-oriented material could therefore
        # return most of the corpus, with the least useful articles winning the
        # prompt budget simply because their ids sorted first.
        aggregate_rrf, trace = {}, []
        for index, (sid, offset, text) in enumerate(queries):
            budget.remaining()
            scores = self.index.get_scores(list(jieba.cut(text)))
            lexical = [
                i
                for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
                if scores[i] > 0
            ][:8]
            semantic = []
            if vectors:
                similarities = [sum(a * b for a, b in zip(vectors[index], v)) for v in self.vectors]
                semantic = sorted(
                    range(len(similarities)), key=lambda i: similarities[i], reverse=True
                )[:8]
            rrf = {}
            for ranking in (lexical, semantic):
                for rank, article_index in enumerate(ranking, 1):
                    rrf[article_index] = rrf.get(article_index, 0) + 1 / (60 + rank)
                    aggregate_rrf[article_index] = aggregate_rrf.get(article_index, 0) + 1 / (
                        60 + rank
                    )
            selected = sorted(rrf, key=lambda i: (-rrf[i], self.ids[i]))[:8]
            ids = [self.ids[i] for i in selected]
            trace.append(
                {
                    "source_id": sid,
                    "start": offset,
                    "end": offset + len(text),
                    "bm25": [self.ids[i] for i in lexical],
                    "vector": [self.ids[i] for i in semantic],
                    "selected": ids,
                }
            )
        ranked = sorted(aggregate_rrf, key=lambda i: (-aggregate_rrf[i], self.ids[i]))
        return [self.ids[i] for i in ranked], trace

    @staticmethod
    def load(path, name, key):
        rows = [json.loads(line) for line in (path / name).read_text(encoding="utf-8").splitlines()]
        return {r[key]: r for r in rows}

    def retrieve(self, sources):
        found = set()
        for source in sources:
            # Every section participates, including content beyond the first 512 characters.
            for start in range(0, len(source.text), 512):
                scores = self.index.get_scores(list(jieba.cut(source.text[start : start + 512])))
                found.update(
                    self.ids[i]
                    for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:8]
                    if scores[i] > 0
                )
        return sorted(found)

    def batches(self, batch_size, retrieved=(), rule_ids=None):
        """Group rules so shared law text ships once per call.

        Rules are clustered by their direct article set (union-find over shared
        ids). Multi-rule clusters stay together so a shared article is carried
        once; single-rule clusters share nothing, so they are packed together to
        avoid one call per rule. A batch closes when the carried article text
        would exceed its budget or the rule cap is reached.
        """
        hits = set(retrieved)
        selected = set(rule_ids) if rule_ids is not None else None
        rules = [
            card
            for rule_id, card in self.rules.items()
            if selected is None or rule_id in selected
        ]
        parent = {c["rule_id"]: c["rule_id"] for c in rules}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # Link rules that share at least one direct article.
        owners = {}
        for card in rules:
            for aid in card["article_ids"]:
                for other in owners.get(aid, ()):
                    union(card["rule_id"], other)
                owners.setdefault(aid, []).append(card["rule_id"])

        groups = {}
        for card in rules:
            groups.setdefault(find(card["rule_id"]), []).append(card)

        def rank(group):
            related = any(hits.intersection(c["article_ids"]) for c in group)
            return (not related, -len(group))

        # Multi-rule clusters first (they carry shared text), then singletons
        # packed together, since a lone rule shares no article with any other.
        clusters = sorted((g for g in groups.values() if len(g) > 1), key=rank)
        singles = [g[0] for g in sorted(groups.values(), key=rank) if len(g) == 1]

        for group in clusters:
            yield from self.pack([group], batch_size)
        if singles:
            yield from self.pack([[card] for card in singles], batch_size)

    def pack(self, groups, batch_size):
        """Flatten groups into batches bounded by article budget and rule cap."""
        batch, carried = [], set()
        for group in groups:
            for card in group:
                extra = {
                    aid
                    for aid in card["article_ids"] + card.get("supporting_article_ids", [])
                }
                if batch and (
                    self.carried_characters(carried | extra) > self.article_budget
                    or len(batch) >= self.max_batch_rules(batch_size)
                ):
                    yield batch, {aid: self.articles[aid] for aid in sorted(carried)}
                    batch, carried = [], set()
                batch.append(card)
                carried |= extra
        if batch:
            yield batch, {aid: self.articles[aid] for aid in sorted(carried)}

    def max_batch_rules(self, batch_size):
        """Upper bound on rules per batch.

        Clustering keeps shared law text from repeating, but each extra rule adds
        output tokens, and latency tracks output length. Keep batches small: the
        cap trades call count against per-call latency.
        """
        return max(batch_size, 2)

    def carried_characters(self, ids):
        return sum(len(self.articles[aid]["original_text"]) for aid in ids if aid in self.articles)

    def context_articles(self, articles, retrieved):
        return {**articles, **{aid: self.articles[aid] for aid in retrieved}}

    def batch_ranked_retrieval(self, cards, retrieved, mandatory_ids, limit):
        """Rank optional hits by both material relevance and batch relevance.

        ``retrieved`` is globally ordered by the submitted material's RRF
        score. The batch's direct law text becomes a local BM25 query. In
        hybrid mode, the centroid of those direct-article embeddings supplies
        a semantic ranking without another paid embedding request. RRF then
        combines the material and batch ranks.
        """
        optional = [
            aid for aid in retrieved if aid in self.articles and aid not in mandatory_ids
        ]
        if not optional or limit <= 0:
            return []

        direct_ids = {
            aid for card in cards for aid in card["article_ids"] if aid in self.articles
        }
        query_tokens = []
        seen_tokens = set()
        for aid in sorted(direct_ids):
            for token in jieba.cut(self.articles[aid]["original_text"]):
                token = token.strip()
                if token and token not in seen_tokens:
                    seen_tokens.add(token)
                    query_tokens.append(token)

        pool_size = max(limit * 3, 8)
        lexical = []
        if query_tokens:
            scores = self.index.get_scores(query_tokens)
            lexical = sorted(
                optional,
                key=lambda aid: (-scores[self.article_positions[aid]], aid),
            )
            lexical = [
                aid for aid in lexical if scores[self.article_positions[aid]] > 0
            ][:pool_size]

        semantic = []
        if self.vectors is not None and direct_ids:
            direct_vectors = [
                self.vectors[self.article_positions[aid]]
                for aid in direct_ids
                if aid in self.article_positions
            ]
            if direct_vectors:
                centroid = [sum(values) / len(direct_vectors) for values in zip(*direct_vectors)]
                norm = math.sqrt(sum(value * value for value in centroid))
                if norm:
                    centroid = [value / norm for value in centroid]
                    similarities = {
                        aid: sum(
                            left * right
                            for left, right in zip(
                                centroid, self.vectors[self.article_positions[aid]]
                            )
                        )
                        for aid in optional
                    }
                    semantic = sorted(optional, key=lambda aid: (-similarities[aid], aid))[
                        :pool_size
                    ]

        relation_rrf = {}
        for ranking in (lexical, semantic):
            for rank, aid in enumerate(ranking, 1):
                relation_rrf[aid] = relation_rrf.get(aid, 0) + 1 / (60 + rank)
        if not relation_rrf:
            return []

        input_rank = {aid: rank for rank, aid in enumerate(retrieved, 1)}
        # A candidate must be near the front of both rankings. Without this
        # intersection every batch would still receive ``limit`` articles,
        # including weak matches from the tail of a long multi-section query.
        material_pool_size = max(limit * 6, 32)
        combined = {
            aid: score + 1 / (60 + input_rank[aid])
            for aid, score in relation_rrf.items()
            if input_rank[aid] <= material_pool_size
        }
        return sorted(combined, key=lambda aid: (-combined[aid], aid))[:limit]

    def budgeted_context_articles(
        self,
        articles,
        retrieved,
        cards=(),
        mode=None,
        retrieved_limit=None,
        retrieved_max_characters=None,
    ):
        """Add ranked retrieval hits without displacing mandatory rule articles.

        ``articles`` contains the direct and supporting law text required by the
        batch. Retrieval hits are augmentation. Global mode follows the material
        order; targeted mode first intersects material relevance with batch-law
        relevance and applies tighter count/character caps. The caller records
        omitted ids for auditability.
        """
        context = dict(articles)
        mandatory_ids = set(context)
        mode = mode or self.settings.rag_batch_context_mode
        retrieved_limit = (
            self.settings.rag_batch_retrieved_limit
            if retrieved_limit is None
            else retrieved_limit
        )
        retrieved_max_characters = (
            self.settings.rag_batch_retrieved_max_characters
            if retrieved_max_characters is None
            else retrieved_max_characters
        )
        mandatory_hits = [aid for aid in retrieved if aid in mandatory_ids]
        optional = [aid for aid in retrieved if aid in self.articles and aid not in mandatory_ids]
        if mode == "global":
            candidates = optional
            augmentation_budget = self.article_budget
        elif mode == "targeted":
            candidates = self.batch_ranked_retrieval(
                cards, retrieved, mandatory_ids, retrieved_limit
            )
            augmentation_budget = min(self.article_budget, retrieved_max_characters)
        elif mode == "none":
            candidates = []
            augmentation_budget = 0
        else:
            raise ValueError(f"Unknown RAG batch context mode: {mode}")

        selected = list(mandatory_hits)
        candidate_set = set(candidates)
        dropped = [aid for aid in optional if aid not in candidate_set]
        augmentation_characters = 0
        for aid in candidates:
            article = self.articles.get(aid)
            if article is None:
                continue
            length = len(article["original_text"])
            if augmentation_characters + length <= augmentation_budget:
                context[aid] = article
                augmentation_characters += length
                selected.append(aid)
            else:
                dropped.append(aid)
        return context, selected, dropped
