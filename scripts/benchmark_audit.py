"""Controlled real-API development benchmark. Incurs usage; never changes .env."""

import argparse
import asyncio
import hashlib
import itertools
import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from verify_g1 import CASES, CONTEXT, checks

from insurance_audit.config import Settings
from insurance_audit.evaluation.metrics import percentile
from insurance_audit.models.bailian import Bailian
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import AuditContext, AuditRequest
from insurance_audit.service import AuditService
from insurance_audit.workflow import PROMPT_VERSION


def summarize(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row["configuration"], []).append(row)
    summary = {}
    for name, items in groups.items():
        responses = [i["response"] for i in items]
        latencies = [r["meta"]["latency_ms"] for r in responses]
        calls = [c for r in responses for c in r["meta"]["calls"]]
        summary[name] = {
            "runs": len(items),
            "all_checks_passed": sum(all(i["checks"].values()) for i in items),
            "expected_decisions": sum(i["checks"]["expected_decision"] for i in items),
            "completed": sum(r["status"] == "completed" for r in responses),
            "latency_p50_ms": median(latencies),
            "latency_p95_ms": percentile(latencies, 0.95),
            "queue_ms_sum": sum(c.get("queue_ms", 0) for c in calls),
            "request_ms_sum": sum(c.get("request_ms", 0) for c in calls),
            "transport_retries": sum(c.get("transport_retry", 0) > 0 for c in calls),
            "structure_repairs": sum(
                c.get("structure_attempt", 0) > 0 and not c.get("transport_retry", 0) for c in calls
            ),
            "tokens": {
                k: sum(r["meta"]["token_usage"].get(k, 0) for r in responses)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            },
            "rule_statuses": dict(
                sum((Counter(r["meta"]["rule_status_counts"]) for r in responses), Counter())
            ),
            "errors": dict(Counter(e["code"] for r in responses for e in r["errors"])),
            "validation_categories": dict(
                Counter(
                    v
                    for r in responses
                    for e in r["meta"]["validation_errors"]
                    for v in e["categories"]
                )
            ),
        }
    return summary


async def main(args):
    if args.out.exists():
        raise ValueError("Output directory already exists; choose a new run")
    args.out.mkdir(parents=True)
    settings = Settings()
    if settings.audit_mock or not settings.configured:
        raise ValueError("Real configured API required")
    configurations = list(itertools.product(args.models, args.batches, args.concurrencies))
    corpus = Corpus(settings)
    source_files = [
        Path("src/insurance_audit") / n
        for n in ("workflow.py", "retrieval.py", "service.py", "models/bailian.py")
    ]
    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "ruleset_id": settings.ruleset_id,
        "ruleset_hash": corpus.hash,
        "rule_count": len(corpus.rules),
        "prompt_version": PROMPT_VERSION,
        "label_status": "provisional",
        "scope": "exposed development cases; not formal accuracy evaluation",
        "thinking": False,
        "attempt_limit": settings.audit_max_model_attempts,
        "audit_timeout": settings.audit_timeout_seconds,
        "model_timeout": settings.model_timeout_seconds,
        "retrieval": settings.retrieval_mode,
        "embedding": settings.embedding_model,
        "dimensions": settings.embedding_dimensions,
        "repeats": args.repeats,
        "configurations": configurations,
        "case_sha256": hashlib.sha256(json.dumps(CASES, ensure_ascii=False).encode()).hexdigest(),
        "code_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = []
    # Deterministic interleaving reduces systematic load/order bias. Only one audit at a time.
    rng = random.Random(20261012)
    for repeat in range(args.repeats):
        for name, _, text, completeness, expected in CASES:
            configs = configurations.copy()
            rng.shuffle(configs)
            for model, batch, concurrency in configs:
                config = f"{model}-b{batch}-c{concurrency}"
                print(f"RUN {repeat + 1} {name} {config}", flush=True)
                current = settings.model_copy(
                    update={
                        "bailian_text_model": model,
                        "batch_rule_count": batch,
                        "model_concurrency": concurrency,
                        "bailian_text_enable_thinking": False,
                    }
                )
                provider = Bailian(current)
                try:
                    result = await AuditService(current, corpus, provider).review(
                        AuditRequest(
                            text=text,
                            context=AuditContext(
                                **dict(CONTEXT, material_completeness=completeness)
                            ),
                            depth="concise",
                        )
                    )
                finally:
                    await provider.close()
                response = result.model_dump(mode="json")
                row = {
                    "repeat": repeat + 1,
                    "sample_id": name,
                    "configuration": config,
                    "expected": expected,
                    "checks": checks(response, expected, corpus),
                    "response": response,
                }
                rows.append(row)
                with (args.out / "results.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                (args.out / "summary.json").write_text(
                    json.dumps(summarize(rows), ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            "case": name,
                            "config": config,
                            "passed": all(row["checks"].values()),
                            "status": result.status,
                            "decision": result.decision,
                            "ms": result.meta["latency_ms"],
                            "errors": [e.code for e in result.errors],
                        }
                    ),
                    flush=True,
                )
    manifest["completed"] = True
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["qwen3.7-plus", "qwen-plus", "qwen-turbo"])
    parser.add_argument("--batches", nargs="+", type=int, choices=[2, 3], default=[2])
    parser.add_argument("--concurrencies", nargs="+", type=int, choices=[4, 8], default=[8])
    parser.add_argument("--repeats", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--out", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
