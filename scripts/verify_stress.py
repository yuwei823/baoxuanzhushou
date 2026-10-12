"""Real HTTP re-verification of the Unicode/HTML stress case for G2 citation repair."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from insurance_audit.config import Settings
from insurance_audit.retrieval import Corpus

STRESS_TEXT = "🧪<img src=x onerror=alert(1)>安心保险产品，由监管部门担保收益，购买后稳赚不赔。"
CONTEXT = {
    "channel": "internet",
    "publisher_type": "insurance_institution",
    "product_type": "insurance",
    "material_completeness": "complete",
}


def checks(response, corpus):
    citation_valid = True
    for violation in response["violations"]:
        for citation in violation["citations"]:
            citation_valid &= (
                citation["article_id"] in corpus.rules[violation["rule_id"]]["article_ids"]
            )
    # A first-attempt validation error that a repair then fixed is an expected trace;
    # only a final-attempt (attempt == 2) citation failure means the repair did not work.
    citation_repair_succeeded = not any(
        error.get("attempt") == 2
        and "Citation is not a direct rule article" in error.get("categories", [])
        for error in response["meta"].get("validation_errors", [])
    )
    return {
        "expected_decision": response["decision"] == "non_compliant",
        "completed_without_errors": response["status"] == "completed" and not response["errors"],
        "violations_found": len(response["violations"]) >= 1,
        "citations_direct": bool(citation_valid),
        "citation_repair_succeeded": citation_repair_succeeded,
        "real_hybrid": not response["mock"] and response["meta"]["retrieval_mode"] == "hybrid",
        "no_vision_call": all(
            call["kind"] != "vision" for call in response["meta"].get("calls", [])
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", type=Path, default=Path("reports/p2-stress-reverify.json"))
    args = parser.parse_args()
    corpus = Corpus(Settings())
    with httpx.Client(base_url=args.base_url, timeout=170, trust_env=False) as client:
        ready = client.get("/readyz")
        ready.raise_for_status()
        result = client.post(
            "/api/v1/audits",
            files={
                "text": (None, STRESS_TEXT),
                "context": (None, json.dumps(CONTEXT)),
            },
        )
        response = result.json()
        assertions = checks(response, corpus)
        report = {
            "started_at_utc": datetime.now(UTC).isoformat(),
            "label_status": "provisional",
            "scope": "G2 unicode/HTML stress case re-verification after citation repair",
            "readiness": ready.json(),
            "text": STRESS_TEXT,
            "context": CONTEXT,
            "transport_ok": result.status_code == 200,
            "checks": assertions,
            "passed": result.status_code == 200
            and all(assertions.values())
            and response["status"] == "completed",
            "response": response,
        }
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report["checks"], ensure_ascii=False), flush=True)
        print(
            "status={} decision={} passed={}".format(
                response["status"], response["decision"], report["passed"]
            ),
            flush=True,
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
