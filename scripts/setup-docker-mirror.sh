#!/usr/bin/env bash
# 配置 Docker 使用腾讯云镜像加速，加快从 docker.io 官方源拉取基础镜像。
#
# 用法：
#   sudo bash scripts/setup-docker-mirror.sh
#
# 说明：
#   - 默认公网加速地址 https://mirror.ccs.tencent.com；
#     腾讯云 CVM 内网可用 https://mirror.ccs.tencentyun.com（更快，免公网流量）；
#     可用环境变量 DOCKER_MIRROR 覆盖，如：
#       sudo DOCKER_MIRROR=https://mirror.ccs.tencentyun.com bash scripts/setup-docker-mirror.sh
#   - 脚本会合并保留 /etc/docker/daemon.json 中已有配置；
#   - 修改后需重启 Docker 生效：systemctl restart docker
#   - 若需临时绕过加速（拉取加速器未同步的镜像），可 docker pull 后删除加速配置。
set -euo pipefail

MIRROR="${DOCKER_MIRROR:-https://mirror.ccs.tencent.com}"
DAEMON_JSON="/etc/docker/daemon.json"

if [ "$(id -u)" -ne 0 ]; then
  echo "请以 root 运行：sudo bash $0" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "缺少 python3，无法合并 JSON 配置" >&2
  exit 1
fi

tmp="$(mktemp)"
if [ -f "$DAEMON_JSON" ]; then
  python3 - "$MIRROR" < "$DAEMON_JSON" > "$tmp" <<'PY'
import json
import sys

mirror = sys.argv[1]
data = json.load(sys.stdin)
mirrors = list(data.get("registry-mirrors") or [])
if mirror not in mirrors:
    mirrors.append(mirror)
data["registry-mirrors"] = mirrors
json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
sys.stdout.write("\n")
PY
else
  printf '{\n  "registry-mirrors": ["%s"]\n}\n' "$MIRROR" > "$tmp"
fi

install -m 644 "$tmp" "$DAEMON_JSON"
rm -f "$tmp"

echo "已写入 $DAEMON_JSON："
cat "$DAEMON_JSON"
echo
echo "请执行以下命令重启 Docker 使配置生效："
echo "  sudo systemctl restart docker"
echo
echo "验证（拉取时走加速镜像）："
echo "  docker info | grep -A3 'Registry Mirrors'"
