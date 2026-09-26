"""健康检查端点（P0-3）：存活 / 就绪 / 兼容探针。

- `GET /api/health`：兼容既有探针，恒 200（不查依赖，仅表示进程在跑）；
- `GET /api/health/live`：存活探针，恒 200 —— 进程能响应即算存活，**不检查依赖**
  （依赖故障时不应重启实例）；
- `GET /api/health/ready`：就绪探针，逐项返回依赖状态；任一**必需**依赖失败返回 503，
  可选依赖（Gotenberg）失败不影响状态码。

路径不带 `/api/v1` 前缀：与既有 `/api/health` 保持同一层，便于探针与网关配置沿用旧路径。
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services.health_service import probe_dependencies

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
