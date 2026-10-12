import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian, Budget, structured


class Client:
    def __init__(self, create):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def response(content):
    return SimpleNamespace(
        model="test-model",
        usage=SimpleNamespace(
            prompt_tokens=3,
            completion_tokens=2,
            total_tokens=5,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))],
    )


@pytest.mark.asyncio
async def test_queue_and_request_are_separate_and_usage_is_per_call():
    async def create(**kwargs):
        await asyncio.sleep(0.01)
        return response("{}")

    provider = Bailian(
        Settings(_env_file=None, audit_mock=True, model_concurrency=1), Client(create)
    )
    budget = Budget()
    await provider.gate.acquire()
    task = asyncio.create_task(provider.call("text", [], budget))
    await asyncio.sleep(0.03)
    provider.gate.release()
    await task
    record = budget.calls[0]
    assert record["queue_ms"] >= 20
    assert record["request_ms"] >= 5
    assert abs(record["latency_ms"] - record["queue_ms"] - record["request_ms"]) <= 3
    assert record["token_usage"]["total_tokens"] == 5
    assert record["reasoning_tokens"] == 0
    assert record["transport_retry"] == 0


@pytest.mark.asyncio
async def test_structure_repair_is_distinct_from_transport_retry():
    class Output(BaseModel):
        ok: bool

    values = iter(["broken json", '{"ok":true}', '{"ok":true}'])

    async def create(**kwargs):
        return response(next(values))

    provider = Bailian(Settings(_env_file=None, audit_mock=True), Client(create))
    budget = Budget()
    await structured(provider, "text", [], Output, budget)
    await provider.call("text", [], budget)
    assert [r["structure_attempt"] for r in budget.calls] == [0, 1, 0]
    assert all(r["transport_retry"] == 0 for r in budget.calls)
    assert budget.tokens["total_tokens"] == 15


@pytest.mark.asyncio
async def test_http_failure_records_only_safe_status_and_timing():
    import httpx
    from openai import APIStatusError

    from insurance_audit.models.bailian import ModelFailure

    async def create(**kwargs):
        response = httpx.Response(429, request=httpx.Request("POST", "https://example.invalid"))
        raise APIStatusError("secret_payload", response=response, body={})

    provider = Bailian(
        Settings(_env_file=None, audit_mock=True, model_max_retries=0), Client(create)
    )
    budget = Budget()
    with pytest.raises(ModelFailure):
        await provider.call("text", [], budget)
    record = budget.calls[0]
    assert record["http_status"] == 429
    assert record["outcome"] == "APIStatusError"
    assert "secret_payload" not in str(record)
    assert "request_ms" in record and "queue_ms" in record
