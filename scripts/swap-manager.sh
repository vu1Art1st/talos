#!/usr/bin/env bash
# =============================================================================
# swap-manager.sh — 一键开启 / 关闭 4GB swap
#
# 用法：
#   sudo bash swap-manager.sh on      开启 swap（若已存在则提示，不重复创建）
#   sudo bash swap-manager.sh off     安全关闭并删除 swap 文件、移除开机自动挂载
#   sudo bash swap-manager.sh status  查看当前 swap / 内存状态
# =============================================================================
set -uo pipefail

SWAP_FILE="/swapfile"
SWAP_SIZE_MB=4096          # 固定 4GB

log()  { printf '%s\n' "$*"; }
err()  { printf '[错误] %s\n' "$*" >&2; }
warn() { printf '[警告] %s\n' "$*" >&2; }
ok()   { printf '[完成] %s\n' "$*"; }
die()  { err "$*"; exit 1; }

usage() {
  cat <<'EOF'
用法: sudo bash swap-manager.sh <on|off|status>

命令:
  on      开启 swap：检查是否已存在 → 磁盘空间检查 → 创建 4GB swap 文件
          → 启用并写入 /etc/fstab 开机自动挂载
  off     关闭 swap：swapoff → 移除 /etc/fstab 条目 → 删除 swap 文件
  status  查看当前 swap / 内存 / 文件 / fstab 状态

示例:
  sudo bash swap-manager.sh on
  sudo bash swap-manager.sh off
  sudo bash swap-manager.sh status
EOF
}

require_root() {
  [ "$(id -u)" -eq 0 ] || die "需要 root 权限，请使用：sudo bash $0 <on|off|status>"
}

confirm() {
  local prompt="$1" ans
  read -r -p "${prompt} [y/N] " ans
  case "$ans" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

# 是否存在任意活动 swap（跳过 /proc/swaps 表头与空行）
has_active_swap() {
  [ -n "$(tail -n +2 /proc/swaps 2>/dev/null | sed '/^[[:space:]]*$/d')" ]
}

# 我们的 swap 文件是否处于活动状态
swapfile_active() {
  tail -n +2 /proc/swaps 2>/dev/null \
    | awk -v f="$SWAP_FILE" '$1 == f {found=1} END {exit (found ? 0 : 1)}'
}

do_enable() {
  require_root

  # 1) 已存在 swap？
  if has_active_swap; then
    warn "系统当前已存在活动 swap："
    swapon --show 2>/dev/null || tail -n +2 /proc/swaps
    err "检测到已有 swap，为避免冲突不重复创建。"
    log "如需重置，请先执行：sudo bash $0 off"
    exit 1
  fi

  if [ -e "$SWAP_FILE" ]; then
    warn "swap 文件已存在（但未启用）：$SWAP_FILE"
    if ! confirm "文件已存在，是否重新格式化并启用？"; then
      log "已取消。"
      exit 0
    fi
  fi

  # 2) 磁盘空间检查
  local fs_dir avail_kb need_kb
  fs_dir="$(dirname "$SWAP_FILE")"
  avail_kb="$(df -kP "$fs_dir" | awk 'NR==2 {print $4}')"
  need_kb=$(( SWAP_SIZE_MB * 1024 ))
  if [ -z "$avail_kb" ] || [ "$avail_kb" -lt "$need_kb" ]; then
    die "磁盘空间不足：创建 ${SWAP_SIZE_MB}MB swap 需要 ${need_kb}KB，但 ${fs_dir} 仅剩 ${avail_kb:-未知}KB。"
  fi

  # 3) 操作确认（防误操作）
  if ! confirm "即将创建并启用 ${SWAP_SIZE_MB}MB swap 文件 ${SWAP_FILE}，是否继续？"; then
    log "已取消。"
    exit 0
  fi

  # 4) 创建 swap 文件
  if command -v fallocate >/dev/null 2>&1; then
    if ! fallocate -l "${SWAP_SIZE_MB}M" "$SWAP_FILE" 2>/dev/null; then
      warn "fallocate 失败（可能文件系统不支持），改用 dd 写入。"
      dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$SWAP_SIZE_MB" status=progress
    fi
  else
    dd if=/dev/zero of="$SWAP_FILE" bs=1M count="$SWAP_SIZE_MB" status=progress
  fi

  chmod 600 "$SWAP_FILE" || die "设置 ${SWAP_FILE} 权限失败。"
  mkswap "$SWAP_FILE"    || die "mkswap 失败。"
  swapon "$SWAP_FILE"    || die "swapon 失败。"

  # 5) 开机自动挂载
  if grep -qE "^${SWAP_FILE}[[:space:]]" /etc/fstab; then
    ok "fstab 已包含 ${SWAP_FILE} 条目，跳过写入。"
  else
    cp -a /etc/fstab "/etc/fstab.bak.$(date +%Y%m%d%H%M%S)"
    printf '%s\n' "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
    ok "已写入 /etc/fstab（开机自动挂载）。"
  fi

  log "----- 开启结果 -----"
  swapon --show
  free -h
}

do_disable() {
  require_root

  local is_active=0
  if swapfile_active; then is_active=1; fi

  if [ "$is_active" -eq 0 ] && [ ! -e "$SWAP_FILE" ]; then
    warn "未找到 swap 文件 ${SWAP_FILE}，且其未处于启用状态。"
    log "如需查看全部 swap，请执行：sudo bash $0 status"
    exit 0
  fi

  # 操作确认（防误操作）
  if ! confirm "即将关闭并删除 ${SWAP_FILE}（含移除开机挂载配置），是否继续？"; then
    log "已取消。"
    exit 0
  fi

  # 1) 关闭 swap
  if [ "$is_active" -eq 1 ]; then
    swapoff "$SWAP_FILE" || die "swapoff 失败（可能内存不足，无法释放），文件未删除。"
    ok "已关闭 swap：$SWAP_FILE"
  fi

  # 2) 移除开机自动挂载
  if grep -qE "^${SWAP_FILE}[[:space:]]" /etc/fstab; then
    cp -a /etc/fstab "/etc/fstab.bak.$(date +%Y%m%d%H%M%S)"
    sed -i "\#^${SWAP_FILE}[[:space:]]#d" /etc/fstab
    ok "已从 /etc/fstab 移除 ${SWAP_FILE} 条目。"
  else
    ok "fstab 中无 ${SWAP_FILE} 条目，跳过。"
  fi

  # 3) 删除文件
  if [ -e "$SWAP_FILE" ]; then
    rm -f "$SWAP_FILE" && ok "已删除文件：$SWAP_FILE"
  fi

  log "----- 关闭结果 -----"
  swapon --show 2>/dev/null || log "（当前无活动 swap）"
  free -h
}

do_status() {
  log "===== Swap 状态 ====="
  log "活动 swap（swapon --show）："
  swapon --show 2>/dev/null || log "（无）"
  log ""
  log "内存（free -h）："
  free -h
  log ""
  if [ -e "$SWAP_FILE" ]; then
    log "swap 文件存在：$SWAP_FILE（$(du -h "$SWAP_FILE" 2>/dev/null | cut -f1)）"
  else
    log "swap 文件不存在：$SWAP_FILE"
  fi
  if grep -qE "^${SWAP_FILE}[[:space:]]" /etc/fstab; then
    log "fstab 挂载条目：存在"
  else
    log "fstab 挂载条目：无"
  fi
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    on|enable|start)  do_enable ;;
    off|disable|stop) do_disable ;;
    status|show)      do_status ;;
    -h|--help|help|"") usage; exit 0 ;;
    *) err "未知命令：$cmd"; usage; exit 2 ;;
  esac
}

main "$@"
