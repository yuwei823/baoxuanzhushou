from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuditContext(StrictModel):
    channel: Literal["unknown", "internet", "offline"] = "unknown"
    publisher_type: Literal[
        "unknown", "insurance_institution", "insurance_intermediary", "marketing_personnel", "other"
    ] = "unknown"
    product_type: Literal[
        "unknown", "insurance", "life_insurance", "property_insurance", "other"
    ] = "unknown"
    material_completeness: Literal["unknown", "complete", "partial"] = "unknown"


class AuditRequest(StrictModel):
    text: str = Field("", max_length=10000)
    context: AuditContext = Field(default_factory=AuditContext)
    # "concise" hides non-blocking review items so simple material is not buried in
    # caveats; "strict" surfaces every review item. Violations always show.
    depth: Literal["concise", "strict"] = "concise"


class TextBlock(StrictModel):
    text: str = Field(min_length=1, max_length=10000)


class VisionOutput(StrictModel):
    text_blocks: list[TextBlock] = Field(max_length=100)
    visual_observations: list[str] = Field(max_length=30)
    unreadable_regions: list[str] = Field(max_length=30)
    extraction_warnings: list[str] = Field(max_length=30)


class ExtractedImage(VisionOutput):
    image_id: str
    visible_text: str
    block_ids: list[str]
    model_id: str


class Source(StrictModel):
    source_id: str
    source_type: Literal["text", "image_text", "image_observation"]
    text: str
    start: int = 0
    image_id: str | None = None
    block_id: str | None = None


class EvidenceRef(StrictModel):
    source_id: str
    quote: str = Field(min_length=1)


class Condition(StrictModel):
    condition: str
    met: bool | None
    evidence_ids: list[str]


class Finding(StrictModel):
    rule_id: str
    applicability: Literal[
        "applicable",
        "not_applicable",
        "needs_context",
        "external_verification_required",
        "out_of_scope",
    ]
    finding: Literal["violation", "no_violation", "uncertain"]
    reason: str = Field(min_length=1, max_length=1000)
    condition_results: list[Condition]
    evidence: list[EvidenceRef]
    article_ids: list[str]
    absence_disclosure: str | None = None
    missing_facts: list[str]
    model_confidence: float | None = Field(default=None, ge=0, le=1)


class JudgeOutput(StrictModel):
    findings: list[Finding]


class PresentEvidence(StrictModel):
    kind: Literal["present"] = "present"
    source_type: str
    source_id: str
    quote: str
    start: int
    end: int
    image_id: str | None = None
    block_id: str | None = None


class AbsenceEvidence(StrictModel):
    kind: Literal["absence"] = "absence"
    inspected_source_ids: list[str]
    required_disclosure: str
    material_completeness: Literal["complete"] = "complete"
    completeness_source: Literal["user_declaration"] = "user_declaration"
    search_scope: str
    reason: str


Evidence = Annotated[PresentEvidence | AbsenceEvidence, Field(discriminator="kind")]


class Citation(StrictModel):
    article_id: str
    document_title: str
    document_status: str
    article_label: str
    original_text: str
    source_locator: dict


class Violation(StrictModel):
    violation_id: str
    rule_id: str
    type: str
    reason: str
    evidence: list[Evidence]
    citations: list[Citation]
    confidence: float | None
    confidence_kind: Literal["model_self_report"] = "model_self_report"


class ReviewItem(StrictModel):
    rule_id: str | None = None
    type: str
    reason: str
    blocking: bool = True
    # Advisory items still shape the verdict but are hidden in concise mode.
    advisory: bool = False
    required_information: list[str] = Field(default_factory=list)


class AuditError(StrictModel):
    stage: str
    code: str
    message: str
    retryable: bool = False
    rule_ids: list[str] = Field(default_factory=list)
    image_id: str | None = None


class RuleLedger(StrictModel):
    rule_id: str
    status: Literal[
        "checked",
        "not_applicable",
        "needs_context",
        "external_verification_required",
        "failed",
        "out_of_scope",
    ]
    finding: Literal["violation", "no_violation", "uncertain"] | None = None
    reason: str


class Coverage(StrictModel):
    total: int
    eligible: int
    checked: int
    coverage_ratio: float | None
    resolved_ratio: float | None
    rules: list[RuleLedger]


class AuditResponse(StrictModel):
    audit_id: str
    trace_id: str
    status: Literal["completed", "partial", "failed"]
    decision: Literal["compliant", "non_compliant", "needs_review"] | None
    is_compliant: Literal["yes", "no"] | None
    summary: str
    ruleset_id: str
    ruleset_mode: str = "official_snapshot"
    violations: list[Violation]
    review_items: list[ReviewItem]
    coverage: Coverage
    confidence: None = None
    confidence_kind: Literal["not_computed"] = "not_computed"
    warnings: list[str]
    errors: list[AuditError]
    images: list[ExtractedImage]
    sources: list[Source]
    mock: bool
    meta: dict
