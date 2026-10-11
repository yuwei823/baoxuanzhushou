"""Explicit demo fixtures only. Never silently substitutes for the real provider."""

import base64
import hashlib
import json
from pathlib import Path


class MockProvider:
    async def close(self):
        pass

    async def call(self, kind, messages, budget, max_tokens=8000):
        budget.consume()
        if kind == "vision":
            data = base64.b64decode(messages[1]["content"][1]["image_url"]["url"].split(",", 1)[1])
            manifest_path = Path(__file__).resolve().parents[1] / "static/demo-images.json"
            fixtures = (
                json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists()
                else {}
            )
            text = fixtures.get(hashlib.sha256(data).hexdigest())
            return json.dumps(
                {
                    "text_blocks": [{"text": text}] if text else [],
                    "visual_observations": [],
                    "unreadable_regions": [] if text else ["模拟模式无法识别任意上传图片"],
                    "extraction_warnings": ["固定演示提取，不是真实视觉模型结果"],
                },
                ensure_ascii=False,
            )
        payload = json.loads(messages[1]["content"])
        sources = payload["sources"]
        trigger = next((s for s in sources if "监管部门担保收益" in s["text"]), None)
        findings = []
        for card in payload["rules"]:
            violation = bool(
                trigger and card["rule_id"] == "no_regulatory_guarantee_or_filing_endorsement"
            )
            missing = payload["context"]["material_completeness"] != "complete"
            applicability = (
                "applicable" if violation else "needs_context" if missing else "not_applicable"
            )
            findings.append(
                {
                    "rule_id": card["rule_id"],
                    "applicability": applicability,
                    "finding": "violation"
                    if violation
                    else "uncertain"
                    if missing
                    else "no_violation",
                    "reason": "固定演示：监管收益担保宣传。"
                    if violation
                    else "固定演示用例；未执行真实法律审核。",
                    "condition_results": [
                        {
                            "condition": c,
                            "met": True if violation else None if missing else False,
                            "evidence_ids": [trigger["source_id"]] if violation else [],
                        }
                        for c in card["trigger_conditions"]
                    ],
                    "evidence": [{"source_id": trigger["source_id"], "quote": "监管部门担保收益"}]
                    if violation
                    else [],
                    "article_ids": [card["article_ids"][0]] if violation else [],
                    "absence_disclosure": None,
                    "missing_facts": ["材料完整性"] if missing else [],
                    "model_confidence": None,
                }
            )
        return json.dumps({"findings": findings}, ensure_ascii=False)
