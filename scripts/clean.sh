#!/usr/bin/env bash
# Talos 本地垃圾文件清理（Linux / macOS / WSL；与 scripts/clean.ps1 行为对齐）。
#
# 定位：**只清可再生的本地产物**（缓存 / 临时 / 构建输出 / 测试残留），
# 绝不碰数据类目录（备份、本机数据库、应用存储、venv、node_modules）。
#
# 用法（仓库根目录）：
#   bash scripts/clean.sh              # 预演（只列出，不删）
#   bash scripts/clean.sh --apply      # 实际删除
#   bash scripts/clean.sh --apply --include-venv   # 连 .venv 内 __pycache__ 一起清
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APPLY=0
INCLUDE_VENV=0
for arg in "$@"; do
  case "$arg" in
  --apply) APPLY=1 ;;
  --include-venv) INCLUDE_VENV=1 ;;
  -h | --help)
    sed -n '^# ' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    echo "[clean] 未知参数：$arg（可用：--apply / --include-venv）"
    exit 2
    ;;
  esac
done

# 绝不删除的路径（数据 / 依赖 / 配置）：任何目标命中即中止
PROTECTED=(.git .env .env.local dev-database backups backend/storage backend/.venv
  frontend/node_modules .codebuddy .qoder .workbuddy design-demos)

assert_not_protected() {
  local rel="${1#"$ROOT"/}"
  for p in "${PROTECTED[@]}"; do
    if [ "$rel" = "$p" ] || [[ "$rel" == "$p/"* ]]; then
      echo "[clean] 目标命中受保护路径，已中止：$rel"
      exit 1
    fi
  done
}

TARGETS=()
# 1) Python 缓存（默认排除 .venv / node_modules）
while IFS= read -r -d '' d; do
  if [ "$INCLUDE_VENV" -eq 0 ] && [[ "$d" == */.venv/* ]]; then continue; fi
  [[ "$d" == */node_modules/* ]] && continue
  TARGETS+=("$d")
done < <(find "$ROOT" -type d -name __pycache__ -print0 2>/dev/null)

# 2) 工具缓存与测试临时目录
for rel in .pytest_cache backend/.pytest_cache backend/.ruff_cache backend/_pytest_tmp; do
  [ -e "$ROOT/$rel" ] && TARGETS+=("$ROOT/$rel")
done

# 3) 前端构建产物
for rel in frontend/dist frontend/dist_check; do
  [ -e "$ROOT/$rel" ] && TARGETS+=("$ROOT/$rel")
done

# 4) 测试存储残留（清内容，保留目录）
if [ -d "$ROOT/backend/tests/test_storage" ]; then
  while IFS= read -r -d '' f; do TARGETS+=("$f"); done \
    < <(find "$ROOT/backend/tests/test_storage" -mindepth 1 -maxdepth 1 -print0 2>/dev/null)
fi

# 5) 本地临时日志（仓库根与 backend：_*.txt / _*.log）
while IFS= read -r -d '' f; do TARGETS+=("$f"); done \
  < <(find "$ROOT" "$ROOT/backend" -maxdepth 1 -type f \( -name '_*.txt' -o -name '_*.log' \) -print0 2>/dev/null)

if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "[clean] 没有可清理的产物（仓库已干净）"
  exit 0
fi

size_of() {
  if [ -d "$1" ]; then du -sk "$1" 2>/dev/null | awk '{print $1 * 1024}'; else stat -c %s "$1" 2>/dev/null || echo 0; fi
}

TOTAL=0
if [ "$APPLY" -eq 1 ]; then
  echo "[clean] 命中 ${#TARGETS[@]} 项（--apply 实际删除）"
else
  echo "[clean] 命中 ${#TARGETS[@]} 项（预演，未删除；加 --apply 执行）"
fi
for t in "${TARGETS[@]}"; do
  assert_not_protected "$t"
  s="$(size_of "$t")"
  TOTAL=$((TOTAL + s))
  printf '  %10s KB  %s\n' "$(awk -v v="$s" 'BEGIN{printf "%.1f", v/1024}')" "${t#"$ROOT"/}"
done
awk -v t="$TOTAL" 'BEGIN{printf "[clean] 合计可释放 %.1f MB\n", t/1048576}'

if [ "$APPLY" -eq 1 ]; then
  for t in "${TARGETS[@]}"; do
    assert_not_protected "$t"
    rm -rf -- "$t" || echo "[clean] ⚠ 删除失败（可能被占用）：$t"
  done
  echo "[clean] 已清理完毕（若仍有残留，多因正在运行的 python/uvicorn 占用 __pycache__）"
fi
