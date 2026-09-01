#!/usr/bin/env bash
# Talos 差异快照：基于最近锚点基线做硬链接差异，只存变化文件（全量 + 差异模型）。
# 前置：已存在 backups/baseline/storage（即至少生成过一次锚点）；无基线时自动降级为锚点备份。
# 用法（仓库根目录）： bash scripts/backup-incremental.sh   （非 root 会自动 sudo 重新执行）
# 产物： backups/snapshots/<年>/<月>/<时间戳>/{storage/, db.sql.zst, MANIFEST.json}
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$(cd "$(dirname "$0")" && pwd)/$(basename "$0")" "$@"
fi

cd "$(dirname "$0")/.."

# shellcheck source=backup-common.sh
source "$(dirname "$0")/backup-common.sh"

require_cmd docker
require_cmd rsync
require_cmd sha256sum

# 无基线则自动降级为迁移锚点（在加锁之前，避免锁重入）
if [ ! -d backups/baseline/storage ]; then
  log "缺少差异基线 backups/baseline/storage，自动降级为迁移锚点备份"
  exec bash "$(cd "$(dirname "$0")" && pwd)/backup.sh"
fi

pick_compressor
acquire_lock

[ -n "$($DOCKER compose ps -q postgres 2>/dev/null)" ] || die "postgres 容器未运行"
[ -n "$($DOCKER compose ps -q api 2>/dev/null)" ]       || die "api 容器未运行"

VOL_PATH="$(storage_volume_path)"
[ -n "$VOL_PATH" ] || die "无法解析 storage 卷宿主机路径"

ts="$(now_ts)"
ym="$(date +%Y/%m)"
SNAP_TMP="backups/snapshots/.tmp-${ts}"
SNAP_DIR="backups/snapshots/${ym}/${ts}"

mkdir -p "$(dirname "${SNAP_DIR}")" "${SNAP_TMP}"

log "生成差异快照 -> ${SNAP_DIR}"

# [1/2] 并行：db 备份 + storage 差异（--link-dest 指向基线）
log "[1/2] 备份数据库 -> db.sql.${ZEXT}"
dump_db "${SNAP_TMP}/db.sql.${ZEXT}" &
DB_PID=$!

log "[2/2] storage 差异（hardlink 基线复用）"
BASE_ABS="$(cd backups/baseline/storage && pwd)"
rsync -a --delete --link-dest="${BASE_ABS}/" "${VOL_PATH}/" "${SNAP_TMP}/storage/" &
RSYNC_PID=$!

wait "$DB_PID"
wait "$RSYNC_PID"

# 校验 + 原子切换
db_sha="$(file_sha256 "${SNAP_TMP}/db.sql.${ZEXT}")"
file_count="$(find "${SNAP_TMP}/storage" -type f 2>/dev/null | wc -l | tr -d ' ')"
git_c="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

mv "${SNAP_TMP}" "${SNAP_DIR}"

write_manifest "${SNAP_DIR}/MANIFEST.json" \
  "type=snapshot" "created_at=${ts}" "git_commit=${git_c}" \
  "db_sha256=${db_sha}" "storage_files=${file_count}" \
  "status=complete" "completed_at=$(now_ts)"

# 更新 latest 软链
ln -sfn "snapshots/${ym}/${ts}" backups/latest

log "差异快照完成：${SNAP_DIR}"
notify "差异快照完成 ${ts}"
