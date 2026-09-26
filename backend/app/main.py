import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from dataclasses import replace

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError

from app.api.health import router as health_router
from app.api.images import router as images_router
from app.api.v1 import api_router
from app.core.config import settings
from app.core.log_context import REQUEST_ID_HEADER, install_log_context, set_request_id
from app.db import init_db
from app.services import task_lifecycle

logger = logging.getLogger(__name__)

# 开放 API 契约版本（P1-6）：仅当发生**破坏性**变更时递增，并同步 docs/OPEN_API_GUIDE.md
OPEN_API_VERSION = "1"


async def _periodic_task_recovery(app: FastAPI) -> None:
    """无队列（进程内执行）形态的兜底扫描：启动之外每 SWEEP_INTERVAL_SECONDS 回收一次。

    有 arq worker 时该职责由 worker 的 cron（workers/main.recover_tasks_task）承担，
    两边同时跑只会重复调用幂等任务，不会产生重复业务副作用。
    """
    while True:
        await asyncio.sleep(task_lifecycle.SWEEP_INTERVAL_SECONDS)
        try:
            await task_lifecycle.recover_and_redispatch(app)
        except Exception as exc:  # noqa: BLE001  兜底扫描失败不应影响服务
            logger.warning("周期性任务回收失败: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # arq 连接池：Redis 不可用时降级为进程内执行（见 workers/dispatch.py）
    app.state.arq = None
    if not settings.DISABLE_QUEUE:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            # 连接超时取 settings.REDIS_TIMEOUT、重试 1 次：Redis 不可达时尽快失败并降级为进程内
            # 执行（arq 默认 1s 超时 × 5 次重试 + 每次 1s 退避 ≈ 10s 的启动阻塞，见 G7）
            app.state.arq = await create_pool(
                replace(
                    RedisSettings.from_dsn(settings.REDIS_URL),
                    conn_timeout=int(settings.REDIS_TIMEOUT),
                    conn_retries=1,
                )
            )
        except Exception as exc:
            logger.warning("Redis 连接失败，后台任务将在进程内执行: %s", exc)
    # 启动时回收超租约 / 待重试任务（P0-3）：worker 崩溃留下的 running/parsing 不再永久卡住。
    # 回收失败不影响启动（探针会通过 worker 心跳暴露问题）。
    try:
        summary = await task_lifecycle.recover_and_redispatch(app)
        if summary["requeued"] or summary["dead"]:
            logger.warning(
                "启动任务回收：重新排队=%s 死信=%s", summary["requeued"], summary["dead"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动任务回收失败（不影响启动）: %s", exc)
    # 无队列形态没有 worker cron，由 API 进程内的周期任务兜底重试（有队列时交给 worker）
    sweep_task = (
        asyncio.create_task(_periodic_task_recovery(app)) if settings.DISABLE_QUEUE else None
    )
    yield
    if sweep_task is not None:
        sweep_task.cancel()
        with suppress(asyncio.CancelledError):
            await sweep_task
    if app.state.arq is not None:
        await app.state.arq.close()


def create_app() -> FastAPI:
    # 业务日志统一带 request_id（P0-3）：便于从界面报错定位后端日志
    install_log_context()
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
    async def _request_context(request, call_next):
        # 请求 ID：优先复用调用方传入值（便于网关/前端串联），并回写响应头。
        # 必须在 call_next 之前写入 ContextVar，下游任务才会继承该值。
        rid = set_request_id(request.headers.get(REQUEST_ID_HEADER, ""))
        response = await call_next(request)
        response.headers.setdefault(REQUEST_ID_HEADER, rid)
        # 阻止浏览器 MIME 嗅探，降低上传文件（如图片）被当作其他类型执行的风险
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # 开放 API 版本标识（P1-6）：破坏性调整必须升版本号（策略见 docs/OPEN_API_GUIDE.md）
        if request.url.path.startswith("/api/v1/open"):
            response.headers.setdefault("X-API-Version", OPEN_API_VERSION)
        if response.status_code >= 400:
            logger.warning(
                "请求失败 rid=%s method=%s path=%s status=%s",
                rid, request.method, request.url.path, response.status_code,
            )
        return response

    # 统一错误响应体：前端按状态码跳转自定义错误页（frontend/src/utils/errorPage.ts），
    # 响应体只需给出可读文案；明细留在服务端日志，避免把内部信息透给客户端。
    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning("请求参数校验失败 %s %s: %s", request.method, request.url.path, exc.errors())
        # 自有校验函数（schemas 层的 ValueError，如影响URL 条数/长度上限）应把中文文案透出，
        # 让用户知道具体哪里不合规；其余（类型/必填等）仍用通用提示，避免暴露内部结构。
        detail = "请求参数校验失败，请检查填写内容"
        for err in exc.errors():
            msg = str(err.get("msg", ""))
            if err.get("type") == "value_error" and msg.startswith("Value error, "):
                detail = msg.removeprefix("Value error, ")
                break
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(DataError)
    async def _data_error_handler(request: Request, exc: DataError):
        # 数据长度/数值越界等数据库层拒绝（如 SQLSTATE 22001 值超长）：属可预期的用户输入问题，
        # 归为 400 并给出可读文案，不再落入兜底 500（前端 500 会整页跳错误页并丢失表单内容）。
        logger.warning(
            "数据写入被数据库拒绝 %s %s: %s", request.method, request.url.path, exc.orig
        )
        return JSONResponse(
            status_code=400,
            content={"detail": "提交的数据超出允许范围，请检查各字段长度或数值后重试"},
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception):
        # 兜底 500：Starlette 默认返回纯文本 "Internal Server Error"，前端拿不到 detail，
        # 这里改为与其它接口一致的 JSON 结构，同时用 logger.exception 保留完整堆栈。
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

    app.include_router(api_router, prefix="/api/v1")
    # 图片需登录下发（安全审计 批次 E-1）：路径保持 /storage/uploads/images/<name> 不变，
    # 但不再是静态直出——导出/导入原始文档/预览等敏感文件同样只走鉴权接口
    app.include_router(images_router)
    # 健康检查（P0-3）：/api/health 兼容旧探针，/live 存活、/ready 就绪（含依赖逐项状态）
    app.include_router(health_router)

    return app


app = create_app()
