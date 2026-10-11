import json
import logging

import jieba
from rank_bm25 import BM25Okapi

from insurance_audit.corpus.ingest import confined, sha256
from insurance_audit.corpus.validate import validate_corpus

jieba.setLogLevel(logging.ERROR)


class Corpus:
    def __init__(self, settings):
        root, ruleset = settings.project_root.resolve(), settings.ruleset_id
        path = confined(root, "data/corpus/" + ruleset)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest.get("publication_status") != "published"
            or not validate_corpus(root, ruleset)["release_ready"]
        ):
            raise ValueError("语料尚未发布或未通过完整性校验。")
        self.manifest, self.hash = manifest, sha256(path / "manifest.json")
        self.documents = self.load(path, "documents.jsonl", "document_id")
        self.articles = self.load(path, "articles.jsonl", "article_id")
        self.rules = self.load(path, "rule_cards.jsonl", "rule_id")
        self.ids = list(self.articles)
        self.index = BM25Okapi(
            [list(jieba.cut(self.articles[aid]["original_text"])) for aid in self.ids]
        )

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

    def batches(self, batch_size):
        rules = list(self.rules.values())
        for offset in range(0, len(rules), batch_size):
            batch = rules[offset : offset + batch_size]
            ids = {
                aid
                for card in batch
                for aid in card["article_ids"] + card.get("supporting_article_ids", [])
            }
            yield batch, {aid: self.articles[aid] for aid in sorted(ids)}
