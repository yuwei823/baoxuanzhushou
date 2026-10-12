import json

from insurance_audit.models.bailian import Bailian, Budget, ModelFailure, structured
from insurance_audit.schemas import VisionOutput
from insurance_audit.uploads import validate_image
from insurance_audit.workflow import vision_messages


async def probe(settings):
    provider = Bailian(settings)
    budget = Budget(settings.audit_timeout_seconds, settings.audit_max_model_attempts)
    result = {"mock": False, "configured": settings.configured, "text": {}, "vision": {}}
    try:
        try:
            raw = await provider.call(
                "text",
                [
                    {"role": "system", "content": "只输出 JSON。"},
                    {"role": "user", "content": '返回 {"ok":true}'},
                ],
                budget,
                max_tokens=300,
            )
            result["text"] = {
                "model": settings.bailian_text_model,
                "json_valid": json.loads(raw).get("ok") is True,
            }
        except (ModelFailure, ValueError) as error:
            result["text"] = {"error": getattr(error, "code", "invalid_json")}
        try:
            path = settings.project_root / "src/insurance_audit/static/demo-1.jpg"
            image = validate_image(path.read_bytes(), "image_1", "image/jpeg")
            extracted = await structured(
                provider, "vision", vision_messages(image), VisionOutput, budget
            )
            result["vision"] = {
                "model": settings.bailian_vision_model,
                "schema_valid": True,
                "contains_expected_text": any("友邦保险" in b.text for b in extracted.text_blocks),
                "extracted_demo_text": [b.text for b in extracted.text_blocks],
            }
        except (ModelFailure, OSError) as error:
            result["vision"] = {"error": getattr(error, "code", "fixture_unavailable")}
        result["attempts"], result["token_usage"], result["calls"] = (
            budget.attempts,
            budget.tokens,
            budget.calls,
        )
        return result
    finally:
        await provider.close()
