#!/usr/bin/env bash
# Talos 数据恢复 / 迁移：从迁移锚点（storage.tar.zst）或差异快照（storage/ 目录）恢复。
# 兼容历史 .gz 产物与旧平铺路径 backups/<时间戳>。
# 用法（新机器仓库根目录，已放好 .env）： bash scripts/restore.sh <备份目录>
#   - 迁移锚点目录： backups/anchors/2026/09/20260901_030001/
#   - 差异快照目录： backups/snapshots/2026/09/20260901_020001/
# 说明：自动清空目标库后导入，支持重复执行。会停掉当前运行的容器再重建。
set -euo pipefail

# 快照目录为 root 所有（备份脚本以 root 运行），统一以 root 执行保证可读
if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$(cd "$(dirname "$0")" && pwd)/$(basename "$0")" "$@"
fi

cd "$(dirname "$0")/.."

# shellcheck source=backup-common.sh
source "$(dirname "$0")/backup-common.sh"

src="${1:?用法: bash scripts/restore.sh <备份目录，如 backups/anchors/2026/09/20260901_030001>}"

# 定位 db 文件（.gz 或 .zst）
DB_FILE=""
for f in "${src}/db.sql.gz" "${src}/db.sql.zst"; do
  [ -f "$f" ] && DB_FILE="$f" && break
done
[ -n "$DB_FILE" ] || { echo "缺少 ${src}/db.sql.gz 或 db.sql.zst"; exit 1; }

# 定位 storage（单文件归档=锚点，或 目录=差异快照）
STORAGE_TAR=""
STORAGE_DIR=""
for f in "${src}/storage.tar.gz" "${src}/storage.tar.zst"; do
  [ -f "$f" ] && STORAGE_TAR="$f" && break
done
[ -d "${src}/storage" ] && STORAGE_DIR="${src}/storage"

[ -n "$STORAGE_TAR" ] || [ -n "$STORAGE_DIR" ] || {
  echo "缺少 ${src}/storage.tar.gz|.zst 或 ${src}/storage/ 目录"; exit 1;
}

DEC="$(decompress_for "$DB_FILE")"
[ -n "$DEC" ] || { echo "无法识别 db 文件压缩格式：$DB_FILE"; exit 1; }

echo "[1/4] 启动 postgres 并等待就绪"
# 先停掉可能残留的旧容器，确保从干净状态开始
$DOCKER compose down 2>/dev/null || true
$DOCKER compose up -d postgres
for i in $(seq 1 30); do
  if $DOCKER compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "[2/4] 清空旧数据并恢复数据库"
# 确保目标库干净：清空 public schema 后重建，避免残留表（如 alembic_version）与 dump 冲突
$DOCKER compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"' >/dev/null
$DEC "$DB_FILE" | $DOCKER compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

echo "[3/4] 启动 api 并恢复上传文件"
$DOCKER compose up -d api
# 等待 api 容器起来（storage 卷已挂载即可解包）
sleep 3
if [ -n "$STORAGE_TAR" ]; then
  # 迁移锚点：单文件归档
  ST_DEC="$(decompress_for "$STORAGE_TAR")"
  $ST_DEC "$STORAGE_TAR" | $DOCKER compose exec -T api sh -c 'tar xf - -C /app/storage'
else
  # 差异快照：storage/ 目录（含硬链接，tar 打包后导入）
  tar cf - -C "$STORAGE_DIR" . | $DOCKER compose exec -T api sh -c 'tar xf - -C /app/storage'
fi

echo "[4/4] 拉起全部服务"
$DOCKER compose up -d

echo "完成。请用原 admin 账号登录验证数据。"
echo "提示：恢复后先执行 bash scripts/migrate.sh 再访问（见 docs/DEPLOY.md「七、恢复后页面 500 排查」）。"
