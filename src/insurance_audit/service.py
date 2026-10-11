import asyncio
import json
import time
from uuid import uuid4

from insurance_audit.models.bailian import Budget, ModelFailure, structured
from insurance_audit.schemas import (
    AuditError,
    AuditResponse,
    Coverage,
    JudgeOutput,
    ReviewItem,
    RuleLedger,
    VisionOutput,
)
from insurance_audit.workflow import (
    PROMPT_VERSION,
    image_sources,
    judge_messages,
    text_sources,
    validate_findings,
    verify,
    vision_messages,
)


def aggregate(violations, reviews, errors):
    if violations:
        return ("partial" if errors else "completed"), "non_compliant", "no"
    if errors:
        return "failed", None, None
    if any(r.blocking for r in reviews):
        return "completed", "needs_review", None
    return "completed", "compliant", "yes"


class AuditService:
    def __init__(self, settings, corpus, provider):
        self.settings, self.corpus, self.provider = settings, corpus, provider

    async def review(self, request, images=()):
        started = time.monotonic()
        budget = Budget(self.settings.audit_timeout_seconds, self.settings.audit_max_model_attempts)
        sources = text_sources(request.text)
        extracted, errors, reviews, violations, ledger = [], [], [], [], []
        warnings = (
            ["模拟演示结果：未调用真实模型，不可作为合规判断或评估成绩。"]
            if self.settings.audit_mock
            else []
        )
        stages = {}

        async def extract_one(image):
            try:
                value = await structured(
                    self.provider, "vision", vision_messages(image), VisionOutput, budget
                )
                return image, value, None
            except ModelFailure as error:
                return image, None, error

        vision_started = time.monotonic()
        results = await asyncio.gather(*(extract_one(image) for image in images))
        for image, value, error in results:
            if error:
                errors.append(
                    AuditError(
                        stage="extract",
                        code=error.code,
                        message=error.message,
                        retryable=error.retryable,
                        image_id=image.image_id,
                    )
                )
                continue
            new_sources, image_result = image_sources(
                image.image_id, value, self.settings.bailian_vision_model
            )
            sources.extend(new_sources)
            extracted.append(image_result)
            warnings.extend(value.extraction_warnings)
            if value.unreadable_regions or not (value.text_blocks or value.visual_observations):
                reviews.append(
                    ReviewItem(
                        type="unreadable_image",
                        reason=f"{image.image_id} 存在不可读或无法提取的区域。",
                        required_information=["更清晰的原图或完整文字"],
                    )
                )
        stages["extract_ms"] = round((time.monotonic() - vision_started) * 1000)
        readable = not errors and not any(r.type == "unreadable_image" for r in reviews)
        retrieval_started = time.monotonic()
        retrieved, retrieval_trace, retrieval_error = [], [], None
        try:
            retrieved, retrieval_trace = await self.corpus.search(sources, self.provider, budget)
        except ModelFailure as error:
            retrieval_error = error
        stages["retrieval_ms"] = round((time.monotonic() - retrieval_started) * 1000)
        context_trace = []

        async def judge_batch(cards, articles):
            try:
                if retrieval_error:
                    raise retrieval_error
                articles = self.corpus.context_articles(articles, retrieved)
                messages = judge_messages(request, sources, cards, articles, readable, retrieved)
                if (
                    len(json.dumps(messages, ensure_ascii=False))
                    > self.settings.batch_max_characters
                ):
                    # Caller splits by rule until the indivisible source/one-rule prompt fits.
                    if len(cards) > 1:
                        middle = len(cards) // 2
                        combined = []
                        for half in (cards[:middle], cards[middle:]):
                            ids = {
                                aid
                                for c in half
                                for aid in c["article_ids"] + c.get("supporting_article_ids", [])
                            }
                            combined.extend(
                                await judge_batch(half, {aid: articles[aid] for aid in ids})
                            )
                        return combined
                    raise ModelFailure(
                        "context_budget_exceeded", "完整材料与规则超过单批上下文预算，未截断。"
                    )
                context_trace.append(
                    {
                        "rule_ids": [c["rule_id"] for c in cards],
                        "article_ids": sorted(articles),
                        "retrieved_article_ids": list(retrieved),
                    }
                )
                result = await structured(
                    self.provider,
                    "text",
                    messages,
                    JudgeOutput,
                    budget,
                    validate=lambda value: validate_findings(value, cards, sources),
                    max_tokens=12000,
                )
                return [(cards, result, None)]
            except ModelFailure as error:
                return [(cards, None, error)]

        judge_started = time.monotonic()
        batches = list(self.corpus.batches(self.settings.batch_rule_count, retrieved))
        batch_results = await asyncio.gather(
            *(judge_batch(cards, articles) for cards, articles in batches)
        )
        for group in batch_results:
            for cards, result, error in group:
                if error:
                    errors.append(
                        AuditError(
                            stage="judge",
                            code=error.code,
                            message=error.message,
                            retryable=error.retryable,
                            rule_ids=[c["rule_id"] for c in cards],
                        )
                    )
                    ledger.extend(
                        RuleLedger(rule_id=c["rule_id"], status="failed", reason=error.message)
                        for c in cards
                    )
                    continue
                by_id = {c["rule_id"]: c for c in cards}
                for finding in result.findings:
                    record, review, violation = verify(
                        finding, by_id[finding.rule_id], sources, self.corpus, request, readable
                    )
                    ledger.append(record)
                    if review:
                        reviews.append(review)
                    if violation:
                        violations.append(violation)
        stages["judge_ms"] = round((time.monotonic() - judge_started) * 1000)
        eligible = sum(r.status not in ("not_applicable", "out_of_scope") for r in ledger)
        checked = sum(r.status == "checked" for r in ledger)
        resolved = sum(r.status == "checked" and r.finding != "uncertain" for r in ledger)
        status, decision, compliant = aggregate(violations, reviews, errors)
        summaries = {
            "compliant": "当前规则集及提交材料范围内未发现违规。",
            "needs_review": "材料或必要条件不足，需补充信息后复核。",
            "non_compliant": "发现有证据支持的违规项。",
            None: "审核遇到技术故障，未生成业务结论。",
        }
        if status == "partial":
            summary = "已发现违规，但部分检查未完成。"
        else:
            summary = summaries[decision]
        response = AuditResponse(
            audit_id=str(uuid4()),
            trace_id=str(uuid4()),
            status=status,
            decision=decision,
            is_compliant=compliant,
            summary=summary,
            ruleset_id=self.settings.ruleset_id,
            violations=violations,
            review_items=reviews,
            coverage=Coverage(
                total=len(self.corpus.rules),
                eligible=eligible,
                checked=checked,
                coverage_ratio=checked / eligible if eligible else None,
                resolved_ratio=resolved / eligible if eligible else None,
                rules=ledger,
            ),
            warnings=list(dict.fromkeys(warnings)),
            errors=errors,
            images=extracted,
            sources=sources,
            mock=self.settings.audit_mock,
            meta={
                "ruleset_hash": self.corpus.hash,
                "prompt_version": PROMPT_VERSION,
                "workflow_version": "1.0",
                "model_ids": {
                    "text": self.settings.bailian_text_model,
                    "vision": self.settings.bailian_vision_model,
                },
                "retrieved_article_ids": retrieved,
                "retrieval_mode": self.settings.retrieval_mode,
                "retrieval_trace": retrieval_trace,
                "context_trace": context_trace,
                "embedding_model": self.settings.embedding_model
                if self.settings.retrieval_mode == "hybrid"
                else None,
                "embedding_dimensions": self.settings.embedding_dimensions
                if self.settings.retrieval_mode == "hybrid"
                else None,
                "validation_errors": budget.validation_errors,
                "attempts": budget.attempts,
                "calls": budget.calls,
                "token_usage": budget.tokens,
                "stage_latency": stages,
                "latency_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return response
