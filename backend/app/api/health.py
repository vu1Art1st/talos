"""健康检查端点（P0-3）：存活 / 就绪 / 兼容探针。

- `GET /api/health`：兼容既有探针，恒 200（不查依赖，仅表示进程在跑）；
- `GET /api/health/live`：存活探针，恒 200 —— 进程能响应即算存活，**不检查依赖**
  （依赖故障时不应重启实例）；
- `GET /api/health/ready`：就绪探针，逐项返回依赖状态；任一必需依赖失败返回 503。

路径不带 `/api/v1` 前缀：与既有 `/api/health` 保持同一层，便于探针与网关配置沿用旧路径。
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.services.health_service import probe_dependencies
from app.services.metrics_service import collect_metrics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["健康检查"])


@router.get("/api/health")
async def health():
    """兼容探针：保持既有响应体 `{"status": "ok"}` 不变。"""
    return {"status": "ok"}


@router.get("/api/health/live")
async def health_live():
    return {"status": "alive"}


@router.get("/api/health/ready")
async def health_ready(request: Request):
    checks, ready = await probe_dependencies(request.app)
    payload = {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }
    if not ready:
        failed = [name for name, c in checks.items() if c["required"] and not c["ok"]]
        logger.warning("就绪探针失败，未就绪的必需依赖：%s", failed)
        return JSONResponse(status_code=503, content=payload)
    return payload


@router.get("/api/health/metrics", response_class=PlainTextResponse)
async def health_metrics(request: Request):
    """Prometheus 文本指标（P2-5）。仅返回聚合值，禁止放入对象名、URL 或错误正文。"""
    return PlainTextResponse(
        await collect_metrics(request.app),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
