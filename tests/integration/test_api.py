import asyncio
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import UploadFile

from insurance_audit.api import create_app
from insurance_audit.config import Settings
from insurance_audit.models.mock import MockProvider


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Settings(_env_file=None, audit_mock=True))) as session:
        yield session


def post(client, text="测试", context=None, files=None):
    return client.post(
        "/api/v1/audits",
        files=[
            ("text", (None, text)),
            ("context", (None, json.dumps(context or {}))),
            *(files or []),
        ],
    )


def test_metadata_and_current_article_allowlist(client):
    assert client.get("/readyz").json()["mock"]
    assert client.get("/api/v1/rulesets/current").json()["rule_count"] == 34
    assert client.get("/api/v1/articles/not-known").status_code == 404
    assert client.get("/").status_code == 200
    assert "frame-ancestors 'none'" in client.get("/").headers["Content-Security-Policy"]


@pytest.mark.parametrize(
    "text,context,files,expected",
    [
        ("", None, None, 422),
        ("x" * 10001, None, None, 422),
        ("测试", {"channel": "invented"}, None, 422),
        ("测试", None, [("images", (None, "http://example.com/a.png"))], 422),
        ("测试", None, [("images", ("fake.png", b"bad", "image/png"))], 415),
        ("测试", None, [("images", ("a.png", png(), "image/jpeg"))], 415),
        ("测试", None, [("images", ("a.png", png(), "image/png"))] * 6, 400),
        ("测试", None, [("images", ("a.png", b"x" * (10 * 1024 * 1024 + 1), "image/png"))], 413),
    ],
)
def test_upload_boundaries(client, text, context, files, expected):
    assert post(client, text, context, files).status_code == expected


def test_uploads_are_closed_on_success_and_failure(client, monkeypatch):
    closed = []
    original = UploadFile.close

    async def close(upload):
        await original(upload)
        closed.append(upload.file.closed)

    monkeypatch.setattr(UploadFile, "close", close)
    response = post(client, files=[("images", ("a.png", png(), "image/png"))])
    assert response.status_code == 200 and all(closed) and closed
    closed.clear()
    assert post(client, files=[("images", ("bad.png", b"bad", "image/png"))]).status_code == 415
    assert closed and all(closed)


def test_no_key_does_not_silently_fall_back_to_mock():
    with TestClient(
        create_app(
            Settings(_env_file=None, dashscope_api_key="", bailian_base_url="", audit_mock=False)
        )
    ) as client:
        assert client.get("/readyz").status_code == 503
        result = post(client)
        assert result.status_code == 503 and result.json()["decision"] is None


def test_body_total_limit_without_relying_on_file_extension(client):
    response = client.post(
        "/api/v1/audits",
        content=b"x" * (26 * 1024 * 1024 + 1),
        headers={"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert response.status_code == 413


def test_shared_token_guards_api_and_stays_off_by_default(client):
    assert client.post("/api/v1/audits", files={"text": (None, "测试")}).status_code == 200


def test_shared_token_guards_api_but_page_and_health_stay_open():
    settings = Settings(_env_file=None, audit_mock=True, auth_token="team-secret")
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        assert (
            client.post("/api/v1/audits", files={"text": (None, "测试")}).status_code == 401
        )
        assert (
            client.post(
                "/api/v1/audits",
                files={"text": (None, "测试")},
                headers={"Authorization": "Bearer wrong"},
            ).status_code
            == 401
        )
        ok = client.post(
            "/api/v1/audits",
            files={"text": (None, "测试")},
            headers={"Authorization": "Bearer team-secret"},
        )
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_audit_concurrency_cap_rejects_while_busy():
    started, release = asyncio.Event(), asyncio.Event()

    class Slow(MockProvider):
        async def call(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().call(*args, **kwargs)

    app = create_app(
        Settings(_env_file=None, audit_mock=True, audit_max_concurrency=1), Slow()
    )
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = asyncio.create_task(
            client.post("/api/v1/audits", files={"text": (None, "监管部门担保收益")})
        )
        await asyncio.wait_for(started.wait(), 3)
        second = await client.post("/api/v1/audits", files={"text": (None, "测试")})
        assert second.status_code == 429
        release.set()
        assert (await first).status_code == 200
