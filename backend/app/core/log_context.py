"""日志关联字段（P0-3）：`request_id` 注入。

**为什么需要**：前端只能展示「服务器内部错误」和状态码，用户报障时运维无法在日志里找到
对应请求的行。本模块给每个 HTTP 请求分配 `request_id`（优先复用调用方传入的
`X-Request-Id`），写入 ContextVar 并回写同名响应头；日志里带上同一个 ID 即可直接定位。

实现要点：
- `install_log_context()` 幂等（`create_app` 在测试中会被反复调用）；
- 只接管本项目 `app.*` 日志器（独立 handler + 统一格式），**不改写 root handler 的 formatter**
  —— uvicorn 的 access/error 日志格式（含着色）由部署方决定，强行改写会破坏其输出；
- 后台任务没有 HTTP 请求上下文，`request_id` 取默认值 `-`，关联靠消息里的
  `job_id=` / `batch_id=`（见 workers/main.py）。
"""
import logging
from contextvars import ContextVar
from uuid import uuid4

# 无请求上下文（后台任务 / 启动阶段）时为 "-"，避免格式化报错
REQUEST_ID_HEADER = "X-Request-Id"

request_id_var: ContextVar[str] = ContextVar("talos_request_id", default="-")

APP_LOG_FORMAT = "%(asctime)s %(levelname)s [rid=%(request_id)s] %(name)s: %(message)s"
_APP_LOGGER_NAME = "app"
_INSTALL_FLAG = "_talos_log_context_installed"


class RequestIdFilter(logging.Filter):
    """把当前请求 ID 注入每条日志记录（格式化串用 `%(request_id)s` 取用）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def new_request_id() -> str:
    """生成请求 ID（12 位十六进制，足够区分且不冗余）。"""
    return uuid4().hex[:12]


def set_request_id(value: str) -> str:
    """设置当前上下文的请求 ID 并返回生效值（空值则视为未提供）。"""
    rid = (value or "").strip()[:64] or new_request_id()
    request_id_var.set(rid)
    return rid


def current_request_id() -> str:
    return request_id_var.get()


def install_log_context() -> None:
    """为 `app.*` 日志器安装 request_id 过滤器与统一格式（幂等）。

    自带 handler 且 `propagate=False`：避免与 uvicorn 的 root handler 重复输出，
    同时保证业务日志一定带 `rid=` 字段。
    """
    logger = logging.getLogger(_APP_LOGGER_NAME)
    if getattr(logger, _INSTALL_FLAG, False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(APP_LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    setattr(logger, _INSTALL_FLAG, True)
