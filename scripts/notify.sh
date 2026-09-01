#!/usr/bin/env bash
# Talos 备份/运维告警：通过 webhook 推送文本（地址读 .env 的 BACKUP_WEBHOOK_URL）。
# 用法： bash scripts/notify.sh "消息内容"
set -uo pipefail

cd "$(dirname "$0")/.."

msg="${1:-}"
# 简单转义，避免消息里的双引号破坏 JSON
msg="${msg//\"/\'}"

url=""
if [ -f .env ]; then
  url="$(grep -E '^BACKUP_WEBHOOK_URL=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi

if [ -z "$url" ]; then
  echo "未配置 BACKUP_WEBHOOK_URL，跳过告警：$msg"
  exit 0
fi

command -v curl >/dev/null 2>&1 || { echo "缺少 curl，无法发送告警：$msg"; exit 1; }

curl -fsS -m 10 -X POST "$url" \
  -H 'Content-Type: application/json' \
  -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"[Talos备份] ${msg}\"}}" \
  || echo "告警发送失败：$msg"
