import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from insurance_audit.config import Settings
from insurance_audit.models.bailian import Bailian
from insurance_audit.models.mock import MockProvider
from insurance_audit.retrieval import Corpus
from insurance_audit.schemas import AuditContext, AuditRequest
from insurance_audit.service import AuditService
from insurance_audit.uploads import MAX_TOTAL, InputError, read_uploads

LOGGER = logging.getLogger("insurance_audit.metadata")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler())
STATIC = Path(__file__).with_name("static")

# Self-contained presentation pages. /intro also runs inline script; the
# workflow page is style-only, so it does not need script relaxed.
INLINE_SCRIPT_PAGES = {"/intro"}
INLINE_STYLE_PAGES = {"/intro", "/workflow"}

# /workflow loads Mermaid from a CDN first and falls back to the bundled copy.
# Only this page may fetch that one script origin; everything else stays 'self'.
CDN_SCRIPT_ORIGIN = "https://cdn.jsdelivr.net"


def error_response(message, status, code="invalid_request"):
    return JSONResponse(
        {
            "status": "failed",
            "decision": None,
            "is_compliant": None,
            "trace_id": str(uuid4()),
            "summary": message,
            "errors": [{"stage": "input", "code": code, "message": message}],
        },
        status_code=status,
    )


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        maximum = MAX_TOTAL + 1024 * 1024
        total = 0

        async def bounded():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > maximum:
                raise InputError("请求体超过大小限制。", 413)
            return message

        await self.app(scope, bounded, send)


def create_app(settings=None, provider=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifecycle(app):
        yield
        await app.state.provider.close()

    application = FastAPI(title="保宣合规助手", lifespan=lifecycle)
    application.add_middleware(BodyLimit)
    application.state.settings = settings
    application.state.provider = provider or (
        MockProvider() if settings.audit_mock else Bailian(settings)
    )
    audit_slots = asyncio.Semaphore(settings.audit_max_concurrency)
    try:
        application.state.corpus = Corpus(settings)
        application.state.startup_error = None
    except (OSError, ValueError, KeyError):
        application.state.corpus = None
        application.state.startup_error = "当前规则集未发布或语料校验未通过。"
    corpus = application.state.corpus
    service = AuditService(settings, corpus, application.state.provider) if corpus else None

    @application.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Static presentation pages carry inline style, so they need
        # 'unsafe-inline' for style. Only /intro also runs inline script. Every
        # other route keeps the strict policy; hashes are not usable because the
        # files are edited by hand and would need a new hash each time.
        path = request.url.path
        if path == "/workflow":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' blob: data:; "
                "style-src 'self' 'unsafe-inline'; "
                f"script-src 'self' 'unsafe-inline' {CDN_SCRIPT_ORIGIN}; "
                "connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
            )
        elif path in INLINE_SCRIPT_PAGES:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' blob: data:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
            )
        elif path in INLINE_STYLE_PAGES:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' blob: data:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                "connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
            )
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(InputError)
    async def handle_input(request, error):
        return error_response(str(error), error.status)

    @application.exception_handler(HTTPException)
    async def handle_http(request, error):
        return error_response("请求格式或资源无效。", error.status_code)

    @application.get("/healthz")
    async def health():
        return {"status": "ok"}

    @application.get("/readyz")
    async def ready():
        success = bool(corpus and settings.configured)
        return JSONResponse(
            {
                "ready": success,
                "corpus_ready": bool(corpus),
                "model_configured": settings.configured,
                "mock": settings.audit_mock,
                "retrieval_mode": settings.retrieval_mode,
                "vector_index_ready": bool(corpus and corpus.vectors is not None),
            },
            status_code=200 if success else 503,
        )

    @application.get("/api/v1/rulesets/current")
    async def current():
        if not corpus:
            return error_response(application.state.startup_error, 503, "corpus_not_ready")
        return {
            "ruleset_id": settings.ruleset_id,
            "ruleset_mode": "official_snapshot",
            "rule_count": len(corpus.rules),
            "retrieval_mode": settings.retrieval_mode,
            "embedding_model": settings.embedding_model if corpus.vectors is not None else None,
            "embedding_dimensions": settings.embedding_dimensions
            if corpus.vectors is not None
            else None,
            "article_count": len(corpus.articles),
            "documents": [
                {"title": d["title"], "document_status": d["document_status"]}
                for d in corpus.documents.values()
            ],
            "mock": settings.audit_mock,
            "model_configured": settings.configured,
            "models": {
                "text": settings.bailian_text_model,
                "vision": settings.bailian_vision_model,
            },
            "excluded_sources": corpus.manifest.get("excluded_sources", []),
        }

    @application.get("/api/v1/articles/{article_id}")
    async def article(article_id: str):
        if not corpus:
            return error_response("语料未就绪。", 503)
        if article_id not in corpus.articles:
            return error_response("未找到当前规则集条文。", 404)
        return corpus.articles[article_id]

    async def parse_audit_form(request):
        """Parse and validate the multipart audit payload shared by both endpoints."""
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("multipart/form-data"):
            raise InputError("请使用 multipart/form-data 上传图文。", 415)
        try:
            async with request.form(max_files=5, max_fields=4, max_part_size=100 * 1024) as form:
                if set(form) - {"text", "context", "images", "images[]", "depth"}:
                    raise InputError("存在不支持的字段。")
                if (
                    len(form.getlist("text")) > 1
                    or len(form.getlist("context")) > 1
                    or len(form.getlist("depth")) > 1
                ):
                    raise InputError("text、context 和 depth 不可重复。")
                files = form.getlist("images") + form.getlist("images[]")
                if form.getlist("images") and form.getlist("images[]"):
                    raise InputError("请统一使用 images 字段，以保留上传顺序。")
                if any(not isinstance(f, UploadFile) for f in files):
                    raise InputError("图片只能使用上传文件，不能使用 URL 或路径。")
                context = AuditContext.model_validate_json(form.get("context") or "{}")
                audit_request = AuditRequest(
                    text=form.get("text") or "",
                    context=context,
                    depth=form.get("depth") or "concise",
                )
                if not audit_request.text.strip() and not files:
                    raise InputError("请输入文本或至少上传一张图片。")
                images = await read_uploads(files)
            # Multipart temporary files are already closed; decoded bytes live only for this request.
        except (ValidationError, TypeError, ValueError) as error:
            if isinstance(error, InputError):
                raise
            raise InputError("参数无效：检查上下文枚举与文本长度（最多 10,000 字）。") from error
        return audit_request, images

    def audit_status_code(result):
        if result.status != "failed":
            return 200
        codes = {e.code for e in result.errors}
        return (
            504 if "budget_exhausted" in codes else 502 if "invalid_model_output" in codes else 503
        )

    def log_audit(result):
        LOGGER.info(
            json.dumps(
                {
                    "trace_id": result.trace_id,
                    "ruleset_id": result.ruleset_id,
                    "status": result.status,
                    "error_codes": [e.code for e in result.errors],
                    "coverage": {
                        "total": result.coverage.total,
                        "checked": result.coverage.checked,
                    },
                    **result.meta,
                },
                ensure_ascii=False,
            )
        )

    @application.post("/api/v1/audits")
    async def audit(request: Request):
        if not service or not settings.configured:
            return error_response(
                application.state.startup_error or "请配置百炼密钥与地域 Base URL。",
                503,
                "not_ready",
            )
        audit_request, images = await parse_audit_form(request)

        if audit_slots.locked():
            return error_response("审核并发已满，请稍后重试。", 429, "busy")

        async def perform(audit_request, images):
            task = asyncio.create_task(service.review(audit_request, images))

            client_disconnected = False

            async def disconnected():
                nonlocal client_disconnected
                while not task.done():
                    if await request.is_disconnected():
                        client_disconnected = True
                        task.cancel()
                        return
                    await asyncio.sleep(0.2)

            monitor = asyncio.create_task(disconnected())
            try:
                result = await task
            except asyncio.CancelledError:
                if client_disconnected:
                    return JSONResponse({"status": "cancelled", "decision": None}, status_code=499)
                raise
            finally:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                images.clear()
            log_audit(result)
            return JSONResponse(
                result.model_dump(mode="json"), status_code=audit_status_code(result)
            )

        async with audit_slots:
            return await perform(audit_request, images)

    @application.post("/api/v1/audits/stream")
    async def audit_stream(request: Request):
        """Same audit as /api/v1/audits, streamed as Server-Sent Events.

        Emits `progress` events while rules are being judged, then one `result`
        event carrying the identical payload the blocking endpoint returns.
        Progress is advisory: a failure to deliver it never fails the audit.
        """
        if not service or not settings.configured:
            return error_response(
                application.state.startup_error or "请配置百炼密钥与地域 Base URL。",
                503,
                "not_ready",
            )
        audit_request, images = await parse_audit_form(request)

        if audit_slots.locked():
            return error_response("审核并发已满，请稍后重试。", 429, "busy")

        queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(event):
            await queue.put(("progress", event))

        async def run_audit():
            try:
                result = await service.review(audit_request, images, on_progress=on_progress)
                log_audit(result)
                await queue.put(("result", result.model_dump(mode="json")))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                LOGGER.exception("audit stream failed")
                await queue.put(("error", {"message": type(error).__name__}))
            finally:
                images.clear()
                await queue.put(("end", None))

        async def events():
            async with audit_slots:
                task = asyncio.create_task(run_audit())
                try:
                    while True:
                        try:
                            kind, payload = await asyncio.wait_for(queue.get(), timeout=15)
                        except TimeoutError:
                            # Comment frame keeps proxies and browsers from idling out.
                            yield ": keep-alive\n\n"
                            continue
                        if kind == "end":
                            break
                        yield f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @application.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @application.get("/intro")
    async def intro():
        """Self-contained demo deck, served as a plain page."""
        return FileResponse(STATIC / "intro.html")

    @application.get("/workflow")
    async def workflow():
        """End-to-end flow diagram, rendered as inline SVG (no JS, no CDN)."""
        return FileResponse(STATIC / "workflow.html")

    application.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
    return application


app = create_app()
