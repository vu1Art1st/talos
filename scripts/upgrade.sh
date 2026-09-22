#!/usr/bin/env bash
# Talos 一键升级：拉取代码 → 备份 → 重建镜像 → 清理构建缓存 → 迁移数据库结构 → 重启服务。
# 在运行着 docker compose 的服务器、仓库根目录执行： bash scripts/upgrade.sh
#
# 选项：
#   --no-backup   跳过升级前自动备份（默认会先备份，除非当前没有运行中的数据库）
#   --no-pull     跳过 git pull（用于已手动拉好代码、仅想走后续升级流程的场景）
#   --anchor      升级前生成全量迁移锚点（默认生成差异快照；MAJOR 发版建议加此参数）
#
# 顺序说明：数据库迁移在 api 服务启动【之前】用一次性容器执行，确保 Alembic 先于
# 后端的 create_all 应用结构变更，避免「新增表被 create_all 抢先建好导致迁移冲突」。
set -euo pipefail

cd "$(dirname "$0")/.." # 切到仓库根目录（docker-compose.yml 所在处）

# docker 命令前缀（root 直接 docker / 非 root 用 $DOCKER），与备份族脚本统一（审计 S-5）
# shellcheck source=scripts/docker-cmd.sh
. "$(dirname "$0")/docker-cmd.sh"

DO_BACKUP=1
DO_PULL=1
DO_ANCHOR=0
for arg in "$@"; do
  case "$arg" in
  --no-backup) DO_BACKUP=0 ;;
  --no-pull) DO_PULL=0 ;;
  --anchor) DO_ANCHOR=1 ;;
  *)
    echo "未知参数：$arg"
    echo "用法： bash scripts/upgrade.sh [--no-backup] [--no-pull] [--anchor]"
    exit 2
    ;;
  esac
done

# 前置校验
[ -f .env ] || {
  echo "缺少 .env，请先按 docs/DEPLOY.md 完成首次配置"
  exit 1
}
command -v docker >/dev/null || {
  echo "未安装 docker"
  exit 1
}

# ---------- fail-open 步骤的显式告警（数据回填 / 缓存清理 / 备份：失败不阻断升级，但不得静默） ----------
# 背景（2026-09-22）：[4.6/5] 源报告回填曾静默失败——失败输出被后续步骤淹没，界面长期显示错误的
# 报告复测三态而无人察觉。此后所有 fail-open 步骤统一登记，升级末尾汇总 + 渠道通知。
# 用法：if ! <命令>; then record_warning "<步骤>" "<影响说明>" "<手动补救命令>"; fi
WARNINGS=()
WARN_COUNT=0
record_warning() {
  WARN_COUNT=$((WARN_COUNT + 1))
  WARNINGS+=("$1 — $2")
  echo "！！$1 失败：$2"
  echo "   手动重跑：$3"
}

OLD_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "========== Talos 升级开始（当前版本 ${OLD_COMMIT}）=========="

# [1/5] 升级前备份（仅当 postgres 与 api 容器都在运行时）
# 备份放入后台，与 [3/5] 重建镜像并行，缩短升级总耗时（fail-open：失败不阻断升级）。
# 默认差异快照（秒级）；--anchor 则生成全量迁移锚点（MAJOR 发版用）。
BACKUP_PID=""
if [ "${DO_BACKUP}" -eq 1 ]; then
  if [ -n "$($DOCKER compose ps -q postgres 2>/dev/null)" ] \
    && [ -n "$($DOCKER compose ps -q api 2>/dev/null)" ]; then
    sudo mkdir -p backups
    if [ "${DO_ANCHOR}" -eq 1 ]; then
      echo "[1/5] 升级前生成迁移锚点（后台，与镜像重建并行）"
      sudo bash scripts/backup.sh >backups/upgrade-backup.log 2>&1 &
    else
      echo "[1/5] 升级前生成差异快照（后台，与镜像重建并行）"
      sudo bash scripts/backup-incremental.sh >backups/upgrade-backup.log 2>&1 &
    fi
    BACKUP_PID=$!
  else
    echo "[1/5] postgres 或 api 容器未运行，跳过升级前备份（首次部署无需备份）"
    echo "     如需强制备份，请先执行: $DOCKER compose up -d 再重试"
  fi
else
  echo "[1/5] 按参数跳过备份"
fi

# [2/5] 拉取最新代码
if [ "${DO_PULL}" -eq 1 ]; then
  echo "[2/5] 拉取最新代码 git pull --ff-only"
  git pull --ff-only
else
  echo "[2/5] 按参数跳过 git pull"
fi
NEW_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

if [ "${OLD_COMMIT}" = "${NEW_COMMIT}" ] && [ "${DO_PULL}" -eq 1 ]; then
  echo "代码已是最新（${NEW_COMMIT}），仍将继续重建与迁移以确保一致。"
fi

# [3/5] 重建镜像
echo "[3/5] 重建镜像 docker compose build"
$DOCKER compose build

# [3.5/5] 清理过期构建缓存：BuildKit 构建缓存只增不减会撑爆磁盘（判据见 DEPLOY.md 附「文件与磁盘」）。
# 保留最近 7 天（168h）缓存，兼顾构建加速与磁盘占用；清理失败不阻断升级。
echo "[3.5/5] 清理过期构建缓存（保留最近 7 天）"
if ! $DOCKER builder prune --filter "until=168h" -f; then
  record_warning "清理过期构建缓存" "构建缓存继续占用磁盘（不影响服务运行）" \
    "$DOCKER builder prune -af"
fi

# [3.6/5] 回收升级前备份 job（fail-open：失败告警但不阻断升级，因有每日差异快照兜底）
if [ -n "${BACKUP_PID}" ]; then
  echo "[3.6/5] 等待升级前备份完成"
  if wait "${BACKUP_PID}"; then
    echo "升级前备份完成"
  else
    record_warning "升级前备份" "本次升级没有可用的升级前备份（每日差异快照仍可兜底）" \
      "sudo bash scripts/backup.sh  # 并检查 backups/upgrade-backup.log"
  fi
fi

# [4/5] 先迁移数据库结构（api 服务尚未启动，Alembic 先行）
echo "[4/5] 数据库结构迁移"
sudo bash scripts/migrate.sh

# [4.5/5] 存量复测聚合标题回填（新格式「复测记录yymmdd」；仅重建旧编号标题的漏洞，幂等）
echo "[4.5/5] 复测聚合标题回填"
if ! $DOCKER compose run --rm api python -m scripts.backfill_retest; then
  record_warning "复测聚合标题回填" "历史「复测记录 N」标题未重建，漏洞详情中的复测记录不按日期格式聚合" \
    "$DOCKER compose run --rm api python -m scripts.backfill_retest"
fi

# [4.6/5] 存量复测轮次回填「源报告」（报告维度复测三态的唯一权威判据；口径见脚本 docstring，幂等）
echo "[4.6/5] 复测轮次源报告回填"
if ! $DOCKER compose run --rm api python -m scripts.backfill_retest_src_report; then
  echo "   先诊断（只统计不落库）：$DOCKER compose run --rm api python -m scripts.backfill_retest_src_report --dry-run"
  record_warning "复测轮次源报告回填" "报告维度复测三态可能显示为「未发起复测」（读取侧覆盖代偿仍可兜底）" \
    "$DOCKER compose run --rm api python -m scripts.backfill_retest_src_report"
fi

# [5/5] 拉起 / 刷新全部服务
echo "[5/5] 启动全部服务 docker compose up -d"
$DOCKER compose up -d

echo "========== 升级完成：${OLD_COMMIT} -> ${NEW_COMMIT} =========="
$DOCKER compose ps
echo "当前数据库迁移版本："
$DOCKER compose exec -T api python -m alembic current 2>/dev/null || echo "（无法读取，可稍后用 docker compose exec api python -m alembic current 查看）"
echo
echo "如需回滚代码： git checkout ${OLD_COMMIT} && docker compose up -d --build"
echo "（数据库回滚请用升级前备份 scripts/restore.sh，见 docs/DEPLOY.md）"

# fail-open 步骤汇总：放在最后打印，保证「有步骤失败」不会被中间输出淹没（2026-09-22 事故整改）
if [ "${WARN_COUNT}" -gt 0 ]; then
  echo
  echo "========== 注意：升级完成，但有 ${WARN_COUNT} 项维护步骤失败（均不阻断升级，请尽快处理） =========="
  for warning in ${WARNINGS[@]+"${WARNINGS[@]}"}; do
    echo "  - ${warning}"
  done
  echo "补救命令见上方各步骤的「手动重跑」提示。"
  sudo bash scripts/notify.sh "Talos 升级完成（${NEW_COMMIT}）：有 ${WARN_COUNT} 项维护步骤失败，请查看升级日志并手动补救" || true
fi
