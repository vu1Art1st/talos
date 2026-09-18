#!/usr/bin/env bash
# Talos docker 命令前缀（被 backup-common.sh / migrate.sh / upgrade.sh 等 source）。
# 规则：root 直接 `docker`，非 root 用 `sudo docker`；调用方已显式设置 $DOCKER 时尊重其取值。
# 注意：只定义变量，不执行其它顶层逻辑（可安全多次 source）。
# 背景：此前只有备份族脚本自适应，migrate.sh / upgrade.sh 硬编码 `sudo docker`（审计 S-5）。
if [ -z "${DOCKER:-}" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    DOCKER="docker"
  else
    DOCKER="sudo docker"
  fi
fi
export DOCKER
