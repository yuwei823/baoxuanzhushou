import asyncio
import io
import json

import httpx
import pytest
from PIL import Image
from starlette.datastructures import UploadFile
from starlette.requests import Request

from insurance_audit.api import create_app
from insurance_audit.config import Settings
from insurance_audit.models.mock import MockProvider
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import AuditRequest
from insurance_audit.service import AuditService
from insurance_audit.uploads import validate_image


def image_bytes():
    data = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(data, "PNG")
    return data.getvalue()


@pytest.mark.asyncio
async def test_conflicting_images_preserve_both_claims_and_observation_sources():
    seen = []

    class Vision(MockProvider):
        async def call(self, kind, messages, budget, **kwargs):
            if kind == "vision":
                first = "image_1" in messages[1]["content"][0]["text"]
                return json.dumps(
                    {
                        "text_blocks": [{"text": "收益保证" if first else "收益不保证"}],
                        "visual_observations": ["人物插画，身份未知"],
                        "unreadable_regions": [],
                        "extraction_warnings": [],
                    }
                )
            seen.append(json.loads(messages[1]["content"])["sources"])
            return await super().call(kind, messages, budget, **kwargs)

    settings = Settings(_env_file=None, audit_mock=True)
    result = await AuditService(settings, Corpus(settings), Vision()).review(
        AuditRequest(text="两幅材料互相矛盾"),
        [validate_image(image_bytes(), f"image_{n}") for n in (1, 2)],
    )
    assert [i.visible_text for i in result.images] == ["收益保证", "收益不保证"]
    assert seen
    for batch in seen:
        assert {"收益保证", "收益不保证"} <= {s["text"] for s in batch}
        assert any(s["source_type"] == "image_observation" for s in batch)


@pytest.mark.asyncio
async def test_disconnect_cancels_model_after_upload_closed(monkeypatch):
    started, cancelled = asyncio.Event(), asyncio.Event()
    closed = []
    original = UploadFile.close

    async def close(upload):
        await original(upload)
        closed.append(upload.file.closed)

    async def disconnected(request):
        return started.is_set()

    class Slow(MockProvider):
        async def call(self, *args, **kwargs):
            assert closed and all(closed)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    monkeypatch.setattr(UploadFile, "close", close)
    monkeypatch.setattr(Request, "is_disconnected", disconnected)
    app = create_app(Settings(_env_file=None, audit_mock=True), Slow())
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with asyncio.timeout(3):
            response = await client.post(
                "/api/v1/audits", files={"images": ("image.png", image_bytes(), "image/png")}
            )
        assert response.status_code == 499 and response.json()["decision"] is None
    assert started.is_set() and cancelled.is_set() and all(closed)
