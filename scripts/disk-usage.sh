#!/usr/bin/env bash
# =============================================================================
# disk-usage.sh — 磁盘占用分析
#
# 扫描指定目录（默认 /），按占用空间降序输出前 N 大目录/文件，
# 结果同时输出到终端与日志文件，并单独列出大于指定阈值的大文件。
#
# 用法：
#   sudo bash disk-usage.sh [-d 目录] [-l 日志文件] [-n 前N名] [-s 大文件阈值]
#
# 示例：
#   sudo bash disk-usage.sh                          # 分析根目录，前 20，日志默认 /var/log/disk_usage_analysis.log
#   sudo bash disk-usage.sh -d /var/lib/docker -n 30
#   sudo bash disk-usage.sh -d / -l /tmp/du.log -s 200M
# =============================================================================
set -uo pipefail

TARGET_DIR="/"
LOG_FILE="/var/log/disk_usage_analysis.log"
TOP_N=20
BIG_SIZE="100M"

usage() {
  cat <<'EOF'
用法: sudo bash disk-usage.sh [-d 目录] [-l 日志文件] [-n 前N名] [-s 大文件阈值]

选项:
  -d <目录>   要扫描的目录（默认 /）
  -l <文件>   日志文件路径（默认 /var/log/disk_usage_analysis.log）
  -n <数量>   输出前 N 大项目（默认 20）
  -s <大小>   大文件阈值，如 100M / 1G（默认 100M）
  -h          显示本帮助

说明:
  - 建议用 sudo 运行，否则无权限目录会被跳过、日志可能写不进 /var/log。
  - 扫描时限定在同一文件系统（-xdev），自动跳过 /proc、/sys、/dev 等虚拟挂载点，
    如需分析独立分区请直接指定该分区挂载点，如 -d /var。

示例:
  sudo bash disk-usage.sh                          # 分析根目录（前 20）
  sudo bash disk-usage.sh -d /var/lib/docker -n 30
  sudo bash disk-usage.sh -d / -l /tmp/du.log -s 200M
EOF
}

while getopts "d:l:n:s:h" opt; do
  case "$opt" in
    d) TARGET_DIR="$OPTARG" ;;
    l) LOG_FILE="$OPTARG" ;;
    n) TOP_N="$OPTARG" ;;
    s) BIG_SIZE="$OPTARG" ;;
    h) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

# ---------- 参数校验与规范化 ----------
[ -z "$TARGET_DIR" ] && TARGET_DIR="/"
TARGET_DIR="${TARGET_DIR%/}"          # 去末尾斜杠
[ -z "$TARGET_DIR" ] && TARGET_DIR="/"

if [ ! -d "$TARGET_DIR" ]; then
  echo "错误：目录不存在：$TARGET_DIR" >&2
  exit 1
fi

case "$TOP_N" in
  ''|*[!0-9]*|[0]*) echo "错误：-n 必须为正整数" >&2; exit 2 ;;
esac

# ---------- 日志文件可写性检查（/var/log 通常需 root） ----------
if [ -n "$LOG_FILE" ]; then
  LOG_DIR="$(dirname "$LOG_FILE")"
  if ! { [ -d "$LOG_DIR" ] && { [ -w "$LOG_DIR" ] || [ "$(id -u)" -eq 0 ]; }; }; then
    echo "警告：无法写入日志目录 $LOG_DIR（请用 sudo 运行），本次仅输出到终端。" >&2
    LOG_FILE=""
  fi
fi

# ---------- 同时输出到终端与日志 ----------
out() {
  printf '%s\n' "$1"
  [ -n "$LOG_FILE" ] && printf '%s\n' "$1" >> "$LOG_FILE"
}

LINE="================================================================================"
TS="$(date '+%Y-%m-%d %H:%M:%S %z')"

out "$LINE"
out "磁盘占用分析报告"
out "扫描时间：$TS"
out "扫描目录：$TARGET_DIR"
out "大文件阈值：$BIG_SIZE"
out "$LINE"

# ---------- 1) 磁盘总体使用率 ----------
out ""
out "【1/3】磁盘总体使用率概览 (df -h)"
out "$LINE"
df -h 2>/dev/null | while IFS= read -r line; do out "$line"; done

# ---------- 2) 前 N 大目录/文件 ----------
out ""
out "【2/3】占用空间最大的前 ${TOP_N} 个项目"
out "$LINE"
du -xh --max-depth=1 "$TARGET_DIR" 2>/dev/null \
  | sort -rh \
  | awk -v base="$TARGET_DIR" '$2 != base' \
  | head -n "$TOP_N" \
  | while IFS= read -r line; do out "$line"; done
out "（目标目录总计：$(du -sh "$TARGET_DIR" 2>/dev/null | cut -f1)）"

# ---------- 3) 大文件清单 ----------
out ""
out "【3/3】大于 ${BIG_SIZE} 的文件清单"
out "$LINE"
big_count="$(find "$TARGET_DIR" -xdev -type f -size +"$BIG_SIZE" 2>/dev/null | wc -l | tr -d ' ')"
out "共 ${big_count} 个文件大于 ${BIG_SIZE}："
if [ "$big_count" -gt 0 ]; then
  find "$TARGET_DIR" -xdev -type f -size +"$BIG_SIZE" -exec du -h {} + 2>/dev/null \
    | sort -rh \
    | while IFS= read -r line; do out "$line"; done
fi

out ""
out "分析完成：$(date '+%Y-%m-%d %H:%M:%S %z')"
out "$LINE"
