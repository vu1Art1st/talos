#!/usr/bin/env bash
# Talos 生产数据恢复 / 迁移到新机器：从 backup.sh 产物恢复数据库与上传文件。
# 用法（新机器仓库根目录，已放好 .env）： bash scripts/restore.sh backups/<时间戳>
# 说明：自动清空目标库后导入，支持重复执行。会停掉当前运行的容器再重建。
set -euo pipefail

cd "$(dirname "$0")/.."  # 切到仓库根目录

src="${1:?用法: bash scripts/restore.sh <备份目录，如 backups/20260731_230000>}"
[ -f "${src}/db.sql.gz" ] || { echo "缺少 ${src}/db.sql.gz"; exit 1; }
[ -f "${src}/storage.tar.gz" ] || { echo "缺少 ${src}/storage.tar.gz"; exit 1; }

echo "[1/4] 启动 postgres 并等待就绪"
# 先停掉可能残留的旧容器，确保从干净状态开始
docker compose down 2>/dev/null || true
docker compose up -d postgres
for i in $(seq 1 30); do
  if docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "[2/4] 清空旧数据并恢复数据库"
# 确保目标库干净：清空 public schema 后重建，避免残留表（如 alembic_version）与 dump 冲突
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"' >/dev/null
gunzip -c "${src}/db.sql.gz" | docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'

echo "[3/4] 启动 api 并恢复上传文件"
docker compose up -d api
# 等待 api 容器起来（storage 卷已挂载即可解包）
sleep 3
gunzip -c "${src}/storage.tar.gz" | docker compose exec -T api sh -c 'tar xf - -C /app/storage'

echo "[4/4] 拉起全部服务"
docker compose up -d

echo "完成。请用原 admin 账号登录验证数据。"
