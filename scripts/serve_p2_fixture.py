"""Local UI fault-injection harness. MOCK ONLY; never calls a model provider."""

import asyncio
import json

import uvicorn

from insurance_audit.api import create_app
from insurance_audit.config import Settings
from insurance_audit.models.bailian import ModelFailure
from insurance_audit.models.mock import MockProvider


class FaultProvider(MockProvider):
    async def call(self, kind, messages, budget, **kwargs):
        if kind == "text":
            payload = json.loads(messages[1]["content"])
            text = "\n".join(s["text"] for s in payload["sources"])
            if "P2_CANCEL" in text:
                await asyncio.sleep(10)
            if "P2_FAILED" in text or (
                "P2_PARTIAL" in text
                and any(r["rule_id"] == "marketing_message_optout" for r in payload["rules"])
            ):
                raise ModelFailure("budget_exhausted", "P2 UI 模拟预算耗尽")
        return await super().call(kind, messages, budget, **kwargs)


if __name__ == "__main__":
    uvicorn.run(
        create_app(Settings(_env_file=None, audit_mock=True), FaultProvider()),
        host="127.0.0.1",
        port=8001,
        access_log=False,
    )
