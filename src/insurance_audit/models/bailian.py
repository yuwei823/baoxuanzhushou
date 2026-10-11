import asyncio
import json
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI


class ModelFailure(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


class Budget:
    def __init__(self, seconds=150, maximum=16, clock=time.monotonic):
        self.clock, self.deadline, self.maximum = clock, clock() + seconds, maximum
        self.attempts = 0
        self.calls = []
        self.tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def remaining(self):
        left = self.deadline - self.clock()
        if left <= 0:
            raise ModelFailure("budget_exhausted", "审核整体时间预算已耗尽。")
        return left

    def consume(self):
        self.remaining()
        if self.attempts >= self.maximum:
            raise ModelFailure("budget_exhausted", "审核模型调用次数预算已耗尽。")
        self.attempts += 1


def retry_after(value):
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError):
            return 0


class Bailian:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.gate = asyncio.Semaphore(settings.model_concurrency)
        self.client = client or AsyncOpenAI(
            api_key=settings.dashscope_api_key.get_secret_value() or "not-configured",
            base_url=settings.bailian_base_url
            or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_retries=0,
        )

    async def close(self):
        await self.client.close()

    async def call(self, kind, messages, budget, max_tokens=8000):
        if not self.settings.configured:
            raise ModelFailure("model_not_configured", "请在后端配置百炼密钥和地域 Base URL。")
        model = (
            self.settings.bailian_vision_model
            if kind == "vision"
            else self.settings.bailian_text_model
        )
        for retry in range(self.settings.model_max_retries + 1):
            started = time.monotonic()
            wait = 0
            try:
                async with asyncio.timeout(budget.remaining()):
                    async with self.gate:
                        budget.consume()
                        try:
                            response = await self.client.chat.completions.create(
                                model=model,
                                messages=messages,
                                temperature=0,
                                max_tokens=max_tokens,
                                timeout=min(
                                    self.settings.model_timeout_seconds, budget.remaining()
                                ),
                                **(
                                    {"response_format": {"type": "json_object"}}
                                    if kind == "text"
                                    else {}
                                ),
                            )
                        finally:
                            budget.calls.append(
                                {
                                    "kind": kind,
                                    "model": model,
                                    "latency_ms": round((time.monotonic() - started) * 1000),
                                }
                            )
                if response.usage:
                    for key in budget.tokens:
                        budget.tokens[key] += getattr(response.usage, key, 0) or 0
                budget.calls[-1]["actual_model"] = response.model
                if not response.choices or response.choices[0].finish_reason != "stop":
                    raise ModelFailure("invalid_model_output", "模型输出未完整结束。")
                return response.choices[0].message.content or ""
            except (APITimeoutError, APIConnectionError) as error:
                failure = ModelFailure("model_unavailable", "模型连接失败或调用超时。", True)
                cause = error
            except TimeoutError as error:
                raise ModelFailure("budget_exhausted", "审核整体时间预算已耗尽。") from error
            except APIStatusError as error:
                cause = error
                code = error.status_code
                recoverable = code == 429 or code in (500, 502, 503, 504)
                failure = ModelFailure(
                    "model_auth_error" if code in (401, 403) else "model_http_error",
                    f"模型服务返回 HTTP {code}。",
                    recoverable,
                )
                wait = retry_after(error.response.headers.get("Retry-After"))
            if not failure.retryable or retry >= self.settings.model_max_retries:
                raise failure from cause
            wait = max(wait, (2**retry) + random.uniform(0, 0.2))
            if wait >= budget.remaining():
                raise ModelFailure("budget_exhausted", "重试等待将超过剩余审核预算。")
            await asyncio.sleep(wait)


async def structured(provider, kind, messages, schema, budget, validate=None, max_tokens=8000):
    """One structure repair per batch; semantic checks also consume that repair allowance."""
    for attempt in range(2):
        try:
            raw = await provider.call(kind, messages, budget, max_tokens=max_tokens)
            value = schema.model_validate_json(raw)
            if validate:
                validate(value)
            return value
        except (ValueError, json.JSONDecodeError) as error:
            failure = error
        except ModelFailure as error:
            if error.code != "invalid_model_output":
                raise
            failure = error
        if not attempt:
            messages = [
                *messages,
                {
                    "role": "user",
                    "content": "上次输出未通过结构、覆盖或证据校验。重新检查原始材料，仅输出完整 JSON，覆盖全部 rule_id；不得伪造引用或证据。",
                },
            ]
    raise ModelFailure(
        "invalid_model_output", "模型输出经一次修复后仍不符合结构或证据约束。"
    ) from failure
