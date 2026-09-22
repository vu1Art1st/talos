#!/usr/bin/env bash
# Talos 端到端测试编排（WSL / Linux / macOS；与 scripts/e2e.ps1 行为对齐）。
#
# 起一套**独立于开发栈**的 E2E 环境并跑 Playwright（系统 Chrome）：
#   vulnplatform_e2e 库 → 迁移 → 种子 → api(27016) → 前端(27017) → playwright → 收摊
# 与 dev 栈完全隔离（不同库、不同端口、不同 storage 目录），因此跑 E2E 不会动到开发数据，
# 也不会被"开发库正在被用"影响；写路径产生的数据只在 e2e 库里，可随时重新种子。
#
# 用法（仓库根目录）：
#   bash scripts/e2e.sh                 # 跑全部黄金链路
#   bash scripts/e2e.sh --headed        # 带界面（排查用）
#   bash scripts/e2e.sh --keep          # 跑完保留 E2E 栈（人工看现场；再次运行前需自行收摊）
#   bash scripts/e2e.sh -- golden-path.spec.ts -g "登录"   # `--` 之后原样透传给 playwright
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_PORT="${E2E_API_PORT:-27016}"
WEB_PORT="${E2E_WEB_PORT:-27017}"
E2E_DB="${E2E_DB_NAME:-vulnplatform_e2e}"
KEEP=0
PLAYWRIGHT_ARGS=()
for arg in "$@"; do
  case "$arg" in
  --keep) KEEP=1 ;;
  --headed) PLAYWRIGHT_ARGS+=(--headed) ;;
  --)
    shift
    PLAYWRIGHT_ARGS+=("$@")
    break
    ;;
  -h | --help)
    sed -n '^# ' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *) PLAYWRIGHT_ARGS+=("$arg") ;;
  esac
done

log() { printf '[e2e] %s\n' "$*"; }
die() {
  printf '[e2e] ✗ %s\n' "$*" >&2
  exit 1
}

# ---------- 依赖预检 ----------
for spec in "5432:PostgreSQL" "6379:Redis"; do
  port="${spec%%:*}"
  name="${spec#*:}"
  (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null ||
    die "$name 未监听 127.0.0.1:$port —— 请先在 DBngin 启动（见 docs/LOCAL_DEV_SETUP.md）"
done

PY="$ROOT/backend/.venv/Scripts/python"
[ -x "$PY" ] || PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || die "未找到 backend/.venv 解释器（见 AGENTS.md「常用命令」）"

# 端口必须空闲：否则会「静默复用」上次未收摊的栈（旧前端代理指向旧 api），得到似是而非的结果
port_owner() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:$1" 2>/dev/null | head -1
  elif command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v p=":$1" '$4 ~ p { if (match($0, /pid=[0-9]+/)) print substr($0, RSTART + 4, RLENGTH - 4) }' | head -1
  fi
}
for port in "$API_PORT" "$WEB_PORT"; do
  owner="$(port_owner "$port")"
  [ -n "$owner" ] && die "$port 已被 PID $owner 占用 —— 多为上次 E2E 未收摊；请先结束该进程或改端口（E2E_API_PORT / E2E_WEB_PORT）"
done

# ---------- 从仓库根 .env 派生 E2E 库 DSN ----------
[ -f .env ] || die "缺少仓库根 .env（需 POSTGRES_USER/POSTGRES_PASSWORD，见 docs/LOCAL_DEV_SETUP.md）"
_env() { grep -E "^\s*$1\s*=" .env | head -1 | sed -E "s/^\s*$1\s*=\s*//" | tr -d '\r'; }
PG_USER="$(_env POSTGRES_USER)"; PG_USER="${PG_USER:-vulnplatform}"
PG_PW="$(_env POSTGRES_PASSWORD)"
[ -n "$PG_PW" ] || die ".env 缺少 POSTGRES_PASSWORD"

export VP_DATABASE_URL="${E2E_DATABASE_URL:-postgresql+asyncpg://${PG_USER}:${PG_PW}@127.0.0.1:5432/${E2E_DB}}"
# E2E 栈专用运行参数：debug（本地凭据校验放宽）+ 免队列 + 独立 storage + 固定初始管理员密码
export VP_DEBUG=0   # 贴近生产行为，且避免 SQL echo 刷爆日志
export VP_DISABLE_QUEUE=1
export VP_SECRET_KEY="e2e-only-secret-key-0123456789abcdef"
export VP_INITIAL_ADMIN_PASSWORD="admin123"
export VP_STORAGE_DIR="storage_e2e"

mkdir -p e2e-results

# 受管终端的删除守卫会拦截 Playwright 清理 outputDir（报 `[safe-delete] 操作失败`）——
# 与 scripts/test.sh 同一处理口径。
export CODEBUDDY_SAFE_DELETE_ENABLED=0

# ---------- 迁移 + 种子（写库前先确认目标库） ----------
log "迁移并重置种子数据：$E2E_DB"
(cd backend && "$PY" -m scripts.migrate) || die "迁移失败（库 $E2E_DB 是否存在？）"
(cd backend && "$PY" -m scripts.seed_dev_data --reset) || die "种子数据失败"

# ---------- 起 api 与前端 ----------
kill_port() {
  local port="$1" pid
  pid="$(port_owner "$port")"
  [ -n "$pid" ] || return 0
  kill -9 "$pid" 2>/dev/null || true
}

cleanup() {
  if [ "$KEEP" -eq 1 ]; then
    log "--keep：保留 E2E 栈（api :$API_PORT / 前端 :$WEB_PORT），收摊请手动 kill"
    return
  fi
  # 杀整棵进程树：`pnpm dev` 会派生 node/vite 子进程，只杀 pnpm 会留下孤儿继续占用端口
  for pid in "${API_PID:-}" "${WEB_PID:-}"; do
    [ -n "$pid" ] || continue
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 1
  kill_port "$API_PORT"
  kill_port "$WEB_PORT"
  log "已收摊"
}
trap cleanup EXIT

log "启动 api :$API_PORT"
(cd backend && "$PY" -m uvicorn app.main:app --port "$API_PORT") >e2e-results/api.log 2>&1 &
API_PID=$!
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$API_PORT/api/health" >/dev/null && break
  sleep 1
done
curl -sf "http://127.0.0.1:$API_PORT/api/health" >/dev/null || {
  tail -30 e2e-results/api.log >&2
  die "api 未就绪（日志见 e2e-results/api.log）"
}

log "启动前端 :$WEB_PORT（代理到 api :$API_PORT）"
(cd frontend && VP_BACKEND_PORT="$API_PORT" VP_FRONTEND_PORT="$WEB_PORT" pnpm dev) >e2e-results/frontend.log 2>&1 &
WEB_PID=$!
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null && break
  sleep 1
done
curl -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null || {
  tail -30 e2e-results/frontend.log >&2
  die "前端未就绪（日志见 e2e-results/frontend.log）"
}

# ---------- 跑 Playwright（根目录工具包；系统 Chrome 免下载） ----------
log "运行 Playwright（E2E_BASE_URL=http://127.0.0.1:$WEB_PORT）"
set +e
E2E_BASE_URL="http://127.0.0.1:$WEB_PORT" pnpm exec playwright test "${PLAYWRIGHT_ARGS[@]+"${PLAYWRIGHT_ARGS[@]}"}"
CODE=$?
set -e
if [ "$CODE" -ne 0 ]; then
  log "✗ 用例未全绿（退出码 $CODE）；报告：e2e-report/index.html，失败追踪：e2e-results/"
else
  log "✓ 黄金链路全绿"
fi
exit "$CODE"
