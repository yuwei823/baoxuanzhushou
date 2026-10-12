import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from insurance_audit.evaluation.metrics import metrics
from insurance_audit.schemas import AuditContext, AuditRequest, AuditResponse


class Sample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: str
    group_id: str
    split: Literal["dev", "test"]
    text: str
    image_paths: list[str] = Field(default_factory=list)
    context: AuditContext = Field(default_factory=AuditContext)
    expected_decision: Literal["compliant", "non_compliant", "needs_review"]
    expected_categories: list[str] | None = None
    expected_article_ids: list[str] | None = None
    expected_evidence: list[dict] | None = None
    annotation_reason: str
    label_status: Literal["provisional", "human_reviewed"] = "provisional"
    reviewer: str | None = None
    provenance: str


def load_samples(path, split):
    samples = [
        Sample.model_validate_json(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not samples or any(s.split != split for s in samples):
        raise ValueError("Empty dataset or split mismatch")
    if len({s.sample_id for s in samples}) != len(samples):
        raise ValueError("Duplicate sample_id")
    if any(s.label_status == "human_reviewed" and not s.reviewer for s in samples):
        raise ValueError("Human labels require a named reviewer")
    sibling = path.with_name("test.jsonl" if split == "dev" else "dev.jsonl")
    if sibling.exists():
        others = [
            Sample.model_validate_json(line)
            for line in sibling.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if {s.group_id for s in samples} & {s.group_id for s in others}:
            raise ValueError("Cross-split group leakage")
        if {s.text.strip() for s in samples if s.text.strip()} & {
            s.text.strip() for s in others if s.text.strip()
        }:
            raise ValueError("Cross-split identical text leakage")
    return samples


def save_report(out, rows, metadata, articles):
    out.mkdir(parents=True, exist_ok=True)
    report = {"metadata": metadata, "metrics": metrics(rows, articles)}
    (out / "results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    (out / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 评估报告",
        "",
        "开发诊断；provisional 与 mock 结果均不代表专家 gold 或正式效果达标。",
        "",
        f"运行方式：{metadata['mode']}；样本：{len(rows)}；数据 SHA-256：{metadata['dataset_sha256']}",
        "",
        "| 指标 | 数值或分子/分母 |",
        "|---|---|",
    ]
    for key, value in report["metrics"].items():
        if isinstance(value, dict) and "denominator" in value:
            lines.append(
                f"| {key} | {value['value']} ({value['numerator']}/{value['denominator']}) |"
            )
        elif not isinstance(value, dict):
            lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "完整混淆矩阵、标签状态、延迟及 token 用量见 metrics.json。",
        "",
        "## 未匹配或技术失败案例",
        "",
    ]
    for row in rows:
        result = row.get("response") or {}
        if (
            result.get("decision") != row["sample"]["expected_decision"]
            or result.get("status") != "completed"
        ):
            lines.append(
                f"- {row['sample']['sample_id']}: expected={row['sample']['expected_decision']}; actual={result.get('decision')}; status={result.get('status', 'failed')}; errors={','.join(e['code'] for e in result.get('errors', [])) or row.get('runner_error', '')}"
            )
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


async def run(args):
    import io

    from starlette.datastructures import UploadFile

    from insurance_audit.config import Settings
    from insurance_audit.models.bailian import Bailian
    from insurance_audit.models.mock import MockProvider
    from insurance_audit.retrieval import Corpus
    from insurance_audit.service import AuditService
    from insurance_audit.uploads import read_uploads

    samples_path = args.samples or Path(f"data/eval/{args.split}.jsonl")
    samples = load_samples(samples_path, args.split)
    # Fixed test is reserved until label review, development freeze and G2 completion.
    if args.split == "test":
        raise ValueError("Fixed-test execution is not released: G2 and dataset review are pending")
    if args.out.exists() and any(args.out.iterdir()):
        raise ValueError("Use an empty output directory; prior results are immutable")
    if args.mock and args.variant != "bm25":
        raise ValueError("Mock provider supports bm25 only; select --variant bm25")
    settings = Settings()
    mode = "replay" if args.replay else "mock" if args.mock else "live"
    settings = settings.model_copy(update={"retrieval_mode": args.variant, "audit_mock": args.mock})
    corpus = Corpus(settings, require_index=mode == "live")
    provider = None if mode == "replay" else MockProvider() if args.mock else Bailian(settings)
    service = AuditService(settings, corpus, provider)
    historical = {}
    if args.replay:
        replay = json.loads(args.replay.read_text(encoding="utf-8"))
        for case in replay["cases"]:
            if case["sample_id"] in historical:
                raise ValueError("Duplicate replay sample ID")
            historical[case["sample_id"]] = case
    metadata = {
        "started_at_utc": datetime.now(UTC).isoformat(),
        "mode": mode,
        "split": args.split,
        "requested_variant": args.variant,
        "dataset_sha256": hashlib.sha256(samples_path.read_bytes()).hexdigest(),
        "replay_sha256": hashlib.sha256(args.replay.read_bytes()).hexdigest()
        if args.replay
        else None,
        "citation_verification_ruleset": settings.ruleset_id,
        "formal_acceptance": False,
        "run_complete": False,
        "evaluation_code_sha256": hashlib.sha256(
            Path(__file__).read_bytes() + Path(__file__).with_name("metrics.py").read_bytes()
        ).hexdigest(),
    }
    rows = []
    try:
        for sample in samples:
            row = {"sample": sample.model_dump(mode="json")}
            if args.replay:
                old = historical.get(sample.sample_id)
                if (
                    old is None
                    or old["text"] != sample.text
                    or old.get("context") != sample.context.model_dump()
                ):
                    raise ValueError(f"Replay input mismatch: {sample.sample_id}")
                result = AuditResponse.model_validate(old["response"])
                if (
                    result.ruleset_id != settings.ruleset_id
                    or result.meta.get("ruleset_hash") != corpus.hash
                ):
                    raise ValueError("Replay corpus does not match current immutable snapshot")
                row["response"] = result.model_dump(mode="json")
            else:
                started = time.monotonic()
                uploads = []
                try:
                    for rel in sample.image_paths:
                        path = (samples_path.parent / rel).resolve()
                        if not path.is_relative_to(samples_path.parent.resolve()):
                            raise ValueError("Image outside dataset directory")
                        uploads.append(
                            UploadFile(io.BytesIO(path.read_bytes()), filename=path.name)
                        )
                    images = await read_uploads(uploads)
                    response = await service.review(
                        AuditRequest(text=sample.text, context=sample.context), images
                    )
                    row["response"] = response.model_dump(mode="json")
                except Exception as error:  # noqa: BLE001 - isolate one sample; retain failure in denominator
                    # Preserve sample in denominator; never serialize provider exceptions/secrets.
                    row["runner_error"] = type(error).__name__
                    row["response"] = None
                finally:
                    for upload in uploads:
                        await upload.close()
                row["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            rows.append(row)
            save_report(args.out, rows, metadata, corpus.articles)
    finally:
        if provider is not None:
            await provider.close()
    metadata["run_complete"] = True
    return save_report(args.out, rows, metadata, corpus.articles)
