import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")
    app.mount("/storage", StaticFiles(directory=str(settings.storage_path)), name="storage")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
