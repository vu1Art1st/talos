#!/usr/bin/env bash
# Talos 一键本地开发脚本（Linux / macOS）
# - 后端：SQLite + 免队列模式，无需 Postgres/Redis，http://localhost:8000
# - 前端：Vite Dev Server，http://localhost:5173
# 用法：bash dev.sh
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

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

echo "[dev] 启动后端 http://localhost:8000 （SQLite + 免队列）"
(
  cd "$BACKEND"
  # 开发模式：开启 DEBUG（放宽密钥校验、暴露 API 文档），固定内置 admin 初始口令
  VP_DATABASE_URL='sqlite+aiosqlite:///./dev.db' VP_DISABLE_QUEUE=1 VP_DEBUG=1 VP_INITIAL_ADMIN_PASSWORD='admin123' \
    exec "$BACKEND/.venv/bin/python" -m uvicorn app.main:app --reload --port 8000
) &
BACKEND_PID=$!
trap 'echo "[dev] 停止后端..."; kill $BACKEND_PID 2>/dev/null || true' EXIT

echo ""
echo "  前端:     http://localhost:5173"
echo "  API 文档: http://localhost:8000/api/docs"
echo "  默认账号: admin / admin123"
echo "  Ctrl+C 退出（自动停止后端）"
echo ""

cd "$FRONTEND"
npm run dev
