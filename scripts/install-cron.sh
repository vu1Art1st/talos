#!/usr/bin/env bash
# 安装 Talos 备份 cron 定时任务（幂等）。建议以 root 运行，装到 root crontab，
# 这样 cron 里的备份脚本直接以 root 执行，无需 sudo 交互。
# 用法： sudo bash scripts/install-cron.sh
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
mkdir -p backups

MARKER="# talos-backup-cron"
DIFF_LINE="0 2 * * * cd ${ROOT} && mkdir -p backups && bash scripts/backup-incremental.sh >> ${ROOT}/backups/cron.log 2>&1"
ANCHOR_LINE="0 3 1 * * cd ${ROOT} && mkdir -p backups && bash scripts/backup.sh >> ${ROOT}/backups/cron.log 2>&1"

# 幂等：移除旧 talos 备份 cron 行后重写
TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'talos-backup-cron\|backup-incremental.sh\|scripts/backup.sh' > "$TMP" || true
{
  cat "$TMP"
  echo "$MARKER"
  echo "$DIFF_LINE"
  echo "$ANCHOR_LINE"
} | crontab -
rm -f "$TMP"

echo "已安装 cron 定时任务（当前用户 crontab）："
crontab -l | grep -A2 "$MARKER"
