"""一次性维护脚本的公共助手（审计 M-2）。

背景：`scripts/` 下的一次性脚本各自复制了同一套样板 —— `sys.path` 注入、
静默 SQLAlchemy 回显、解析 `--dry-run`、写 `storage/backups/` JSON 快照，
以及「dry-run 必须先取纯数据快照再 rollback（否则会话内 ORM 实例过期触发
`MissingGreenlet`）」这一隐式约定。本模块把约定固化为代码。

用法（脚本头部）：

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 先让 scripts 包可导入
    from scripts._common import dry_run_flag, run                      # noqa: E402

    async def main(dry_run: bool = False) -> None:
        ...

    if __name__ == "__main__":
        run(main, dry_run=dry_run_flag())

注意：`run()` 内部会调用 `bootstrap()`，因此脚本无需再手动静默日志或插入 sys.path；
但**为了能 import 本模块**，头部仍需保留那两行 `sys.path.insert`（`python -m scripts.x`
与 `python scripts/x.py` 两种调用方式都要能跑）。
"""
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPTS_DIR.parent


def bootstrap() -> None:
    """静默 SQLAlchemy 调试回显 + 确保 backend 根目录在 sys.path（均幂等）。"""
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    root = str(BACKEND_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def dry_run_flag() -> bool:
    """是否带 `--dry-run`（一次性脚本统一约定：只统计不落库）。"""
    return "--dry-run" in sys.argv


def save_backup(records: list[dict], prefix: str, indent: int | None = 2) -> Path | None:
    """把待改记录快照写入「配置的存储目录」下的 `backups/<prefix>_<时间戳>.json`。

    - 目录取自 `settings.storage_sub("backups")`（尊重 `VP_STORAGE_DIR`，容器内为
      `/app/storage/backups`）—— 与既有脚本口径一致；
    - 返回快照路径；`records` 为空时不写文件、返回 None（等价于「无需备份」）；
    - `indent=None` 输出紧凑 JSON（用于保留个别脚本原有的文件格式）。

    实现约束：`settings` 必须**在函数体内延迟导入**。模块顶层导入会在
    `import scripts._common` 时即加载 `app.core.config`，若必填环境变量（如 `VP_SECRET_KEY`）
    缺失，会连带让只用 `run()` 的脚本无法启动。
    """
    if not records:
        return None
    from app.core.config import settings  # 延迟导入：原因见 docstring

    backup_dir = settings.storage_sub("backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=indent, default=str),
        encoding="utf-8",
    )
    return path


def run(main, **kwargs) -> None:
    """一次性脚本统一入口：bootstrap() 后以 asyncio.run 执行 main（透传关键字参数）。

    **dry-run 与快照的约定（由本入口固化）**：`--dry-run` 分支必须在 `session.rollback()`
    **之前**把要打印/备份的值取成普通 dict（`id`/`title`/`html` 等标量），不可在 rollback
    之后再访问 ORM 实例属性 —— 异步会话在 rollback 后实例全部过期，再访问会触发同步 IO
    并抛 `MissingGreenlet`。各脚本的「纯数据快照」代码保留在脚本内（其字段与结构各不相同，
    抽成公共抽象反而会掩盖语义）；本 docstring 是该约定的唯一说明处。
    """
    bootstrap()
    asyncio.run(main(**kwargs))
