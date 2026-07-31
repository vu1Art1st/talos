#!/usr/bin/env bash
# Talos 生产数据备份：导出 PostgreSQL 逻辑备份 + 打包 storage 上传文件。
# 在运行着 docker compose 的服务器上、仓库根目录执行： bash scripts/backup.sh
# 产物： backups/<时间戳>/db.sql.gz 与 storage.tar.gz （与镜像/DB 版本无关，可跨机恢复）
set -euo pipefail

cd "$(dirname "$0")/.."  # 切到仓库根目录（docker-compose.yml 所在处）

ts="$(date +%Y%m%d_%H%M%S)"
out="backups/${ts}"
mkdir -p "${out}"

echo "[1/2] 备份数据库 -> ${out}/db.sql.gz"
# 在 postgres 容器内用其自带凭证做 pg_dump，无需知道卷名/密码
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "${out}/db.sql.gz"

echo "[2/2] 备份上传文件 -> ${out}/storage.tar.gz"
# api 容器把 storage_data 卷挂在 /app/storage，直接打包免去卷名依赖
docker compose exec -T api sh -c 'tar czf - -C /app/storage .' > "${out}/storage.tar.gz"

echo "完成：${out}"
echo "提示：迁移新机器时，请同时手动复制仓库代码与 .env（含密钥，勿入库/勿随意外传）。"
