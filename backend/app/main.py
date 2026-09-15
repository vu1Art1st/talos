import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.core.config import settings
from app.db import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # arq 连接池：Redis 不可用时降级为进程内执行（见 workers/dispatch.py）
    app.state.arq = None
    if not settings.DISABLE_QUEUE:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            app.state.arq = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        except Exception as exc:
            logger.warning("Redis 连接失败，后台任务将在进程内执行: %s", exc)
    yield
    if app.state.arq is not None:
        await app.state.arq.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        # 仅在调试模式暴露交互式文档，生产环境关闭以减少信息面
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _security_headers(request, call_next):
        # 阻止浏览器 MIME 嗅探，降低上传文件（如图片）被当作其他类型执行的风险
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    # 统一错误响应体：前端按状态码跳转自定义错误页（frontend/src/utils/errorPage.ts），
    # 响应体只需给出可读文案；明细留在服务端日志，避免把内部信息透给客户端。
    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning("请求参数校验失败 %s %s: %s", request.method, request.url.path, exc.errors())
        return JSONResponse(status_code=422, content={"detail": "请求参数校验失败，请检查填写内容"})

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception):
        # 兜底 500：Starlette 默认返回纯文本 "Internal Server Error"，前端拿不到 detail，
        # 这里改为与其它接口一致的 JSON 结构，同时用 logger.exception 保留完整堆栈。
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

    app.include_router(api_router, prefix="/api/v1")
    # 仅公开图片子目录：导出/导入原始文档/预览等敏感文件不再静态暴露，改走鉴权接口
    images_dir = settings.storage_sub("uploads", "images")
    app.mount("/storage/uploads/images", StaticFiles(directory=str(images_dir)), name="images")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
