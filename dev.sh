#!/usr/bin/env bash
# Talos 一键本地开发脚本（Linux / macOS）
# - 数据库：PostgreSQL 16 + Redis 7，由 DBngin 原生托管（本机 127.0.0.1:5432 / 6379，见 docs/LOCAL_DEV_SETUP.md）
#   凭据复用仓库根目录 .env 的 POSTGRES_USER / POSTGRES_PASSWORD；开发库 = POSTGRES_DB（默认 vulnplatform）
# - 后端：免队列模式（后台任务进程内执行，无需另开 arq worker），绑定 0.0.0.0:${BACKEND_PORT}
# - 前端：Vite Dev Server，绑定 0.0.0.0:${FRONTEND_PORT}，支持通过 VPS_IP:PORT 外部访问
# - 内置端口冲突检测与健康检查：启动前检测端口占用；启动后轮询 HTTP 确认服务真正响应，
#   发现端口冲突或「假启动」（进程存在但服务未监听）时明确提示并给出处理建议
# 用法：bash dev.sh
# 可选：FRONTEND_PORT=xxxxx BACKEND_PORT=xxxxx HEALTH_TIMEOUT=60 bash dev.sh 覆盖默认值
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# 默认端口：前端 27014，后端 27015（可用环境变量覆盖）
FRONTEND_PORT="${FRONTEND_PORT:-27014}"
BACKEND_PORT="${BACKEND_PORT:-27015}"
# 健康检查：等待服务可响应（HTTP）的最长秒数与轮询间隔
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-1}"
# 后端健康检查路径：无需鉴权，未登录返回 401 同样证明服务已存活
BACKEND_HEALTH_PATH="/api/v1/meta"
# 前端健康检查路径：Vite 根路径返回 200
FRONTEND_HEALTH_PATH="/"

for cmd in node pnpm curl; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "[dev] 未找到 $cmd，请先安装后重试"; exit 1; }
done

# 后端解释器：优先 uv（可自行管理并下载 Python 3.12，与容器 python:3.12-slim 对齐），否则需系统 python3
if ! command -v uv >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "[dev] 需要 uv（推荐，https://docs.astral.sh/uv/）或 python3 之一"
  exit 1
fi

# ---------- 端口检测工具（兼容 Linux / macOS） ----------

# 端口是否处于 LISTEN 状态
is_port_listening() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE "[:.]${port} "
  elif command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -qE "[:.]${port} .*LISTEN"
  else
    # 兜底：bash 内建 TCP，直接尝试建立连接
    (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null
  fi
}

# 获取监听指定端口的进程 PID（尽力而为，无权限/无工具时返回空）
pid_on_port() {
  local port=$1
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | head -1
  elif command -v fuser >/dev/null 2>&1; then
    fuser "$port/tcp" 2>/dev/null | tr -d ' '
  fi
}

# 按 PID 取进程名
proc_name() {
  local proc_id=$1
  [ -n "$proc_id" ] && ps -p "$proc_id" -o comm= 2>/dev/null | head -1
}

# HTTP 探测：任何响应（含 401/404）都视为服务已监听
http_ok() {
  local port=$1 path=$2
  curl -s -o /dev/null --max-time 2 "http://127.0.0.1:${port}${path}" 2>/dev/null
}

# 轮询等待服务就绪
wait_service_ready() {
  local port=$1 name=$2 path=$3 i
  for ((i = 0; i < HEALTH_TIMEOUT; i++)); do
    if http_ok "$port" "$path"; then
      echo "[dev] $name 已就绪 http://127.0.0.1:${port}${path}"
      return 0
    fi
    sleep "$HEALTH_INTERVAL"
  done
  return 1
}

# ---------- 提示信息 ----------

# 端口冲突提示 + 处理建议
print_conflict_advice() {
  local port=$1 name=$2 proc_id=$3 pname=$4
  echo ""
  echo "[dev] ⚠ 端口 $port 已被占用，$name 无法启动！"
  if [ -n "$proc_id" ]; then
    echo "[dev] 占用进程: PID $proc_id（${pname:-未知进程}）"
  else
    echo "[dev] 占用进程: 无法识别（权限不足或工具缺失）"
  fi
  echo "[dev] 该端口被占用时进程可能「假启动」（进程存在但服务监听失败）。"
  echo "[dev] 处理建议（任选其一）："
  echo "[dev]   1) 终止占用进程："
  if [ -n "$proc_id" ]; then
    echo "[dev]        Linux/macOS:  kill -9 $proc_id"
    echo "[dev]        Windows:      taskkill /PID $proc_id /F"
  fi
  echo "[dev]   2) 更换端口启动："
  echo "[dev]        Linux/macOS:  FRONTEND_PORT=27016 BACKEND_PORT=27017 bash dev.sh"
  echo "[dev]        Windows:      .\\dev.ps1 -FrontendPort 27016 -BackendPort 27017"
  echo "[dev] 处理完成后重新运行本脚本。"
}

# 假启动（进程在但服务未响应）提示 + 处理建议
print_fake_start_advice() {
  local port=$1 name=$2 path=$3 extra=$4
  echo ""
  echo "[dev] ⚠ $name 启动超时（${HEALTH_TIMEOUT} 秒内未响应 http://127.0.0.1:${port}${path}）"
  echo "[dev] 进程可能仍在但服务未正常监听（假启动）。"
  echo "[dev] 请查看上方 $name 启动日志中的错误（Traceback / 报错信息）。"
  echo "[dev] 常见原因：端口被占用、数据库被锁、依赖缺失、磁盘空间不足。"
  [ -n "$extra" ] && echo "[dev] $extra"
  echo "[dev] 可终止相关进程后重新运行本脚本。"
}

# ---------- 端口预检 ----------
check_port_free() {
  local port=$1 name=$2 pid pname
  if is_port_listening "$port"; then
    pid=$(pid_on_port "$port")
    pname=$(proc_name "$pid")
    print_conflict_advice "$port" "$name" "$pid" "$pname"
    exit 1
  fi
}

echo "[dev] 预检端口占用（端口冲突检测）..."
check_port_free "$BACKEND_PORT" "后端"
check_port_free "$FRONTEND_PORT" "前端"
echo "[dev] 端口检查通过：$BACKEND_PORT / $FRONTEND_PORT 均空闲。"

# ---------- 依赖服务预检（DBngin 托管的 PostgreSQL / Redis） ----------
if ! is_port_listening 5432; then
  echo "[dev] ⚠ 依赖服务未启动：PostgreSQL (DBngin, 16) 未监听 127.0.0.1:5432！"
  echo "[dev] 请先打开 DBngin 启动对应服务（建库步骤见 docs/LOCAL_DEV_SETUP.md）。"
  exit 1
fi
if ! is_port_listening 6379; then
  echo "[dev] ⚠ 依赖服务未启动：Redis (DBngin, 7.x) 未监听 127.0.0.1:6379！"
  echo "[dev] 请先打开 DBngin 启动对应服务（建库步骤见 docs/LOCAL_DEV_SETUP.md）。"
  exit 1
fi
echo "[dev] 依赖服务就绪：PostgreSQL(5432) / Redis(6379) 均在监听。"

# ---------- 解析根 .env 的 PostgreSQL 凭据（与 docker-compose 共用一份） ----------
PG_USER=""
PG_PASSWORD=""
PG_DB=""
if [ -f "$ROOT/.env" ]; then
  PG_USER=$(grep -E '^\s*POSTGRES_USER\s*=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d '[:space:]')
  PG_PASSWORD=$(grep -E '^\s*POSTGRES_PASSWORD\s*=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d '[:space:]')
  PG_DB=$(grep -E '^\s*POSTGRES_DB\s*=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d '[:space:]')
fi
if [ -z "$PG_USER" ] || [ -z "$PG_PASSWORD" ]; then
  echo "[dev] ⚠ 无法从仓库根目录 .env 解析 POSTGRES_USER / POSTGRES_PASSWORD！"
  echo "[dev] 请确认 .env 存在且包含这两项（与 docker-compose 部署共用同一份凭据）。"
  exit 1
fi
PG_DB="${PG_DB:-vulnplatform}"
echo "[dev] 数据库凭据已加载：用户 $PG_USER，库 $PG_DB（来自 .env）"

if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  echo "[dev] 初始化后端虚拟环境（Python 3.12）并安装依赖..."
  if command -v uv >/dev/null 2>&1; then
    # uv 可直接指定并用自身托管的 3.12 解释器，避免落到系统低版本 python
    uv venv "$BACKEND/.venv" --python 3.12
    uv pip install --python "$BACKEND/.venv/bin/python" -r "$BACKEND/requirements-dev.txt"
  else
    echo "[dev] 未检测到 uv，回退 python3 -m venv（请确保为 Python 3.12）"
    python3 -m venv "$BACKEND/.venv"
    "$BACKEND/.venv/bin/pip" install -r "$BACKEND/requirements-dev.txt"
  fi
fi

if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "[dev] 安装前端依赖..."
  (cd "$FRONTEND" && pnpm install)
fi

# ---------- 启动后端（后台）并等待就绪 ----------
echo "[dev] 启动后端 http://0.0.0.0:$BACKEND_PORT （PostgreSQL[DBngin] + Redis + 免队列）"
(
  cd "$BACKEND"
  # 开发模式：DBngin 托管 PostgreSQL + Redis + 免队列 + DEBUG + 固定内置 admin 初始口令。
  # --host 0.0.0.0：绑定所有网卡，否则仅 127.0.0.1 可访问（VPS 外部无法连接）
  # DISABLE_QUEUE=1：后台任务在 API 进程内执行，无需另开 arq worker（热重载友好）；
  # Redis 真实承担限流/登录锁定/token 轮换（不再走进程内降级）。
  VP_DATABASE_URL="postgresql+asyncpg://${PG_USER}:${PG_PASSWORD}@127.0.0.1:5432/${PG_DB}" \
  VP_REDIS_URL='redis://127.0.0.1:6379/0' VP_DISABLE_REDIS=0 VP_DISABLE_QUEUE=1 VP_DEBUG=1 \
  VP_INITIAL_ADMIN_PASSWORD='admin123' \
    exec "$BACKEND/.venv/bin/python" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!
trap 'echo "[dev] 停止后端..."; kill "$BACKEND_PID" 2>/dev/null || true' EXIT

if ! wait_service_ready "$BACKEND_PORT" "后端" "$BACKEND_HEALTH_PATH"; then
  print_fake_start_advice "$BACKEND_PORT" "后端" "$BACKEND_HEALTH_PATH" \
    "若为端口冲突，请先释放端口；若为数据库连接失败，请检查 DBngin 服务是否启动、.env 凭据是否正确后重试。"
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
fi

# ---------- 启动前端（后台，日志仍输出到终端）并等待就绪 ----------
echo "[dev] 启动前端 http://0.0.0.0:$FRONTEND_PORT （Vite Dev Server）"
(
  cd "$FRONTEND"
  # 传递端口给 vite.config.ts（前端页面通过 Vite 代理访问后端，外部只需放行前端端口）
  VP_FRONTEND_PORT="$FRONTEND_PORT" VP_BACKEND_PORT="$BACKEND_PORT" pnpm run dev
) &
FRONTEND_PID=$!
trap 'echo "[dev] 停止前后端..."; kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true' EXIT

if ! wait_service_ready "$FRONTEND_PORT" "前端" "$FRONTEND_HEALTH_PATH"; then
  print_fake_start_advice "$FRONTEND_PORT" "前端" "$FRONTEND_HEALTH_PATH"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  exit 1
fi

echo ""
echo "  前端(本机):  http://localhost:$FRONTEND_PORT"
echo "  前端(外部):  http://<VPS_IP>:$FRONTEND_PORT （需放行 $FRONTEND_PORT 端口）"
echo "  API 文档:    http://localhost:$BACKEND_PORT/api/docs"
echo "  默认账号:    admin / admin123"
echo "  Ctrl+C 退出（自动停止前后端）"
echo ""

# 前台等待前端退出；Ctrl+C 时由 EXIT trap 统一清理
wait "$FRONTEND_PID"
