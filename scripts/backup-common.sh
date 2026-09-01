#!/usr/bin/env bash
# Talos 备份公共函数库（被 backup.sh / backup-incremental.sh / restore.sh source）。
# 提供：docker 命令前缀、互斥锁、zstd/gzip 自动选择、SHA256、MANIFEST、webhook 告警、storage 卷路径解析。
# 注意：本文件只定义函数与变量，不执行顶层逻辑（可安全多次 source）。

# ---- docker 命令前缀（root 直接 docker，否则 sudo docker）----
if [ "$(id -u)" -eq 0 ]; then
  DOCKER="docker"
else
  DOCKER="sudo docker"
fi

# ---- 时间与日志 ----
now_ts() { date +%Y%m%d_%H%M%S; }
log()   { echo "[$(date +%H:%M:%S)] $*"; }
die()   { log "错误：$*" >&2; exit 1; }

# ---- 命令前置校验 ----
require_cmd() {
  local cmd="$1" hint="${2:-}"
  command -v "$cmd" >/dev/null 2>&1 || die "缺少命令 $cmd${hint:+（$hint）}"
}

# ---- 压缩器选择（优先 zstd，回退 gzip）----
# 先调用 pick_compressor，之后可用 $ZEXT / $COMPRESS / $DECOMPRESS
ZEXT="gz"; COMPRESS="gzip"; DECOMPRESS="gunzip -c"
pick_compressor() {
  if command -v zstd >/dev/null 2>&1; then
    ZEXT="zst"; COMPRESS="zstd -T0"; DECOMPRESS="zstd -dc"
  else
    log "未检测到 zstd，回退 gzip（较慢，建议 apt install zstd）"
  fi
}

# 按文件扩展名返回解压命令（restore 兼容历史 .gz 与新的 .zst 产物）
decompress_for() {
  case "$1" in
    *.zst) echo "zstd -dc" ;;
    *.gz)  echo "gunzip -c" ;;
    *)     echo "" ;;
  esac
}

# ---- webhook 告警（未配置 BACKUP_WEBHOOK_URL 则静默跳过）----
notify() {
  local script
  script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/notify.sh"
  [ -f "$script" ] && bash "$script" "${1:-}" || true
}

# ---- 互斥锁（flock，同一时刻只允许一份备份）----
acquire_lock() {
  require_cmd flock
  LOCK_FILE="/tmp/talos-backup.lock"
  exec 9>"$LOCK_FILE"
  flock -n 9 || die "已有备份任务在运行（锁 $LOCK_FILE），本次退出"
  trap 'flock -u 9 2>/dev/null || true' EXIT
}

# ---- 解析 storage 卷的宿主机挂载路径（供 rsync 硬链接使用）----
storage_volume_path() {
  local cid
  cid="$($DOCKER compose ps -q api 2>/dev/null)" || return 1
  [ -n "$cid" ] || return 1
  $DOCKER inspect -f '{{range .Mounts}}{{if eq .Destination "/app/storage"}}{{.Source}}{{end}}{{end}}' "$cid"
}

# ---- 数据库逻辑备份（pg_dump → 压缩）----
dump_db() {
  local out="$1"
  $DOCKER compose exec -T postgres sh -c 'pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | $COMPRESS >"$out"
}

# ---- 单文件 SHA256 ----
file_sha256() { sha256sum "$1" | awk '{print $1}'; }

# ---- 写入 MANIFEST.json（手工拼 JSON，值均为字符串）----
# 用法：write_manifest <文件> "key=value" "key2=value2" ...
write_manifest() {
  local file="$1"; shift
  local json=""
  local kv
  for kv in "$@"; do
    json="${json:+$json,}\"${kv%%=*}\":\"${kv#*=}\""
  done
  printf '{%s}\n' "$json" >"$file"
}
