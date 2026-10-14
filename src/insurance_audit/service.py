import asyncio
import json
import logging
import time
from collections import Counter
from uuid import uuid4

from insurance_audit.models.bailian import Budget, ModelFailure, structured
from insurance_audit.retrieval import related_rule_ids
from insurance_audit.rule_names import (
    REVIEW_TYPE_DISPLAY_NAMES,
    display_names_for,
    required_information_for,
)
from insurance_audit.schemas import (
    AuditError,
    AuditResponse,
    Coverage,
    JudgeOutput,
    ReviewItem,
    RuleLedger,
    VisionOutput,
)
from insurance_audit.vector_index import digest
from insurance_audit.workflow import (
    PROMPT_VERSION,
    citation_repair_context,
    image_sources,
    judge_messages,
    resolve_condition_ids,
    text_sources,
    verify,
    vision_messages,
)

LOGGER = logging.getLogger("insurance_audit.service")


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

    async def review(self, request, images=(), on_progress=None):
        """Run one audit.

        ``on_progress`` is an optional async callable receiving a small dict
        describing completed work. It lets a streaming transport report real
        progress; it must never raise, since a progress failure must not fail
        an audit.
        """

        async def progress(**event):
            if on_progress is None:
                return
            try:
                await on_progress(event)
            except Exception:
                LOGGER.warning("progress callback failed", exc_info=True)

        started = time.monotonic()
        budget = Budget(self.settings.audit_timeout_seconds, self.settings.audit_max_model_attempts)
        sources = text_sources(request.text)
        extracted, errors, reviews, violations, ledger = [], [], [], [], []
        assessment_trace = []
        await progress(
            stage="start",
            total_rules=len(self.corpus.rules),
            planned_rules=len(self.corpus.rules),
            total_batches=0,
            completed_rules=0,
            completed_batches=0,
        )
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
        await progress(
            stage="extract",
            total_rules=len(self.corpus.rules),
            planned_rules=len(self.corpus.rules),
            total_batches=0,
            completed_rules=0,
            completed_batches=0,
            total_images=len(images),
        )
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
            # Stream what the model saw so the UI can show it while judging runs.
            await progress(
                stage="observation",
                image_id=image.image_id,
                total_images=len(images),
                observations=list(value.visual_observations),
                visible_text=(image_result.visible_text or "").strip(),
                unreadable_regions=list(value.unreadable_regions),
            )
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
        await progress(
            stage="retrieve",
            total_rules=len(self.corpus.rules),
            planned_rules=len(self.corpus.rules),
            total_batches=0,
            completed_rules=0,
            completed_batches=0,
        )
        retrieved, retrieval_trace, retrieval_error = [], [], None
        retrieval_executed = self.settings.rag_batch_context_mode != "none"
        if retrieval_executed:
            try:
                retrieved, retrieval_trace = await self.corpus.search(
                    sources, self.provider, budget
                )
            except ModelFailure as error:
                retrieval_error = error
        stages["retrieval_ms"] = round((time.monotonic() - retrieval_started) * 1000)
        context_trace = []
        all_rule_ids = list(self.corpus.rules)
        rule_selection_mode = "retrieved" if request.depth == "concise" else "all"
        if rule_selection_mode == "retrieved":
            if not retrieval_executed:
                retrieval_error = ModelFailure(
                    "retrieval_disabled", "初审模式需要启用 RAG 法条检索。"
                )
            selected_rule_ids = (
                related_rule_ids(self.corpus.rules, retrieved)
                if retrieval_error is None
                else []
            )
        else:
            selected_rule_ids = all_rule_ids
        selected_rule_id_set = set(selected_rule_ids)
        omitted_rule_ids = [rid for rid in all_rule_ids if rid not in selected_rule_id_set]

        judge_started = time.monotonic()
        batches = list(
            self.corpus.batches(
                self.settings.batch_rule_count,
                retrieved,
                rule_ids=selected_rule_ids,
            )
        )
        await progress(
            stage="judge",
            rule_selection_mode=rule_selection_mode,
            total_rules=len(selected_rule_ids),
            planned_rules=sum(len(cards) for cards, _ in batches),
            total_batches=len(batches),
            completed_rules=0,
            completed_batches=0,
        )
        done_rules = 0
        done_batches = 0
        progress_lock = asyncio.Lock()

        async def judge_batch(cards, articles):
            nonlocal done_rules, done_batches
            try:
                if retrieval_error:
                    raise retrieval_error
                # Direct and supporting articles are mandatory.  Retrieved
                # articles are optional augmentation. Targeted mode re-ranks
                # them against this batch before applying the prompt budget.
                mandatory_articles = articles
                articles, selected_retrieved, dropped_retrieved = (
                    self.corpus.budgeted_context_articles(
                        mandatory_articles,
                        retrieved,
                        cards,
                        self.settings.rag_batch_context_mode,
                        self.settings.rag_batch_retrieved_limit,
                        self.settings.rag_batch_retrieved_max_characters,
                    )
                )
                messages = judge_messages(
                    request, sources, cards, articles, readable, selected_retrieved
                )
                prompt_characters = len(json.dumps(messages, ensure_ascii=False))
                if prompt_characters > self.settings.batch_max_characters:
                    # The conservative article budget normally prevents this,
                    # but unusually large material may consume the remaining
                    # prompt. Remove the lowest-ranked optional hits one by one
                    # before splitting mandatory rules or reporting a true
                    # indivisible overflow.
                    optional_selected = [
                        aid for aid in selected_retrieved if aid not in mandatory_articles
                    ]
                    while (
                        prompt_characters > self.settings.batch_max_characters
                        and optional_selected
                    ):
                        # Remove enough low-ranked article text to cover the
                        # measured excess, then serialize once.  Rebuilding the
                        # entire prompt after every single article made the
                        # overflow safeguard itself expensive on large unions.
                        excess = prompt_characters - self.settings.batch_max_characters
                        removed_characters = 0
                        removed_ids = []
                        while optional_selected and removed_characters < excess + 512:
                            aid = optional_selected.pop()
                            removed_characters += len(
                                self.corpus.articles[aid]["original_text"]
                            )
                            articles.pop(aid, None)
                            selected_retrieved.remove(aid)
                            removed_ids.append(aid)
                        dropped_retrieved = [
                            *reversed(removed_ids),
                            *dropped_retrieved,
                        ]
                        messages = judge_messages(
                            request,
                            sources,
                            cards,
                            articles,
                            readable,
                            selected_retrieved,
                        )
                        prompt_characters = len(json.dumps(messages, ensure_ascii=False))

                if prompt_characters > self.settings.batch_max_characters:
                    # Split rules without truncating material or mandatory law text.
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
                                await judge_batch(
                                    half, {aid: self.corpus.articles[aid] for aid in ids}
                                )
                            )
                        return combined
                    raise ModelFailure(
                        "context_budget_exceeded", "完整材料与规则超过单批上下文预算，未截断。"
                    )
                context_trace.append(
                    {
                        "rule_ids": [c["rule_id"] for c in cards],
                        "article_ids": sorted(articles),
                        "retrieved_article_ids": selected_retrieved,
                        "dropped_retrieved_article_ids": dropped_retrieved,
                        "retrieval_context_mode": self.settings.rag_batch_context_mode,
                        "retrieved_optional_limit": self.settings.rag_batch_retrieved_limit,
                        "retrieved_optional_max_characters": (
                            self.corpus.article_budget
                            if self.settings.rag_batch_context_mode == "global"
                            else self.settings.rag_batch_retrieved_max_characters
                            if self.settings.rag_batch_context_mode == "targeted"
                            else 0
                        ),
                        "prompt_characters": prompt_characters,
                    }
                )
                result = await structured(
                    self.provider,
                    "text",
                    messages,
                    JudgeOutput,
                    budget,
                    validate=lambda value: resolve_condition_ids(value, cards, sources),
                    max_tokens=12000,
                    repair_context=citation_repair_context(cards, articles),
                )
                return [(cards, result, None)]
            except ModelFailure as error:
                return [(cards, None, error)]
            finally:
                # Count the batch as finished whether it succeeded or failed, so
                # the reported total always converges on the planned rule count.
                async with progress_lock:
                    done_batches += 1
                    done_rules += len(cards)
                    await progress(
                        stage="judge",
                        rule_selection_mode=rule_selection_mode,
                        total_rules=len(selected_rule_ids),
                        planned_rules=sum(len(cards) for cards, _ in batches),
                        total_batches=len(batches),
                        completed_rules=min(done_rules, len(selected_rule_ids)),
                        completed_batches=done_batches,
                        rule_ids=[c["rule_id"] for c in cards],
                    )

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
                    assessment_trace.append(
                        {
                            "rule_id": finding.rule_id,
                            "model_applicability": finding.applicability,
                            "model_finding": finding.finding,
                            "condition_values": [c.met for c in finding.condition_results],
                            "verified_status": record.status,
                            "verified_finding": record.finding,
                        }
                    )
                    if review:
                        reviews.append(review)
                    if violation:
                        violations.append(violation)
        if rule_selection_mode == "retrieved" and retrieval_error is not None:
            errors.append(
                AuditError(
                    stage="retrieve",
                    code=retrieval_error.code,
                    message=retrieval_error.message,
                    retryable=retrieval_error.retryable,
                    rule_ids=all_rule_ids,
                )
            )
            ledger.extend(
                RuleLedger(
                    rule_id=rule_id,
                    status="failed",
                    reason="RAG 规则选择失败，本次未执行规则判定。",
                )
                for rule_id in all_rule_ids
            )
        elif rule_selection_mode == "retrieved":
            ledger.extend(
                RuleLedger(
                    rule_id=rule_id,
                    status="not_reviewed",
                    reason="初审模式下未被 RAG 召回，本次未执行规则判定。",
                )
                for rule_id in omitted_rule_ids
            )
            reviews.append(
                ReviewItem(
                    type="limited_rule_scope",
                    reason=(
                        f"初审模式仅查验 RAG 选中的 {len(selected_rule_ids)} 条规则，"
                        f"其余 {len(omitted_rule_ids)} 条未查验。"
                    ),
                    required_information=["如需完整规则结论，请使用“完全模式”"],
                )
            )
        stages["judge_ms"] = round((time.monotonic() - judge_started) * 1000)
        await progress(
            stage="done",
            rule_selection_mode=rule_selection_mode,
            total_rules=len(selected_rule_ids),
            planned_rules=len(selected_rule_ids),
            total_batches=len(batches),
            completed_rules=len(selected_rule_ids),
            completed_batches=len(batches),
        )
        eligible = sum(
            r.status not in ("not_applicable", "out_of_scope", "not_reviewed") for r in ledger
        )
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
        elif errors and all(error.code == "invalid_model_output" for error in errors):
            summary = "本次审核未能形成可靠结论，部分规则需要重新审核。"
        else:
            summary = summaries[decision]
        shown_reviews = reviews
        response = AuditResponse(
            audit_id=str(uuid4()),
            trace_id=str(uuid4()),
            status=status,
            decision=decision,
            is_compliant=compliant,
            summary=summary,
            ruleset_id=self.settings.ruleset_id,
            violations=violations,
            review_items=shown_reviews,
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
                "workflow_version": "1.5-depth-rule-selection",
                "diagnostics_version": "queue-request-v1",
                "rule_status_counts": dict(Counter(r.status for r in ledger)),
                "transport_retry_calls": sum(c.get("transport_retry", 0) > 0 for c in budget.calls),
                "structure_repair_calls": sum(
                    c.get("structure_attempt", 0) > 0 and c.get("transport_retry", 0) == 0
                    for c in budget.calls
                ),
                "retrieval_version": "segment512-rrf60-batch-targeted-v3",
                "rag_batch_context_mode": self.settings.rag_batch_context_mode,
                "rag_batch_retrieved_limit": self.settings.rag_batch_retrieved_limit,
                "rag_batch_retrieved_max_characters": (
                    self.settings.rag_batch_retrieved_max_characters
                ),
                "index_id": digest(self.corpus.vector_manifest)
                if self.corpus.vector_manifest
                else None,
                "model_ids": {
                    "text": self.settings.bailian_text_model,
                    "vision": self.settings.bailian_vision_model,
                },
                "retrieved_article_ids": retrieved,
                "retrieval_mode": self.settings.retrieval_mode,
                "retrieval_executed": retrieval_executed,
                "depth": request.depth,
                "rule_selection_mode": rule_selection_mode,
                "selected_rule_ids": selected_rule_ids,
                "omitted_rule_ids": omitted_rule_ids,
                "rule_display_names": display_names_for(self.corpus.rules),
                "rule_required_information": required_information_for(self.corpus.rules),
                "review_type_display_names": REVIEW_TYPE_DISPLAY_NAMES,
                "hidden_review_items": len(reviews) - len(shown_reviews),
                "retrieval_trace": retrieval_trace,
                "context_trace": context_trace,
                "assessment_trace": assessment_trace,
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
