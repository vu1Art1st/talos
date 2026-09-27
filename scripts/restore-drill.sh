#!/usr/bin/env bash
# P2-5 备份恢复演练：把最近备份导入独立数据库，执行迁移并校验关键计数，
# 结果写入 backups/restore_drills/latest.json，供 /api/health/metrics 读取。
#
# 用法（仓库根目录 / WSL-Linux）：
#   bash scripts/restore-drill.sh [备份目录]
# 默认备份目录为 backups/latest。脚本只操作 vulnplatform_restore_drill 临时库，
# 不触碰生产库；失败时保留临时库与日志，便于人工排查后重跑。
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=backup-common.sh
source "$(dirname "$0")/backup-common.sh"

BACKUP_DIR="${1:-backups/latest}"
DRILL_DB="${VP_RESTORE_DRILL_DB:-vulnplatform_restore_drill}"
RESULT_DIR="backups/restore_drills"
RESULT_FILE="${RESULT_DIR}/latest.json"

[ -d "$BACKUP_DIR" ] || die "备份目录不存在：$BACKUP_DIR"
[ -f "${BACKUP_DIR}/MANIFEST.json" ] || die "备份缺少 MANIFEST.json：${BACKUP_DIR}"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-vulnplatform}"
PG_PASSWORD="${POSTGRES_PASSWORD:-}"
export PGPASSWORD="$PG_PASSWORD"

require_cmd psql
require_cmd dropdb
require_cmd createdb
require_cmd python3

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x backend/.venv/bin/python ]; then
    PYTHON_BIN="backend/.venv/bin/python"
  elif [ -x backend/.venv/Scripts/python.exe ]; then
    PYTHON_BIN="backend/.venv/Scripts/python.exe"
  else
    die "未找到 backend/.venv Python；请先按 docs/LOCAL_DEV_SETUP.md 创建后端虚拟环境"
  fi
fi

started_epoch="$(date +%s)"
mkdir -p "$RESULT_DIR"

cleanup_failed() {
  rc=$?
  if [ "$rc" -ne 0 ]; then
    python3 - "$RESULT_FILE" "$started_epoch" "$BACKUP_DIR" "$DRILL_DB" <<'PY'
import json
import pathlib
import sys
import time

out, started, backup, db = sys.argv[1:]
pathlib.Path(out).write_text(json.dumps({
    "success": False,
    "started_at_epoch": int(started),
    "finished_at_epoch": int(time.time()),
    "backup_dir": backup,
    "database": db,
    "reason": "restore drill failed; inspect runner log",
}, ensure_ascii=False, indent=2), encoding="utf-8")
PY
  fi
  exit "$rc"
}
trap cleanup_failed EXIT

log "重建临时库 ${DRILL_DB}"
dropdb --if-exists --force --host "$PG_HOST" --port "$PG_PORT" --username "$PG_USER" "$DRILL_DB"
createdb --host "$PG_HOST" --port "$PG_PORT" --username "$PG_USER" "$DRILL_DB"

encoded_password="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$PG_PASSWORD")"
auth="${PG_USER}"
[ -n "$encoded_password" ] && auth="${PG_USER}:${encoded_password}"
sync_dsn="postgresql://${auth}@${PG_HOST}:${PG_PORT}/${DRILL_DB}"
async_dsn="postgresql+asyncpg://${auth}@${PG_HOST}:${PG_PORT}/${DRILL_DB}"

log "导入备份 ${BACKUP_DIR}"
bash scripts/restore-local.sh "$BACKUP_DIR" --dsn "$sync_dsn" --yes

log "执行 Alembic 迁移"
PYTHON_BIN="$(cd "$(dirname "$PYTHON_BIN")" && pwd)/$(basename "$PYTHON_BIN")"
(cd backend && VP_DATABASE_URL="$async_dsn" "$PYTHON_BIN" -m alembic upgrade head)

log "校验关键计数"
read -r table_count vuln_count plan_count report_count asset_count user_count migration <<EOF
$(psql "$sync_dsn" -At -F ' ' -c "
SELECT
  (SELECT count(*) FROM information_schema.tables WHERE table_schema='public'),
  (SELECT count(*) FROM vulns),
  (SELECT count(*) FROM testing_plans),
  (SELECT count(*) FROM reports),
  (SELECT count(*) FROM assets),
  (SELECT count(*) FROM users),
  (SELECT version_num FROM alembic_version);" )
EOF

[ "$table_count" -gt 0 ] || die "恢复后没有业务表"

finished_epoch="$(date +%s)"
python3 - "$RESULT_FILE" "$started_epoch" "$finished_epoch" "$BACKUP_DIR" \
  "$DRILL_DB" "$table_count" "$vuln_count" "$plan_count" "$report_count" \
  "$asset_count" "$user_count" "$migration" <<'PY'
import json
import pathlib
import sys

(out, started, finished, backup, db, tables, vulns, plans, reports, assets,
 users, migration) = sys.argv[1:]
pathlib.Path(out).write_text(json.dumps({
    "success": True,
    "started_at_epoch": int(started),
    "finished_at_epoch": int(finished),
    "elapsed_seconds": int(finished) - int(started),
    "backup_dir": backup,
    "database": db,
    "table_count": int(tables),
    "counts": {
        "vulns": int(vulns),
        "testing_plans": int(plans),
        "reports": int(reports),
        "assets": int(assets),
        "users": int(users),
    },
    "alembic_version": migration,
}, ensure_ascii=False, indent=2), encoding="utf-8")
PY

log "恢复演练通过：表数=${table_count} 迁移=${migration}"
notify "恢复演练通过 ${finished_epoch}"
trap - EXIT
