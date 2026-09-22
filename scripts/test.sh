#!/usr/bin/env bash
# Talos 后端测试入口（PostgreSQL 单栈；本地、WSL、CI 共用）。
#
# 为什么需要它：跑测试有一串「记错就得到误导性结果」的必带项，本脚本把它们固化——
#   1) 受管终端（WorkBuddy / CodeBuddy 沙箱）的删除守卫会打断 pytest 清理 basetemp，
#      缺 CODEBUDDY_SAFE_DELETE_ENABLED=0 时的症状是「单个文件全绿、全量几十个 ERROR」；
#   2) --basetemp 必须落在仓库内（系统临时目录会被守卫视为越界删除目标），且每次运行唯一
#      （共用固定目录时并发跑两份测试会互相删掉对方的临时文件）；
#   3) 测试库 schema 由 conftest 按进程派生（VP_DB_SCHEMA），无需在此指定；但残留 schema
#      可用 --prune 清理。
#
# 用法（仓库根目录）：
#   bash scripts/test.sh                          # 全量（串行）
#   bash scripts/test.sh -k retest -x             # 透传 pytest 参数
#   bash scripts/test.sh --workers 4              # 4 进程并行（--dist loadscope）
#   bash scripts/test.sh --no-deps-check          # 跳过 5432/6379 预检（CI 由 services 保证）
#   bash scripts/test.sh --prune --yes            # 清理残留 test_* schema 与 basetemp 后退出
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"

WORKERS=""
DO_DEPS_CHECK=1
PRUNE=0
CONFIRM=0
PYTEST_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
  --workers)
    WORKERS="${2:-}"
    [ -n "$WORKERS" ] || { echo "[test] --workers 需要一个数值参数（如 --workers 4）"; exit 2; }
    case "$WORKERS" in
    *[!0-9]* | '')
      echo "[test] --workers 只接受正整数：$WORKERS"
      exit 2
      ;;
    esac
    shift 2
    ;;
  --no-deps-check)
    DO_DEPS_CHECK=0
    shift
    ;;
  --prune)
    PRUNE=1
    shift
    ;;
  --yes)
    CONFIRM=1
    shift
    ;;
  -h | --help)
    sed -n '^# ' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    PYTEST_ARGS+=("$1")
    shift
    ;;
  esac
done

# ---------- 解释器（宿主机一律用项目 venv，禁止系统 python） ----------
if [ -x "$BACKEND/.venv/bin/python" ]; then
  PY="$BACKEND/.venv/bin/python"
elif [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then
  PY="$BACKEND/.venv/Scripts/python.exe"
else
  echo "[test] 未找到 backend/.venv，请先按 AGENTS.md「常用命令」用 uv 创建并安装依赖"
  exit 1
fi

# ---------- 清理模式 ----------
if [ "$PRUNE" -eq 1 ]; then
  if [ "$CONFIRM" -ne 1 ]; then
    echo "[test] --prune 会删除残留的 test_* schema 与 basetemp；确认无并发测试在跑后加 --yes 执行"
    exit 2
  fi
  (cd "$BACKEND" && "$PY" -m scripts.prune_test_schemas --yes)
  if [ -d "$BACKEND/_pytest_tmp" ]; then
    rm -rf "${BACKEND:?}/_pytest_tmp"/* || true
    echo "[test] 已清理 basetemp 目录"
  fi
  exit 0
fi

# ---------- 依赖服务预检 ----------
port_listening() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE "[:.]${port} "
  elif command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -qE "[:.]${port} .*LISTEN"
  else
    (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null
  fi
}
if [ "$DO_DEPS_CHECK" -eq 1 ]; then
  for spec in "5432:PostgreSQL(DBngin)" "6379:Redis(DBngin)"; do
    port="${spec%%:*}"
    name="${spec#*:}"
    if ! port_listening "$port"; then
      echo "[test] ⚠ $name 未监听 127.0.0.1:$port —— 测试库/限流依赖它，请先启动（见 docs/LOCAL_DEV_SETUP.md）"
      exit 1
    fi
  done
fi

# ---------- 运行 ----------
BASETEMP="$BACKEND/_pytest_tmp/run_$$_$(date +%s)"
mkdir -p "$BASETEMP"
cleanup() { rm -rf "$BASETEMP" 2>/dev/null || true; }
trap cleanup EXIT

PYTEST_ARGS=(-p no:cacheprovider --basetemp="$BASETEMP" "${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"}")
if [ -n "$WORKERS" ]; then
  # loadscope：同一测试模块（用例间存在累积状态依赖）不拆到不同 worker
  PYTEST_ARGS=(-n "$WORKERS" --dist loadscope "${PYTEST_ARGS[@]}")
  echo "[test] 并行执行：$WORKERS 个 worker（每个 worker 独占一个 PostgreSQL schema）"
fi

echo "[test] $PY -m pytest ${PYTEST_ARGS[*]}"
cd "$BACKEND"
CODEBUDDY_SAFE_DELETE_ENABLED=0 "$PY" -m pytest "${PYTEST_ARGS[@]}"
