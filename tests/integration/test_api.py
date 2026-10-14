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
    corpus = client.app.state.corpus
    assert client.get("/api/v1/rulesets/current").json()["rule_count"] == len(corpus.rules)
    assert client.get("/api/v1/articles/not-known").status_code == 404
    assert client.get("/").status_code == 200
    assert "frame-ancestors 'none'" in client.get("/").headers["Content-Security-Policy"]


def test_intro_route_serves_the_self_contained_deck_with_a_relaxed_csp(client):
    response = client.get("/intro")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "保宣合规助手" in response.text

    # The deck carries inline style and script, so it needs 'unsafe-inline'.
    csp = response.headers["Content-Security-Policy"]
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    # Relaxing those must not widen anything else.
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "img-src 'self' blob: data:" in csp


def test_batch_flow_route_serves_the_animation_with_a_relaxed_csp(client):
    response = client.get("/batch-flow")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "法规如何入库，文案如何进入模型" in response.text
    assert "前期准备 · 法规或规则集变更时执行一次" in response.text
    assert "实时查询 · 每次用户提交文案时执行" in response.text
    assert "4 部法规按“整条法条”切成 359 个稳定块" in response.text
    assert "359 条法条一次性生成 1024 维向量索引" in response.text
    assert "此时只为用户片段调用 Embedding，法条向量直接复用" in response.text
    assert "const batches = [" in response.text
    assert "RAG 不决定" in response.text
    assert "每批最多 8 条、8,000 字符" in response.text

    csp = response.headers["Content-Security-Policy"]
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_only_the_presentation_pages_relax_the_csp(client):
    # The app itself must never allow inline style or script.
    for path in ("/", "/api/v1/rulesets/current"):
        csp = client.get(path).headers["Content-Security-Policy"]
        assert "'unsafe-inline'" not in csp, path


def test_workflow_route_serves_the_diagram_with_its_cdn_fallback(client):
    response = client.get("/workflow")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "端到端流程图" in response.text
    # Mermaid source is inlined and rendered client-side.
    assert "flowchart TD" in response.text
    assert "mermaid.min.js" in response.text

    csp = response.headers["Content-Security-Policy"]
    assert "style-src 'self' 'unsafe-inline'" in csp
    # Only this page may load the CDN copy of the library.
    assert "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;" in csp
    assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp


def test_only_the_workflow_page_may_reach_the_cdn(client):
    for path in ("/", "/intro", "/batch-flow", "/api/v1/rulesets/current"):
        csp = client.get(path).headers["Content-Security-Policy"]
        assert "jsdelivr" not in csp, path


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


def test_input_page_enforces_the_stricter_frontend_character_limit(client):
    # The page intentionally stays below the API's 10,000-code-point ceiling
    # and counts Unicode code points so emoji do not consume two positions.
    page = client.get("/").text
    assert 'id="counter"' in page and "5,000" in page
    script = client.get("/static/app.js").text
    assert "const MAX_TEXT = 5000" in script
    assert "alert(" in script and "5,000" in script
    # Both the paste handler and the submit guard share the limit.
    assert script.count("MAX_TEXT") >= 3


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


def test_api_is_open_by_default(client):
    assert client.post("/api/v1/audits", files={"text": (None, "测试")}).status_code == 200


def test_depth_defaults_to_concise_and_accepts_strict(client):
    concise = client.post("/api/v1/audits", files={"text": (None, "监管部门担保收益")}).json()
    assert concise["meta"]["depth"] == "concise"
    strict = client.post(
        "/api/v1/audits",
        files={"text": (None, "监管部门担保收益"), "depth": (None, "strict")},
    ).json()
    assert strict["meta"]["depth"] == "strict"
    # Strict surfaces at least as many review items, and never changes the violations.
    assert len(strict["review_items"]) >= len(concise["review_items"])
    assert len(strict["violations"]) == len(concise["violations"])


def test_unknown_depth_is_rejected(client):
    response = client.post(
        "/api/v1/audits", files={"text": (None, "测试"), "depth": (None, "deep")}
    )
    assert response.status_code == 422


def test_stream_emits_progress_then_the_same_result_as_the_blocking_endpoint(client):
    blocking = post(client, "监管部门担保收益").json()

    with client.stream(
        "POST", "/api/v1/audits/stream", files={"text": (None, "监管部门担保收益")}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    frames = [f for f in body.split("\n\n") if f.strip()]
    events = {}
    for frame in frames:
        name = frame.split("\n", 1)[0].removeprefix("event: ")
        events.setdefault(name, []).append(frame.split("data: ", 1)[1])

    # Progress is reported before the verdict, and converges on the rule total.
    assert events["progress"], "stream must report progress"
    first = json.loads(events["progress"][0])
    last = json.loads(events["progress"][-1])
    assert first["completed_rules"] == 0
    assert last["completed_rules"] == last["total_rules"] == len(client.app.state.corpus.rules)
    assert last["completed_batches"] == last["total_batches"] > 0

    # Exactly one result frame, carrying the same payload the blocking call returns.
    assert len(events["result"]) == 1
    streamed = json.loads(events["result"][0])
    assert streamed["status"] == blocking["status"]
    assert streamed["decision"] == blocking["decision"]
    assert len(streamed["violations"]) == len(blocking["violations"])
    assert streamed["coverage"]["total"] == blocking["coverage"]["total"]


def test_stream_reports_image_observations_before_the_result(client):
    with client.stream(
        "POST",
        "/api/v1/audits/stream",
        files=[("text", (None, "请结合图片审核。")), ("images", ("a.png", png(), "image/png"))],
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    frames = [f for f in body.split("\n\n") if f.strip()]
    events = {}
    for frame in frames:
        name = frame.split("\n", 1)[0].removeprefix("event: ")
        events.setdefault(name, []).append(frame.split("data: ", 1)[1])

    observations = [json.loads(p) for p in events["progress"] if '"observation"' in p]
    assert observations, "an image audit must stream what the model saw"
    first = observations[0]
    assert first["image_id"]
    assert isinstance(first["observations"], list)
    assert "visible_text" in first and "unreadable_regions" in first

    # Observations must arrive before the verdict, so the UI can show them live.
    assert body.index('"observation"') < body.index("event: result")


def test_stream_rejects_a_non_multipart_body(client):
    response = client.post(
        "/api/v1/audits/stream",
        content="text=测试",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_audit_concurrency_cap_rejects_while_busy():
    started, release = asyncio.Event(), asyncio.Event()

    class Slow(MockProvider):
        async def call(self, *args, **kwargs):
            started.set()
            await release.wait()
            return await super().call(*args, **kwargs)

    app = create_app(Settings(_env_file=None, audit_mock=True, audit_max_concurrency=1), Slow())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        first = asyncio.create_task(
            client.post("/api/v1/audits", files={"text": (None, "监管部门担保收益")})
        )
        await asyncio.wait_for(started.wait(), 3)
        second = await client.post("/api/v1/audits", files={"text": (None, "测试")})
        assert second.status_code == 429
        release.set()
        assert (await first).status_code == 200
