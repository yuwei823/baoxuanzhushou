import json

import pytest
from fastapi.testclient import TestClient

from insurance_audit.api import create_app
from insurance_audit.config import Settings
from insurance_audit.models.bailian import ModelFailure
from insurance_audit.models.mock import MockProvider


@pytest.mark.parametrize(
    "code,http_status",
    [("budget_exhausted", 504), ("invalid_model_output", 502), ("model_auth_error", 503)],
)
def test_text_api_failure_matrix_and_sanitized_metadata(code, http_status, caplog):
    class Failed(MockProvider):
        async def call(self, *args, **kwargs):
            raise ModelFailure(code, "模拟失败")

    with TestClient(create_app(Settings(_env_file=None, audit_mock=True), Failed())) as client:
        response = client.post("/api/v1/audits", files={"text": (None, "private_marker_87321")})
    assert response.status_code == http_status
    assert response.json()["decision"] is None
    assert response.json()["coverage"]["total"] == 34
    assert "private_marker_87321" not in caplog.text
    assert response.json()["trace_id"] in caplog.text


def test_text_api_partial_violation_is_200_with_failed_rules():
    class Partial(MockProvider):
        async def call(self, kind, messages, budget, **kwargs):
            cards = json.loads(messages[1]["content"])["rules"]
            if any(c["rule_id"] == "marketing_message_optout" for c in cards):
                raise ModelFailure("budget_exhausted", "模拟后续批次失败")
            return await super().call(kind, messages, budget, **kwargs)

    with TestClient(create_app(Settings(_env_file=None, audit_mock=True), Partial())) as client:
        r = client.post("/api/v1/audits", files={"text": (None, "监管部门担保收益")})
    assert r.status_code == 200
    assert r.json()["status"] == "partial" and r.json()["decision"] == "non_compliant"
    assert any(rule["status"] == "failed" for rule in r.json()["coverage"]["rules"])
