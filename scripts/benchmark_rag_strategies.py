"""Compare baseline-only, retrieval-only, and combined audit strategies.

This is a development benchmark over exposed provisional cases.  The
retrieval-only strategy is deliberately isolated here: it maps retrieved law
articles back to rule cards and audits only those rules, so it does not satisfy
the production requirement that every rule is accounted for.
"""

import argparse
import asyncio
import hashlib
import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path

from benchmark_audit import benchmark_checks, summarize
from verify_g1 import CASES, CONTEXT

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian, Budget
from insurance_audit.retrieval import Corpus, related_rule_ids
from insurance_audit.schemas import AuditContext, AuditRequest
from insurance_audit.service import AuditService
from insurance_audit.workflow import PROMPT_VERSION, text_sources

STRATEGIES = {
    "baseline-only": {"context_mode": "none", "rule_mode": "all"},
    "rag-only": {"context_mode": "targeted", "rule_mode": "retrieved"},
    "combined": {"context_mode": "targeted", "rule_mode": "all"},
}


class RetrievedRuleCorpus(Corpus):
    """Shallow corpus view restricted to rules selected by retrieval."""

    def __init__(self, base, rule_ids, retrieved, trace):
        self.__dict__ = base.__dict__.copy()
        self.rules = {rule_id: base.rules[rule_id] for rule_id in rule_ids}
        self._retrieved = list(retrieved)
        self._retrieval_trace = list(trace)

    async def search(self, sources, provider, budget):
        return list(self._retrieved), list(self._retrieval_trace)


def merge_pre_retrieval_metrics(response, budget, retrieval_ms, total_latency_ms):
    """Include the retrieval-only preselection call in end-to-end metrics."""
    meta = response["meta"]
    meta["calls"] = [*budget.calls, *meta["calls"]]
    meta["attempts"] += budget.attempts
    for key, value in budget.tokens.items():
        meta["token_usage"][key] = meta["token_usage"].get(key, 0) + value
    meta["stage_latency"]["retrieval_ms"] = retrieval_ms
    meta["latency_ms"] = total_latency_ms


async def run_case(settings, base_corpus, strategy, text, completeness):
    spec = STRATEGIES[strategy]
    current = settings.model_copy(
        update={
            "bailian_text_model": "qwen3.7-plus",
            "batch_rule_count": 4,
            "model_concurrency": 8,
            "bailian_text_enable_thinking": False,
            "rag_batch_context_mode": spec["context_mode"],
        }
    )
    request = AuditRequest(
        text=text,
        context=AuditContext(**dict(CONTEXT, material_completeness=completeness)),
        depth="concise",
    )
    provider = Bailian(current)
    corpus = base_corpus
    selected_rule_ids = list(base_corpus.rules)
    pre_budget = None
    retrieval_ms = 0
    started = time.monotonic()
    try:
        if spec["rule_mode"] == "retrieved":
            pre_budget = Budget(current.audit_timeout_seconds, current.audit_max_model_attempts)
            retrieval_started = time.monotonic()
            retrieved, trace = await base_corpus.search(
                text_sources(request.text), provider, pre_budget
            )
            retrieval_ms = round((time.monotonic() - retrieval_started) * 1000)
            selected_rule_ids = related_rule_ids(base_corpus.rules, retrieved)
            if not selected_rule_ids:
                raise ValueError("Retrieval-only strategy selected no rules")
            corpus = RetrievedRuleCorpus(base_corpus, selected_rule_ids, retrieved, trace)

        result = await AuditService(current, corpus, provider).review(request)
    finally:
        await provider.close()

    response = result.model_dump(mode="json")
    if pre_budget is not None:
        merge_pre_retrieval_metrics(
            response,
            pre_budget,
            retrieval_ms,
            round((time.monotonic() - started) * 1000),
        )
    selected = set(selected_rule_ids)
    response["meta"]["strategy"] = strategy
    response["meta"]["corpus_rule_count"] = len(base_corpus.rules)
    response["meta"]["selected_rule_ids"] = selected_rule_ids
    response["meta"]["omitted_rule_ids"] = [
        rule_id for rule_id in base_corpus.rules if rule_id not in selected
    ]
    return response


async def main(args):
    if args.out.exists():
        raise ValueError("Output directory already exists; choose a new run")
    args.out.mkdir(parents=True)
    settings = Settings()
    if settings.audit_mock or not settings.configured:
        raise ValueError("Real configured API required")
    base_corpus = Corpus(settings)
    source_files = [
        Path("scripts/benchmark_rag_strategies.py"),
        Path("scripts/benchmark_audit.py"),
        Path("src/insurance_audit/service.py"),
        Path("src/insurance_audit/retrieval.py"),
        Path("src/insurance_audit/workflow.py"),
    ]
    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "ruleset_id": settings.ruleset_id,
        "ruleset_hash": base_corpus.hash,
        "rule_count": len(base_corpus.rules),
        "article_count": len(base_corpus.articles),
        "prompt_version": PROMPT_VERSION,
        "label_status": "provisional",
        "scope": "exposed development cases; not formal accuracy evaluation",
        "model": "qwen3.7-plus",
        "batch_rule_count": 4,
        "model_concurrency": 8,
        "thinking": False,
        "retrieval": settings.retrieval_mode,
        "embedding": settings.embedding_model,
        "dimensions": settings.embedding_dimensions,
        "strategies": args.strategies,
        "strategy_definitions": STRATEGIES,
        "repeats": args.repeats,
        "case_sha256": hashlib.sha256(json.dumps(CASES, ensure_ascii=False).encode()).hexdigest(),
        "code_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files
        },
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows = []
    rng = random.Random(20261014)
    for repeat in range(args.repeats):
        for name, _, text, completeness, expected in CASES:
            strategies = list(args.strategies)
            rng.shuffle(strategies)
            for strategy in strategies:
                print(f"RUN {repeat + 1} {name} {strategy}", flush=True)
                response = await run_case(
                    settings, base_corpus, strategy, text, completeness
                )
                context_mode = STRATEGIES[strategy]["context_mode"]
                assertions = benchmark_checks(
                    response, expected, base_corpus, context_mode
                )
                if strategy == "rag-only":
                    assertions.pop("all_rules_accounted")
                    actual_ids = [row["rule_id"] for row in response["coverage"]["rules"]]
                    selected_ids = response["meta"]["selected_rule_ids"]
                    assertions["selected_rules_accounted"] = (
                        set(actual_ids) == set(selected_ids)
                        and len(actual_ids) == len(set(actual_ids))
                    )
                    assertions["selection_is_retrieval_derived"] = (
                        0 < len(selected_ids) <= len(base_corpus.rules)
                        and set(selected_ids)
                        == set(
                            related_rule_ids(
                                base_corpus, response["meta"]["retrieved_article_ids"]
                            )
                        )
                    )
                row = {
                    "repeat": repeat + 1,
                    "sample_id": name,
                    "configuration": strategy,
                    "expected": expected,
                    "checks": assertions,
                    "response": response,
                }
                rows.append(row)
                with (args.out / "results.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                (args.out / "summary.json").write_text(
                    json.dumps(summarize(rows), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(
                    json.dumps(
                        {
                            "case": name,
                            "strategy": strategy,
                            "passed": all(assertions.values()),
                            "status": response["status"],
                            "decision": response["decision"],
                            "selected_rules": len(response["meta"]["selected_rule_ids"]),
                            "latency_ms": response["meta"]["latency_ms"],
                            "errors": [error["code"] for error in response["errors"]],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    manifest["completed"] = True
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=list(STRATEGIES),
        default=list(STRATEGIES),
    )
    parser.add_argument("--repeats", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--out", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
