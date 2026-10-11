"""Small, immutable, version-bound local vector index; no user text persisted."""

import hashlib
import json
import math
import os
from uuid import uuid4

from insurance_audit.models.bailian import Budget, ModelFailure


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def normalize(vector, dimensions):
    if len(vector) != dimensions or any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
        for x in vector
    ):
        raise ValueError("向量维度或数值无效。")
    norm = math.sqrt(sum(x * x for x in vector))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("向量范数无效。")
    return [x / norm for x in vector]


def specification(corpus, settings):
    texts = [
        corpus.documents[a["document_id"]]["title"]
        + "\n"
        + a["chapter"]
        + "\n"
        + a["article_label"]
        + "\n"
        + a["original_text"]
        for a in corpus.articles.values()
    ]
    # Current longest article is 787 characters. Future oversized articles need
    # a reviewed child-chunk strategy, never truncation of exceptions.
    if any(len(t) > 2000 for t in texts):
        raise ValueError("条文超过当前整条索引限制，须建立保留父条关系的分款索引。")
    meta = {
        "ruleset_id": settings.ruleset_id,
        "ruleset_hash": corpus.hash,
        "embedding_model": settings.embedding_model,
        "dimensions": settings.embedding_dimensions,
        "chunker_version": "whole-article-v1",
        "article_ids": corpus.ids,
        "text_hashes": [digest(t) for t in texts],
    }
    return meta, texts


def index_path(settings, meta):
    return settings.project_root / "data/indexes" / (digest(meta) + ".json")


def load_index(corpus, settings):
    meta, _ = specification(corpus, settings)
    path = index_path(settings, meta)
    payload = json.loads(path.read_text(encoding="utf-8"))
    vectors = payload["vectors"]
    if payload["manifest"] != meta or payload["vectors_sha256"] != digest(vectors):
        raise ValueError("向量索引版本或哈希不匹配。")
    if len(vectors) != len(corpus.ids):
        raise ValueError("向量索引条目不完整。")
    return meta, [normalize(v, settings.embedding_dimensions) for v in vectors]


async def build_index(corpus, settings, provider):
    meta, texts = specification(corpus, settings)
    path = index_path(settings, meta)
    if path.exists():
        load_index(corpus, settings)
        return {"status": "reused", "path": str(path), "article_count": len(texts)}
    budget = Budget(seconds=900, maximum=60)  # Offline construction, separate from audit budget.
    vectors = []
    for start in range(0, len(texts), 10):
        rows = await provider.embed(texts[start : start + 10], budget)
        if len(rows) != len(texts[start : start + 10]):
            raise ModelFailure("invalid_embedding_output", "向量条数不匹配。")
        vectors.extend(normalize(v, settings.embedding_dimensions) for v in rows)
    payload = {"manifest": meta, "vectors": vectors, "vectors_sha256": digest(vectors)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        # On Windows rename refuses to overwrite an existing immutable index.
        os.rename(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    load_index(corpus, settings)
    return {
        "status": "built",
        "path": str(path),
        "article_count": len(texts),
        "manifest": meta,
        "attempts": budget.attempts,
        "token_usage": budget.tokens,
    }
