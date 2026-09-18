#!/usr/bin/env bash
# Talos 生产数据库结构迁移：在 api 容器内以 Alembic 为准演进 PostgreSQL 表结构（幂等）。
# 每次发布后在仓库根目录执行： bash scripts/migrate.sh
# 逻辑见 backend/scripts/migrate.py 与 docs/DEPLOY.md「三、版本升级」。
set -euo pipefail

cd "$(dirname "$0")/.." # 切到仓库根目录（docker-compose.yml 所在处）

# docker 命令前缀（root 直接 docker / 非 root 用 sudo docker），与备份族脚本统一（审计 S-5）
# shellcheck source=scripts/docker-cmd.sh
. "$(dirname "$0")/docker-cmd.sh"

# run --rm 起一个临时 api 容器执行迁移命令，复用其环境变量与依赖，完事即删
$DOCKER compose run --rm api python -m scripts.migrate
