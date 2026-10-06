"""为存量用户随机分配一个预置头像（官方《绝区零》角色头像）。

默认只处理「当前没有有效头像」的用户：

- `avatar` 为空：从未设置过；
- `avatar` 是已下线的旧预设（`preset:<旧编号>`）：原来 12 款 SVG 预设已整体移除，
  这些值在新版本里解析不出 URL，必须重新分配。

用户自己上传的头像（`uploads/images/...`）默认**不动**，避免覆盖用户的主动选择；
确需全部重掷时显式加 `--all`。

用法（backend/ 目录，使用 .venv）：
    python -m scripts.assign_random_avatars --dry-run
    python -m scripts.assign_random_avatars
    python -m scripts.assign_random_avatars --all --seed 20261006
"""
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import dry_run_flag, ensure_local_env, run, save_backup  # noqa: E402

# 本地直连 DB 时补上仓库根 .env（容器内由 compose 注入环境变量，此调用不覆盖已有值）
ensure_local_env()

from sqlalchemy import select  # noqa: E402

from app.constants import AVATAR_PRESETS  # noqa: E402
from app.core.avatars import is_preset_id  # noqa: E402
from app.db import async_session_maker  # noqa: E402
from app.models import User  # noqa: E402

PRESET_PREFIX = "preset:"


def needs_assignment(avatar: str) -> bool:
    """空值或已下线的旧预设 -> True；用户上传的图与现役预置 -> False。"""
    value = (avatar or "").strip()
    if not value:
        return True
    if value.startswith(PRESET_PREFIX):
        return not is_preset_id(value[len(PRESET_PREFIX):])
    return False


def parse_seed(argv: list[str]) -> int | None:
    """读取 `--seed <int>`；缺省返回 None（用系统熵源）。"""
    if "--seed" not in argv:
        return None
    index = argv.index("--seed")
    if index + 1 >= len(argv):
        raise SystemExit("--seed 需要一个整数参数")
    return int(argv[index + 1])


def _report(total_users: int, snapshots: list[dict], picked: list[str], *, dry_run: bool) -> None:
    """输出统计：总量、来源分布、以及命中次数最多的预置头像。"""
    tag = "[dry-run] " if dry_run else ""
    blank = sum(1 for s in snapshots if not s["old_avatar"])
    legacy = sum(1 for s in snapshots if s["old_avatar"].startswith(PRESET_PREFIX))
    uploaded = len(snapshots) - blank - legacy
    print(f"{tag}用户总数 {total_users}，本次分配 {len(snapshots)} 人")
    print(f"{tag}来源：空头像 {blank}，旧预设 {legacy}，已上传（仅 --all 时覆盖）{uploaded}")
    if not snapshots:
        return
    counter = Counter(picked)
    print(f"{tag}用到 {len(counter)} 款预置；命中最多：{counter.most_common(3)}")


async def assign(
    session,
    *,
    all_users: bool,
    seed: int | None,
    dry_run: bool,
) -> int:
    """执行分配，返回被重新分配的用户数（dry-run 时整体回滚）。"""
    preset_ids = list(AVATAR_PRESETS)
    if not preset_ids:
        raise SystemExit("AVATAR_PRESETS 为空，先确认预置头像资源是否随镜像分发")

    users = (await session.execute(select(User).order_by(User.id))).scalars().all()
    targets = [u for u in users if all_users or needs_assignment(u.avatar or "")]

    rng = random.Random(seed)
    snapshots: list[dict] = []
    picked: list[str] = []
    for user in targets:
        preset_id = rng.choice(preset_ids)
        picked.append(preset_id)
        snapshots.append(
            {
                "user_id": user.id,
                "username": user.username,
                "old_avatar": user.avatar or "",
                "new_avatar": f"{PRESET_PREFIX}{preset_id}",
            }
        )

    if dry_run:
        await session.rollback()
        _report(len(users), snapshots, picked, dry_run=True)
        return len(snapshots)

    backup_file = save_backup(snapshots, "user_avatars")
    for user, preset_id in zip(targets, picked, strict=True):
        user.avatar = f"{PRESET_PREFIX}{preset_id}"
    await session.commit()

    _report(len(users), snapshots, picked, dry_run=False)
    if backup_file:
        print(f"原值备份：{backup_file}")
    return len(snapshots)


async def main(*, dry_run: bool = False) -> None:
    all_users = "--all" in sys.argv
    seed = parse_seed(sys.argv)
    async with async_session_maker() as session:
        await assign(session, all_users=all_users, seed=seed, dry_run=dry_run)


if __name__ == "__main__":
    run(main, dry_run=dry_run_flag())
