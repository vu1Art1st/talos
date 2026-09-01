#!/usr/bin/env bash
# Talos 生产数据备份：导出 PostgreSQL 逻辑备份 + 打包 storage 上传文件。
# 在运行着 docker compose 的服务器上、仓库根目录执行： bash scripts/backup.sh
# 产物： backups/<时间戳>/db.sql.gz 与 storage.tar.gz （与镜像/DB 版本无关，可跨机恢复）
# 备份后自动应用保留策略：每日去重 + 保留最近 BACKUP_KEEP_DAYS 天（默认 30）。
set -euo pipefail

cd "$(dirname "$0")/.." # 切到仓库根目录（docker-compose.yml 所在处）

ts="$(date +%Y%m%d_%H%M%S)"
out="backups/${ts}"
sudo mkdir -p "${out}"

echo "[1/2] 备份数据库 -> ${out}/db.sql.gz"
# 在 postgres 容器内用其自带凭证做 pg_dump，无需知道卷名/密码
# --clean --if-exists: 生成的 SQL 以 DROP ... IF EXISTS 开头，支持重复导入到有数据的库（幂等恢复）
sudo docker compose exec -T postgres sh -c 'pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"' | sudo gzip >"${out}/db.sql.gz"

echo "[2/2] 备份上传文件 -> ${out}/storage.tar.gz"
# api 容器把 storage_data 卷挂在 /app/storage，直接打包免去卷名依赖
sudo docker compose exec -T api sh -c 'tar czf - -C /app/storage .' >"${out}/storage.tar.gz"

# [3/3] 备份保留策略：每日去重 + 保留最近 N 天（默认 30，可用 BACKUP_KEEP_DAYS 覆盖）
# 目录名即时间戳（YYYYmmdd_HHMMSS），字符串排序 = 时间排序，因此无需解析日期。
echo "[3/3] 应用备份保留策略（每日去重 + 保留最近 ${BACKUP_KEEP_DAYS:-30} 天）"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

# 第一步：每日去重 —— 降序遍历，每天第一份（最新）保留，其余删除
last_day=""
while IFS= read -r d; do
  day="$(basename "${d}" | cut -c1-8)"
  if [ "${day}" = "${last_day}" ]; then
    echo "  删除当日重复备份：${d}"
    sudo rm -rf "${d}"
  else
    last_day="${day}"
  fi
done < <(find backups -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' 2>/dev/null | sort -r)

# 第二步：保留期 —— 删除早于截止日（今天 - KEEP_DAYS 天）的备份
cutoff="$(date -d "-${KEEP_DAYS} days" +%Y%m%d 2>/dev/null || true)"
if [ -n "${cutoff}" ]; then
  while IFS= read -r d; do
    day="$(basename "${d}" | cut -c1-8)"
    if [[ "${day}" < "${cutoff}" || "${day}" == "${cutoff}" ]]; then
      echo "  删除超过保留期的备份：${d}"
      sudo rm -rf "${d}"
    fi
  done < <(find backups -mindepth 1 -maxdepth 1 -type d -name '[0-9]*' 2>/dev/null | sort -r)
else
  echo "  （无法计算保留期截止日，跳过保留期清理）"
fi

echo "完成：${out}"
echo "提示：迁移新机器时，请同时手动复制仓库代码与 .env（含密钥，勿入库/勿随意外传）。"
