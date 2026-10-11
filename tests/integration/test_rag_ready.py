from fastapi.testclient import TestClient

from insurance_audit.api import create_app
from insurance_audit.config import Settings
from insurance_audit.models.mock import MockProvider


def test_hybrid_missing_index_is_not_ready_and_never_calls_models(monkeypatch):
    def missing(*args):
        raise FileNotFoundError("index missing")

    monkeypatch.setattr("insurance_audit.retrieval.load_index", missing)
    app = create_app(
        Settings(_env_file=None, audit_mock=True, retrieval_mode="hybrid"), MockProvider()
    )
    with TestClient(app) as client:
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["vector_index_ready"] is False
        assert response.json()["retrieval_mode"] == "hybrid"
        assert client.post("/api/v1/audits", files={"text": (None, "测试")}).status_code == 503
