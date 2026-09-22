#!/usr/bin/env bash
# Talos 本地（非 Docker）数据恢复：把迁移锚点 / 差异快照导入本机或远程 PostgreSQL，供开发测试用。
#
# 与 scripts/restore.sh 的分工：
#   restore.sh       面向 docker compose 栈（VPS 迁移 / 灾备）：起停容器、解包 storage 卷；
#   restore-local.sh 面向「裸」PostgreSQL（本地 DBngin、WSL 里的独立 PG、任意可达库），不依赖 docker。
#
# 用法（仓库根目录）：
#   bash scripts/restore-local.sh <备份目录> [选项]
#     --dsn <url>         目标库 DSN；默认取 $VP_RESTORE_DSN，否则按 --host/--port/--user/--db 组装
#     --host/--port/--user/--db   组装 DSN（默认 127.0.0.1 / 5432 / $POSTGRES_USER / vulnplatform）
#     --storage-dir <dir> 同时把 storage 归档解包到该目录（默认跳过：归档通常 GB 级）
#     --yes               跳过「目标非本机」确认（目标主机不是 127.0.0.1/localhost/::1 时必须显式给出）
# 环境变量：PGPASSWORD（目标库非 trust 认证时提供）
#
# 破坏性：会 DROP SCHEMA public CASCADE，目标库现有数据全部清除。
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=backup-common.sh
source "$(dirname "$0")/backup-common.sh"

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
}

src=""; dsn=""; host=""; port=""; user=""; db=""; storage_dir=""; assume_yes=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dsn)         dsn="${2:?--dsn 需要参数}"; shift 2 ;;
    --host)        host="${2:?--host 需要参数}"; shift 2 ;;
    --port)        port="${2:?--port 需要参数}"; shift 2 ;;
    --user)        user="${2:?--user 需要参数}"; shift 2 ;;
    --db)          db="${2:?--db 需要参数}"; shift 2 ;;
    --storage-dir) storage_dir="${2:?--storage-dir 需要参数}"; shift 2 ;;
    --yes|-y)      assume_yes=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    -*)            die "未知参数：$1（-h 查看用法）" ;;
    *)             src="$1"; shift ;;
  esac
done
[ -n "$src" ] || { usage; die "缺少备份目录参数"; }
[ -d "$src" ] || die "备份目录不存在：$src"
require_cmd psql "目标库导入需要 psql 客户端"

# 定位 db 文件（.zst 优先，兼容历史 .gz）
DB_FILE=""
for f in "${src}/db.sql.zst" "${src}/db.sql.gz"; do
  [ -f "$f" ] && DB_FILE="$f" && break
done
[ -n "$DB_FILE" ] || die "缺少 ${src}/db.sql.zst 或 db.sql.gz"
DEC="$(decompress_for "$DB_FILE")"
[ -n "$DEC" ] || die "无法识别压缩格式：$DB_FILE"
[ "$DEC" = "zstd -dc" ] && require_cmd zstd "解压 .zst 需要 zstd（apt install zstd / winget install Facebook.ZStandard）"

# 定位 storage（单文件归档＝锚点，目录＝差异快照）
STORAGE_TAR=""; STORAGE_SRC_DIR=""
for f in "${src}/storage.tar.zst" "${src}/storage.tar.gz"; do
  [ -f "$f" ] && STORAGE_TAR="$f" && break
done
[ -d "${src}/storage" ] && STORAGE_SRC_DIR="${src}/storage"

# 目标 DSN：--dsn > $VP_RESTORE_DSN > 由 host/port/user/db 组装（user 默认取 .env 的 POSTGRES_USER）
env_user="$(sed -n 's/^POSTGRES_USER=//p' .env 2>/dev/null | tail -1 || true)"
dsn="${dsn:-${VP_RESTORE_DSN:-}}"
if [ -z "$dsn" ]; then
  dsn="postgresql://${user:-${env_user:-vulnplatform}}@${host:-127.0.0.1}:${port:-5432}/${db:-vulnplatform}"
fi

# 破坏性护栏：仅对明确的回环目标免确认（判据与 backend/scripts/seed_dev_data.py::_assert_dev_database 一致：
# 主机须为回环地址），避免误清同名远程库；口令在日志中打码
dsn_display="$(printf '%s' "$dsn" | sed -E 's#://([^:@/]+):[^@]*@#://\1:***@#')"
case "$dsn" in
  *@127.0.0.1[:/]*|*@localhost[:/]*|*@\[::1\][:/]*|\
  postgresql://127.0.0.1[:/]*|postgresql://localhost[:/]*|postgresql://\[::1\][:/]*) ;;
  *) [ "$assume_yes" -eq 1 ] || die "目标是远程库（${dsn_display}）。本操作会 DROP SCHEMA public CASCADE，确认后请追加 --yes" ;;
esac

log "备份目录：${src}"
log "目标库：${dsn_display}"

echo "[1/3] 校验目标库连通性"
psql "$dsn" -v ON_ERROR_STOP=1 -Atc "select current_database()" >/dev/null \
  || die "无法连接目标库（检查 host/port/用户/口令 PGPASSWORD）"

echo "[2/3] 清空目标库并导入 $(basename "$DB_FILE")"
psql "$dsn" -v ON_ERROR_STOP=1 -q -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
$DEC "$DB_FILE" | psql "$dsn" -v ON_ERROR_STOP=1 -q >/dev/null

echo "[3/3] storage"
if [ -n "$storage_dir" ]; then
  mkdir -p "$storage_dir"
  if [ -n "$STORAGE_TAR" ]; then
    ST_DEC="$(decompress_for "$STORAGE_TAR")"
    # --no-same-owner：备份条目属主是容器内 root，开发机上不保留属主（否则非 root 解包会报 chown 失败）
    $ST_DEC "$STORAGE_TAR" | tar xf - -C "$storage_dir" --no-same-owner
  else
    tar cf - -C "$STORAGE_SRC_DIR" . | tar xf - -C "$storage_dir" --no-same-owner
  fi
  log "storage 已解包到 ${storage_dir}"
else
  log "跳过 storage（需要时加 --storage-dir <目录>，如 backend/storage；归档通常 GB 级）"
fi

log "完成。恢复后先补数据库迁移再访问页面：cd backend && python -m scripts.migrate（见 docs/DEPLOY.md「九」）"
