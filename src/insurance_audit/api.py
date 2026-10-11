import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
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
STATIC = Path(__file__).with_name("static")


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

    @application.post("/api/v1/audits")
    async def audit(request: Request):
        if not service or not settings.configured:
            return error_response(
                application.state.startup_error or "请配置百炼密钥与地域 Base URL。",
                503,
                "not_ready",
            )
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("multipart/form-data"):
            raise InputError("请使用 multipart/form-data 上传图文。", 415)
        try:
            async with request.form(max_files=5, max_fields=3, max_part_size=100 * 1024) as form:
                if set(form) - {"text", "context", "images", "images[]"}:
                    raise InputError("存在不支持的字段。")
                if len(form.getlist("text")) > 1 or len(form.getlist("context")) > 1:
                    raise InputError("text 和 context 不可重复。")
                files = form.getlist("images") + form.getlist("images[]")
                if form.getlist("images") and form.getlist("images[]"):
                    raise InputError("请统一使用 images 字段，以保留上传顺序。")
                if any(not isinstance(f, UploadFile) for f in files):
                    raise InputError("图片只能使用上传文件，不能使用 URL 或路径。")
                context = AuditContext.model_validate_json(form.get("context") or "{}")
                audit_request = AuditRequest(text=form.get("text") or "", context=context)
                if not audit_request.text.strip() and not files:
                    raise InputError("请输入文本或至少上传一张图片。")
                images = await read_uploads(files)
            # Multipart temporary files are already closed; decoded bytes live only for this request.
        except (ValidationError, TypeError, ValueError) as error:
            if isinstance(error, InputError):
                raise
            raise InputError("参数无效：检查上下文枚举与文本长度（最多 10,000 字）。") from error

        task = asyncio.create_task(service.review(audit_request, images))

        async def disconnected():
            while not task.done():
                if await request.is_disconnected():
                    task.cancel()
                    return
                await asyncio.sleep(0.2)

        monitor = asyncio.create_task(disconnected())
        try:
            result = await task
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
            if not task.done():
                task.cancel()
            images.clear()
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
        status_code = 200
        if result.status == "failed":
            codes = {e.code for e in result.errors}
            status_code = (
                504
                if "budget_exhausted" in codes
                else 502
                if "invalid_model_output" in codes
                else 503
            )
        return JSONResponse(result.model_dump(mode="json"), status_code=status_code)

    @application.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    application.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
    return application


app = create_app()
