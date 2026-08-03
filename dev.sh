#!/usr/bin/env bash
# Talos 一键本地开发脚本（Linux / macOS）
# - 后端：SQLite + 免队列模式，无需 Postgres/Redis，绑定 0.0.0.0:${BACKEND_PORT}
# - 前端：Vite Dev Server，绑定 0.0.0.0:${FRONTEND_PORT}，支持通过 VPS_IP:PORT 外部访问
# 用法：bash dev.sh
# 可选：FRONTEND_PORT=xxxxx BACKEND_PORT=xxxxx bash dev.sh 覆盖默认端口
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# 默认端口：前端 27014，后端 27015（可用环境变量覆盖）
FRONTEND_PORT="${FRONTEND_PORT:-27014}"
BACKEND_PORT="${BACKEND_PORT:-27015}"

for cmd in python3 node npm; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "[dev] 未找到 $cmd，请先安装后重试"; exit 1; }
done

if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  echo "[dev] 初始化后端虚拟环境并安装依赖..."
  python3 -m venv "$BACKEND/.venv"
  "$BACKEND/.venv/bin/pip" install -r "$BACKEND/requirements-dev.txt"
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "[dev] 安装前端依赖..."
  (cd "$FRONTEND" && npm install)
fi

echo "[dev] 启动后端 http://0.0.0.0:$BACKEND_PORT （SQLite + 免队列）"
(
  cd "$BACKEND"
  # 开发模式：开启 DEBUG（放宽密钥校验、暴露 API 文档），固定内置 admin 初始口令
  # --host 0.0.0.0：绑定所有网卡，否则仅 127.0.0.1 可访问（VPS 外部无法连接）
  VP_DATABASE_URL='sqlite+aiosqlite:///./dev.db' VP_DISABLE_QUEUE=1 VP_DEBUG=1 VP_INITIAL_ADMIN_PASSWORD='admin123' \
    exec "$BACKEND/.venv/bin/python" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!
trap 'echo "[dev] 停止后端..."; kill $BACKEND_PID 2>/dev/null || true' EXIT

echo ""
echo "  前端(本机):  http://localhost:$FRONTEND_PORT"
echo "  前端(外部):  http://<VPS_IP>:$FRONTEND_PORT （需放行 $FRONTEND_PORT 端口）"
echo "  API 文档:    http://localhost:$BACKEND_PORT/api/docs"
echo "  默认账号:    admin / admin123"
echo "  Ctrl+C 退出（自动停止后端）"
echo ""

cd "$FRONTEND"
# 传递端口给 vite.config.ts（前端页面通过 Vite 代理访问后端，外部只需放行前端端口）
VP_FRONTEND_PORT="$FRONTEND_PORT" VP_BACKEND_PORT="$BACKEND_PORT" npm run dev
