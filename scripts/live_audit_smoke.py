"""Real API smoke tests on explicit synthetic demonstrations, not an evaluation set."""

import argparse
import asyncio
import json
from datetime import UTC, datetime

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import AuditContext, AuditRequest
from insurance_audit.service import AuditService
from insurance_audit.uploads import validate_image

CASES = {
    "violation": ("安心保险产品，由监管部门担保收益，购买后稳赚不赔。", "complete", []),
    "education": (
        "保险知识科普：任何人都不应宣称‘监管部门担保收益’。分红属于非保证利益，实际收益可能低于演示水平。本文不介绍或销售具体产品。",
        "complete",
        [],
    ),
    "multi": ("请结合两张图片审核完整图文材料。", "complete", [1, 2]),
    "review": ("某年金保险产品，详细说明请见完整宣传页面。（当前仅为局部截取）", "partial", []),
}


async def main(names, output):
    settings = Settings(audit_mock=False)
    provider = Bailian(settings)
    service = AuditService(settings, Corpus(settings), provider)
    path = settings.project_root / output
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"cases": {}}
    try:
        for name in names:
            print(f"Running real API case: {name}", flush=True)
            text, completeness, image_numbers = CASES[name]
            images = [
                validate_image(
                    (
                        settings.project_root / f"src/insurance_audit/static/demo-{n}.png"
                    ).read_bytes(),
                    f"image_{i}",
                    "image/png",
                )
                for i, n in enumerate(image_numbers, 1)
            ]
            request = AuditRequest(
                text=text,
                context=AuditContext(
                    channel="internet",
                    publisher_type="insurance_institution",
                    product_type="insurance",
                    material_completeness=completeness,
                ),
            )
            result = await service.review(request, images)
            report["cases"][name] = {
                "run_at_utc": datetime.now(UTC).isoformat(),
                "synthetic_demo": True,
                "response": result.model_dump(mode="json"),
            }
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "case": name,
                        "status": result.status,
                        "decision": result.decision,
                        "violations": len(result.violations),
                        "reviews": len(result.review_items),
                        "errors": [e.code for e in result.errors],
                        "latency_ms": result.meta["latency_ms"],
                        "attempts": result.meta["attempts"],
                    }
                ),
                flush=True,
            )
    finally:
        await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Real API calls incur usage; uses synthetic examples only."
    )
    parser.add_argument("cases", nargs="*", choices=list(CASES))
    parser.add_argument("--out", default="reports/text-audit-smoke.json")
    args = parser.parse_args()
    asyncio.run(main(args.cases or ["violation", "education", "review"], args.out))
