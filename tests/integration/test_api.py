import asyncio
import io
import json
import re

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
    assert "后端拆解" in response.text
    assert "后端审核引擎" not in response.text
    assert "初审模式只查 RAG 召回法条所关联的规则" in response.text
    assert "案例库仅用于开发验证与评估准备，不参与实时裁决" in response.text
    assert "图片先提取可见文字和画面事实" in response.text
    assert "RAG 选中的可疑规则" not in response.text

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
    assert "法规切成法条，规则卡再按共享法条形成规则簇" in response.text
    assert "grid-template-columns: repeat(10, minmax(0, 1fr))" in response.text
    assert ".phase-label.prep { grid-column: 1 / 4;" in response.text
    assert ".phase-label.live { grid-column: 4 / 9;" in response.text
    assert ".phase-label.review { grid-column: 9 / -1;" in response.text
    assert "验证复盘 · 案例与方案取舍" in response.text
    assert "前期准备、实时查询和验证复盘三部分" in response.text
    assert "当前规则卡总数" in response.text
    assert "完全模式计划批次" in response.text
    assert "359 条法条一次性生成 1024 维向量索引" in response.text
    assert "用户文案的 512 字查询片段需要生成查询向量" in response.text
    assert "const batches = [" in response.text
    assert "规则查验与 RAG 汇合" in response.text
    assert "46 / 46 全部保留" in response.text
    assert "46 条规则全部检查" in response.text
    assert "本页展示完全模式" in response.text
    assert "初审模式只检查 RAG 召回法条所关联的规则" in response.text
    assert "补充搜索 · RAG 法条检索" in response.text
    retrieval_scene = response.text.split('data-scene="4"', 1)[1].split("</article>", 1)[0]
    assert retrieval_scene.index("补充搜索 · RAG 法条检索") < retrieval_scene.index(
        "当前材料的每个 512 字片段"
    )
    assert '<div class="recall-product"><b>产物</b>定向召回的补充法条</div>' in (retrieval_scene)
    assert "规则直接法条 + 补充搜索产物" in retrieval_scene
    assert "上轨" not in response.text and "下轨" not in response.text
    assert "规则卡决定：</strong>必须检查什么" in response.text
    assert "每批最多 8 条、8,000 字符" in response.text
    assert "方案取舍：为什么提供初审与完全两种模式" in response.text
    assert "46 条规则全部查验" in response.text
    assert "使用 RAG 检索出法条再进行查验" in response.text
    assert "产品化选择：两档模式" in response.text
    assert 'class="head strategy-head"' in response.text
    assert 'class="head strategy-head initial"' in response.text
    assert 'class="head strategy-head chosen"' in response.text
    assert (
        ".strategy-metric .initial { color: #176958; background: var(--green-soft);"
        in response.text
    )
    assert response.text.count('class="initial"') == 6
    assert 'content: "初审模式"' in response.text
    assert 'content: "完全模式"' in response.text
    assert 'content: "最终选择"' not in response.text
    assert 'class="strategy-grid"' not in response.text
    assert "¥0.154" in response.text
    assert "¥0.292" in response.text
    assert "qwen3.7-plus 输入 ¥2/百万 token" in response.text
    assert response.text.count("5 / 5") == 3
    # Every metric row must carry the full three-column comparison (plain /
    # initial / chosen). Asserting the absence of a substring such as
    # "<div>开发案例通过</div><div>5 / 5</div>" cannot work, because that text
    # is itself the prefix of a correct three-column row.
    metric_rows = re.findall(
        r"<div>([^<]+)</div>((?:<div[^>]*>[^<]*</div>)+)",
        response.text.split('class="strategy-metric"', 1)[1].split('class="decision-callout"', 1)[
            0
        ],
    )
    assert metric_rows, "strategy metric table must have rows"
    for label, cells in metric_rows:
        assert len(re.findall(r"<div", cells)) == 3, label
        assert 'class="initial"' in cells, label
        assert 'class="chosen"' in cells, label
    assert "两违规案例规则级发现</div><div>13 项</div>" in response.text
    assert '<div class="initial">7 项</div><div class="chosen">13 项</div>' in response.text
    assert "三种方案均有 1 个共同技术失败案例" in response.text
    assert "⑨ 案例及结论" in response.text
    assert 'aria-label="审核结论及其含义"' in response.text
    assert ".decision-legend { display: grid; grid-template-columns: 1fr;" in response.text
    assert response.text.index('aria-label="三方案对照开发案例"') < response.text.index(
        'aria-label="审核结论及其含义"'
    )
    assert "is_compliant = no" in response.text
    assert "is_compliant = yes" in response.text
    assert "is_compliant = null" in response.text
    assert "技术故障不属于审核结论" in response.text
    assert "发现违规 · 审核未完成" in response.text
    assert "明显违规" in response.text and "中性科普" in response.text
    assert '<span class="expected">不合规</span>' in response.text
    assert '<span class="expected">合规</span>' in response.text
    assert '<span class="expected">需复核</span>' in response.text
    assert '<span class="expected">non_compliant</span>' not in response.text
    assert '<span class="expected">needs_review</span>' not in response.text
    assert response.text.index("⑧ 批次并发审核") < response.text.index("⑨ 案例及结论")
    assert response.text.index("⑨ 案例及结论") < response.text.index("⑩ 方案取舍")
    assert "if (current === 7) animateDispatch();" in response.text
    assert "grid-template-columns: repeat(5, minmax(190px, 1fr))" in response.text
    assert response.text.index("按共享法条形成连通组") < response.text.index(
        "被审核文案切分为证据块"
    )
    assert "规则卡引用法条" in response.text
    assert "A 与 B 共享法条 22，因此进入同一规则簇" in response.text
    assert 'class="cluster-summary"' not in response.text
    assert 'class="article-rule-link"' in response.text
    assert 'marker-end="url(#shared-rule-arrow)"' in response.text
    assert "条文与规则组织" in response.text
    assert "规则簇在规则集发布时形成，不会在每次用户请求中重新聚类" in response.text
    assert "<strong>规则聚类</strong>" not in response.text
    assert "${ruleNames[x] || '未命名规则'}" in response.text
    assert "批次并发审核，取回结果并返回前端" in response.text
    assert "取回批次结果" in response.text
    assert "程序校验" in response.text
    assert "确定性聚合" in response.text
    assert "API 返回前端" in response.text
    assert "前端收到的是后端校验和聚合后的统一响应" in response.text
    assert "function animateReturn()" in response.text
    assert "grid-template-columns: minmax(420px, 1fr) minmax(0, 2fr)" in response.text
    assert (
        ".queue { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr))" in response.text
    )
    assert 'href="/batch-flow/report"' in response.text
    assert response.text.count('class="step"') == 9
    assert response.text.count('class="step active"') == 1
    assert response.text.count('class="scene"') == 9
    assert response.text.count('class="scene active"') == 1
    assert "步骤 1 / 10" in response.text

    csp = response.headers["Content-Security-Policy"]
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_batch_flow_report_route_serves_the_three_strategy_evidence(client):
    response = client.get("/batch-flow/report")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# 三种法规上下文策略真实对照" in response.text
    assert "仅基线 `baseline-only`" in response.text
    assert "仅 RAG `rag-only`" in response.text
    assert "两者都开 `combined`" in response.text


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
    assert "按非空行保留原句与位置" in response.text
    assert "每个证据块再按最多 512 字切片" in response.text
    assert "每个检索片段各取 Top 8 候选" in response.text
    assert "召回法条所关联的规则" in response.text
    assert "13 个裁决批次" in response.text
    assert "查询向量按每 10 个检索片段分批调用" in response.text
    assert "案例库不进入实时 Prompt，也不参与裁决" in response.text
    assert "效果数据需以独立评估报告为准" in response.text
    assert "裁决 <strong>25 次</strong>" not in response.text
    assert "检索（1 次调用）" not in response.text

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


def test_frontend_uses_initial_review_wording_and_chinese_rule_names(client):
    page = client.get("/").text
    script = client.get("/static/app.js").text
    assert ">初审</button>" in page
    assert "简单模式" not in page and "简单模式" not in script
    assert "rule_display_names" in script
    assert "rule_required_information" in script
    assert "review_type_display_names" in script
    assert "事项：${typeName}" in script
    assert "疑似共违反${total}条规则" in script
    assert "details('全部规则')" in script
    assert "details('其余规则')" not in script
    assert "暂未形成结论" in script
    assert "部分规则的审核结果不够可靠，请重新审核。" in script


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
    assert concise["meta"]["rule_selection_mode"] == "retrieved"
    assert strict["meta"]["rule_selection_mode"] == "all"
    assert len(concise["meta"]["selected_rule_ids"]) <= len(strict["meta"]["selected_rule_ids"])
    assert strict["meta"]["omitted_rule_ids"] == []
    names = concise["meta"]["rule_display_names"]
    assert len(names) == concise["coverage"]["total"] == 46
    assert names["disclose_material_policy_terms_and_restrictions"] == ("重要保单条款与限制披露")
    required = concise["meta"]["rule_required_information"]
    assert required["suitability_and_consumer_demand"][:2] == [
        "消费者需求分析记录",
        "风险承受能力与支付能力评估记录",
    ]
    assert concise["meta"]["review_type_display_names"]["needs_context"] == "需补充材料"


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
    assert last["completed_rules"] == last["total_rules"] > 0
    assert last["completed_batches"] == last["total_batches"] > 0
    judge_events = [json.loads(payload) for payload in events["progress"] if '"judge"' in payload]
    assert judge_events and all(
        event["rule_selection_mode"] == "retrieved" for event in judge_events
    )

    # Exactly one result frame, carrying the same payload the blocking call returns.
    assert len(events["result"]) == 1
    streamed = json.loads(events["result"][0])
    assert last["total_rules"] == len(streamed["meta"]["selected_rule_ids"])
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
