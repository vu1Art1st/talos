#!/usr/bin/env bash
# Talos 迁移锚点备份：生成自包含全量备份（zstd 多线程 + db/storage 并行），
# 并解包差异基线、清空旧差异快照、裁剪锚点到最近 3 份（全量 + 差异模型）。
# 用法（仓库根目录）： bash scripts/backup.sh   （非 root 会自动 sudo 重新执行）
# 产物： backups/anchors/<年>/<月>/<时间戳>/{db.sql.zst, storage.tar.zst, MANIFEST.json}
set -euo pipefail

# 需要 root（访问 docker 卷宿主机路径、写 backups/）；非 root 用 sudo 重新执行自身
if [ "$(id -u)" -ne 0 ]; then
  exec sudo bash "$(cd "$(dirname "$0")" && pwd)/$(basename "$0")" "$@"
fi

cd "$(dirname "$0")/.."   # 切到仓库根目录

# shellcheck source=backup-common.sh
source "$(dirname "$0")/backup-common.sh"

require_cmd docker "需已安装 docker"
require_cmd rsync
require_cmd sha256sum
pick_compressor
acquire_lock

# 校验容器在运行（锚点同时需要 postgres 与 api，缺一不可）
[ -n "$($DOCKER compose ps -q postgres 2>/dev/null)" ] || die "postgres 容器未运行，无法备份"
[ -n "$($DOCKER compose ps -q api 2>/dev/null)" ]       || die "api 容器未运行，无法打包 storage"

VOL_PATH="$(storage_volume_path)"
[ -n "$VOL_PATH" ] || die "无法解析 storage 卷宿主机路径"

ts="$(now_ts)"
ym="$(date +%Y/%m)"
ANCHOR_TMP="backups/anchors/.tmp-${ts}"
ANCHOR_DIR="backups/anchors/${ym}/${ts}"
BASE_TMP="backups/baseline/.storage.tmp"
BASE_DIR="backups/baseline"

mkdir -p "${ANCHOR_TMP}" "$(dirname "${ANCHOR_DIR}")" "${BASE_DIR}"

log "生成迁移锚点 -> ${ANCHOR_DIR}"

# [1/4] 并行：db 逻辑备份 + storage 归档压缩（zstd 多线程）
log "[1/4] 备份数据库 -> db.sql.${ZEXT}"
dump_db "${ANCHOR_TMP}/db.sql.${ZEXT}" &
DB_PID=$!

log "[2/4] 打包 storage -> storage.tar.${ZEXT}"
$DOCKER compose exec -T api sh -c 'tar cf - -C /app/storage .' \
  | $COMPRESS >"${ANCHOR_TMP}/storage.tar.${ZEXT}" &
STORAGE_PID=$!

wait "$DB_PID"
wait "$STORAGE_PID"

# [3/4] 解包差异基线（后续差异快照以此为 hardlink 源）
log "[3/4] 解包差异基线 -> ${BASE_DIR}/storage"
rm -rf "${BASE_TMP}"
mkdir -p "${BASE_TMP}"
$DECOMPRESS "${ANCHOR_TMP}/storage.tar.${ZEXT}" | tar xf - -C "${BASE_TMP}"

# [4/4] 校验 + 原子切换 + 清空/裁剪（先建新、再拆旧）
log "[4/4] 校验并切换"
db_sha="$(file_sha256 "${ANCHOR_TMP}/db.sql.${ZEXT}")"
st_sha="$(file_sha256 "${ANCHOR_TMP}/storage.tar.${ZEXT}")"
git_c="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

# 原子 mv 锚点目录
mv "${ANCHOR_TMP}" "${ANCHOR_DIR}"

# 原子切换 baseline：旧目录先挪开，新目录就位，再删旧
rm -rf "${BASE_DIR}.old"
if [ -d "${BASE_DIR}/storage" ]; then mv "${BASE_DIR}/storage" "${BASE_DIR}.old"; fi
mv "${BASE_TMP}" "${BASE_DIR}/storage"
rm -rf "${BASE_DIR}.old"

write_manifest "${ANCHOR_DIR}/MANIFEST.json" \
  "type=anchor" "created_at=${ts}" "git_commit=${git_c}" \
  "db_sha256=${db_sha}" "storage_sha256=${st_sha}" \
  "status=complete" "completed_at=$(now_ts)"
write_manifest "${BASE_DIR}/MANIFEST.json" \
  "source_anchor=${ts}" "status=complete" "completed_at=$(now_ts)"

# 清空旧差异快照（新锚点 + 新基线已就绪才执行）
log "清空旧差异快照 backups/snapshots/"
rm -rf backups/snapshots/*
mkdir -p backups/snapshots
ln -sfn "anchors/${ym}/${ts}" backups/latest

# 裁剪锚点：保留最近 3 份
log "裁剪迁移锚点：保留最近 3 份"
find backups/anchors -mindepth 3 -maxdepth 3 -type d -name '[0-9]*' 2>/dev/null \
  | sort -r | tail -n +4 | while IFS= read -r d; do
      log "  删除旧锚点：${d}"
      rm -rf "${d}"
    done

log "锚点完成：${ANCHOR_DIR}"
notify "迁移锚点备份完成 ${ts}"
