#!/usr/bin/env bash
# Talos 一键升级：拉取代码 → 备份 → 重建镜像 → 迁移数据库结构 → 重启服务。
# 在运行着 docker compose 的服务器、仓库根目录执行： bash scripts/upgrade.sh
#
# 选项：
#   --no-backup   跳过升级前自动备份（默认会先备份，除非当前没有运行中的数据库）
#   --no-pull     跳过 git pull（用于已手动拉好代码、仅想走后续升级流程的场景）
#
# 顺序说明：数据库迁移在 api 服务启动【之前】用一次性容器执行，确保 Alembic 先于
# 后端的 create_all 应用结构变更，避免「新增表被 create_all 抢先建好导致迁移冲突」。
set -euo pipefail

cd "$(dirname "$0")/.." # 切到仓库根目录（docker-compose.yml 所在处）

DO_BACKUP=1
DO_PULL=1
for arg in "$@"; do
  case "$arg" in
  --no-backup) DO_BACKUP=0 ;;
  --no-pull) DO_PULL=0 ;;
  *)
    echo "未知参数：$arg"
    echo "用法： bash scripts/upgrade.sh [--no-backup] [--no-pull]"
    exit 2
    ;;
  esac
done

# 前置校验
[ -f .env ] || {
  echo "缺少 .env，请先按 docs/DEPLOY.md 完成首次配置"
  exit 1
}
command -v docker >/dev/null || {
  echo "未安装 docker"
  exit 1
}

OLD_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "========== Talos 升级开始（当前版本 ${OLD_COMMIT}）=========="

# [1/5] 升级前备份（仅当数据库容器在运行时）
if [ "${DO_BACKUP}" -eq 1 ]; then
  if [ -n "$(docker compose ps -q postgres 2>/dev/null)" ]; then
    echo "[1/5] 升级前备份"
    bash scripts/backup.sh
  else
    echo "[1/5] 未检测到运行中的数据库，跳过备份（首次部署无需备份）"
  fi
else
  echo "[1/5] 按参数跳过备份"
fi

# [2/5] 拉取最新代码
if [ "${DO_PULL}" -eq 1 ]; then
  echo "[2/5] 拉取最新代码 git pull --ff-only"
  git pull --ff-only
else
  echo "[2/5] 按参数跳过 git pull"
fi
NEW_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

if [ "${OLD_COMMIT}" = "${NEW_COMMIT}" ] && [ "${DO_PULL}" -eq 1 ]; then
  echo "代码已是最新（${NEW_COMMIT}），仍将继续重建与迁移以确保一致。"
fi

# [3/5] 重建镜像
echo "[3/5] 重建镜像 docker compose build"
sudo docker compose build

# [4/5] 先迁移数据库结构（api 服务尚未启动，Alembic 先行）
echo "[4/5] 数据库结构迁移"
bash scripts/migrate.sh

# [5/5] 拉起 / 刷新全部服务
echo "[5/5] 启动全部服务 docker compose up -d"
sudo docker compose up -d

echo "========== 升级完成：${OLD_COMMIT} -> ${NEW_COMMIT} =========="
sudo docker compose ps
echo "当前数据库迁移版本："
sudo docker compose exec -T api python -m alembic current 2>/dev/null || echo "（无法读取，可稍后用 docker compose exec api python -m alembic current 查看）"
echo
echo "如需回滚代码： git checkout ${OLD_COMMIT} && docker compose up -d --build"
echo "（数据库回滚请用升级前备份 scripts/restore.sh，见 docs/DEPLOY.md）"
