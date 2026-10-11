import asyncio
import json
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError


class ModelFailure(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


class Budget:
    def __init__(self, seconds=150, maximum=16, clock=time.monotonic):
        self.clock, self.deadline, self.maximum = clock, clock() + seconds, maximum
        self.attempts = 0
        self.calls = []
        self.validation_errors = []
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

    async def embed(self, texts, budget):
        """Embedding shares the process gate, deadline and attempt budget with judgment."""
        if not self.settings.configured or self.settings.audit_mock:
            raise ModelFailure("embedding_not_configured", "向量接口需要真实百炼配置。")
        if not texts or len(texts) > 10 or any(not t or len(t) > 2000 for t in texts):
            raise ModelFailure(
                "embedding_input_invalid", "向量输入须为 1～10 条，每条最多 2000 字符。"
            )
        for retry in range(self.settings.model_max_retries + 1):
            started = time.monotonic()
            wait = 0
            try:
                async with asyncio.timeout(budget.remaining()):
                    async with self.gate:
                        budget.consume()
                        record = {"kind": "embedding", "model": self.settings.embedding_model}
                        try:
                            response = await self.client.embeddings.create(
                                model=self.settings.embedding_model,
                                input=texts,
                                dimensions=self.settings.embedding_dimensions,
                                encoding_format="float",
                                timeout=min(
                                    self.settings.model_timeout_seconds, budget.remaining()
                                ),
                            )
                        finally:
                            record["latency_ms"] = round((time.monotonic() - started) * 1000)
                            budget.calls.append(record)
                if response.usage:
                    for key in budget.tokens:
                        budget.tokens[key] += getattr(response.usage, key, 0) or 0
                record["actual_model"] = response.model
                if sorted(item.index for item in response.data) != list(range(len(texts))):
                    raise ModelFailure("invalid_embedding_output", "向量响应条目索引不完整。")
                return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
            except (APITimeoutError, APIConnectionError) as error:
                failure = ModelFailure("embedding_unavailable", "向量调用连接失败或超时。", True)
                cause = error
            except TimeoutError as error:
                raise ModelFailure("budget_exhausted", "审核整体时间预算已耗尽。") from error
            except APIStatusError as error:
                cause = error
                code = error.status_code
                failure = ModelFailure(
                    "model_auth_error" if code in (401, 403) else "embedding_http_error",
                    f"向量服务返回 HTTP {code}。",
                    code == 429 or code in (500, 502, 503, 504),
                )
                wait = retry_after(error.response.headers.get("Retry-After"))
            if not failure.retryable or retry >= self.settings.model_max_retries:
                raise failure from cause
            wait = max(wait, 2**retry + random.uniform(0, 0.2))
            if wait >= budget.remaining():
                raise ModelFailure("budget_exhausted", "向量重试将超过剩余预算。")
            await asyncio.sleep(wait)

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
                        record = {"kind": kind, "model": model}
                        options = {}
                        if kind == "text":
                            options["response_format"] = {"type": "json_object"}
                            if self.settings.bailian_text_enable_thinking is not None:
                                options["extra_body"] = {
                                    "enable_thinking": self.settings.bailian_text_enable_thinking
                                }
                                record["enable_thinking"] = (
                                    self.settings.bailian_text_enable_thinking
                                )
                        try:
                            response = await self.client.chat.completions.create(
                                model=model,
                                messages=messages,
                                temperature=0,
                                max_tokens=max_tokens,
                                timeout=min(
                                    self.settings.model_timeout_seconds, budget.remaining()
                                ),
                                **options,
                            )
                        finally:
                            record["latency_ms"] = round((time.monotonic() - started) * 1000)
                            budget.calls.append(record)
                if response.usage:
                    for key in budget.tokens:
                        budget.tokens[key] += getattr(response.usage, key, 0) or 0
                record["actual_model"] = response.model
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
        if isinstance(failure, ValidationError):
            detail = sorted(
                {e["type"] for e in failure.errors(include_input=False, include_url=False)}
            )
        elif isinstance(failure, ModelFailure):
            detail = [failure.code]
        else:
            allowed = {
                "Missing, duplicate or invented rule IDs",
                "Condition coverage mismatch",
                "Citation is not a direct rule article",
                "Evidence does not occur in the specified source",
                "Invented condition evidence",
                "Violation lacks citations or evidence",
            }
            detail = [str(failure) if str(failure) in allowed else "invalid_json_or_schema"]
        budget.validation_errors.append(
            {
                "kind": kind,
                "attempt": attempt + 1,
                "categories": detail,
                "rule_id": getattr(failure, "rule_id", None),
            }
        )
        if not attempt:
            messages = [
                *messages,
                {
                    "role": "user",
                    "content": "上次输出未通过校验，错误类别："
                    + json.dumps(detail)
                    + "，失败规则："
                    + (getattr(failure, "rule_id", None) or "见本批 Schema")
                    + "。重新检查原始材料，仅输出完整 JSON，覆盖全部 rule_id 及 condition_bindings 中 c1/c2 等条件 ID；即使不适用也不能省略条件。不得伪造引用或证据。",
                },
            ]
    raise ModelFailure(
        "invalid_model_output", "模型输出经一次修复后仍不符合结构或证据约束。"
    ) from failure
