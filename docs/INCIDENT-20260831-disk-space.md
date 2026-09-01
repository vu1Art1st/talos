# VPS 磁盘空间告警排查复盘

| 项目 | 内容 |
|---|---|
| 文档类型 | 运维事故复盘（Incident Postmortem） |
| 发生时间 | 2026-08-31 |
| 影响范围 | VPS（Ubuntu 22.04，1Panel 管理，Docker Compose 部署 Talos） |
| 严重程度 | 中（磁盘可用空间降至 22%~28%，存在写满宕机风险） |
| 结论 | 根因是 Docker BuildKit 构建缓存无限累积（12.95GB，可回收 12.47GB） |

---

## 一、问题现象

- 用户报告：VPS 磁盘仅剩余约 **22%** 空间，担心磁盘写满导致服务异常。
- 实测 `df -h`：系统盘 `/dev/vda2` 共 50G，已用 34~35G（约 **72%~73%**），可用 13~14G。
- 同期还观察到两个伴生现象：
  1. 最新一份备份 `storage.tar.gz` 达 1.7G，而几天前历史备份仅 ~120M，上传文件卷出现 8 倍增长；
  2. `du` 统计根目录 39G 与 `df` 的 34G 相差约 5G（后证实为 containerd 快照硬链接被 `du` 重复统计，非真实多占）。

---

## 二、排查步骤与时间线（2026-08-31）

| 时间 | 步骤 | 关键输出 |
|---|---|---|
| 上午 | 分析历史备份目录 | 18 份备份共约 3.8G，其中 08-13 一天 5 份、08-23 两份仅差 2 分钟、08-25 一天 3 份，冗余明显 |
| 上午 | 编写运维脚本 | 新增 `scripts/disk-usage.sh`（磁盘占用分析）、`scripts/swap-manager.sh`（4GB swap 开关） |
| 07:52 | 执行 `disk-usage.sh -d /` | 顶层占用：`/var` 19G、`/home` 6.6G、`/usr` 4.1G、`/swapfile` 4.1G、`/boot` 135M |
| 08:02 | 执行 `disk-usage.sh -d /var/lib/docker` | `/var/lib/docker` 仅 4.4G（volumes 1.8G + buildkit 46M），与 `/var` 19G 差距大，指向 `/var/lib/containerd` |
| 08:23 | 执行 `disk-usage.sh -d /var` | `/var/lib` 18G、`/var/log` 1.3G、`/var/cache` 150M；大文件碎片集中在 `/var/lib/containerd`（chromium 295M、libLLVM 171M、多个 sha256 blob） |
| 08:27 | 执行 `docker system df` | **Build Cache 12.95GB，可回收 12.47GB，活跃 0%** ← 定位根因 |
| 08:27 | 分析存储卷 | `/app/storage/uploads` 1.4G、`/app/storage/exports` 402M、`previews` 4K |

> 关键转折点：`du` 只能把 12.95G 的构建缓存拆成一个个 100~300M 的碎片文件（藏在 `/var/lib/containerd` 内容库里），无法归因；而 `docker system df` 的 **Build Cache / RECLAIMABLE** 一栏直接给出了答案。

---

## 三、根本原因分析

**直接原因**：Docker BuildKit **构建缓存**无限累积，达到 **12.95GB**（占 50G 系统盘约 26%），其中 **12.47GB 可回收且活跃度为 0**。

触发机制：

- 每次执行 `scripts/upgrade.sh` 升级都会走 `docker compose build`，BuildKit 会为每一层保留构建缓存；
- 项目内没有任何「构建缓存清理」环节，缓存只增不减；
- 升级较为频繁（结合版本发布记录），缓存快速膨胀到 12.95G。

**次要/伴生因素**（合计约 4~5G）：

| 因素 | 占用 | 性质 |
|---|---|---|
| 冗余备份 | ~1.1G（10 份同日/近时重复） | 无自动保留策略 |
| `/var/log` 日志 | 1.3G | 无大小上限 |
| snapd 缓存 | 232M | 未清理 |
| Homebrew 缓存 + linuxbrew | ~0.3~1G | 含 gcc-16.1.0 bottle |
| `/app/storage/uploads` | 1.4G | 业务数据（正常增长，需关注） |
| `/app/storage/exports` | 402M | 导出产物（可清理） |

**非问题项**：`/swapfile` 4.1G（本次按需求主动创建，属有意占用）；containerd 镜像 3.4G（全部在运行容器使用，不可删）；docker volumes 1.9G（业务数据库与上传卷，不可删）。

---

## 四、修复措施

| 序号 | 措施 | 命令 | 回收量 |
|---|---|---|---|
| 1 | 清理冗余备份 | 删除 10 份同日/近时重复备份，保留 8 份 | +1.1G |
| 2 | **清理构建缓存（核心）** | `sudo docker builder prune -af` | **+12.47G** |
| 3 | 日志瘦身 | `sudo journalctl --vacuum-size=300M` | +~1G |
| 4 | 清理 snap 缓存 | `sudo snap set system refresh.retain=2` | +~230M |
| 5 | （可选）清理 Homebrew 缓存 | `brew cleanup --prune=all && rm -rf ~/.cache/Homebrew/downloads/*` | +~0.3~1G |
| 6 | （可选）删除 1panel 旧安装包 | `rm -rf /home/ubuntu/1panel-v1.10.34-lts-linux-amd64` | +~120M |

> `docker builder prune -af` 安全性的依据：`docker system df` 显示 Build Cache 的 ACTIVE=0（无正在进行的构建任务），因此这 12.47G 可全部安全回收，不影响运行中的容器与镜像。

---

## 五、验证结果

- 预期效果：磁盘从 **35G / 50G（73%）** 降至约 **21.5G / 50G（~43%）**，腾出约 13.5G。
- 待确认项：执行 `docker builder prune -af` 后，用 `df -h /` 与 `docker system df` 复验最终占用与 Build Cache 回收量（本文档定稿时用户尚未回报最终 `df` 结果）。

---

## 六、预防同类问题的建议

1. **升级流程内置构建缓存清理**：在 `scripts/upgrade.sh` 的 `docker compose build` 之后追加 `sudo docker builder prune -f`，每次升级即回收，杜绝累积。
2. **备份自动保留策略**：在 `scripts/backup.sh` 末尾增加「只保留最近 N 份 / 每日去重」逻辑（或 cron 定时清理），避免同一天多份堆积。
3. **磁盘监控告警**：设置磁盘使用率阈值告警（如 1Panel 告警或 `cron + df` 脚本，超过 80% 通知），在写满前预警。
4. **日志轮转与大小上限**：配置 journald `SystemMaxUse`（如 300M）与 `docker` json 日志轮转，避免 `/var/log` 膨胀。
5. **定期维护 cron**：建议每月跑一次「构建缓存 + snap 缓存 + apt 缓存 + Homebrew 缓存」清理。
6. **导出产物清理**：对 `/app/storage/exports` 建立「超过 N 天自动清理」策略（这些是临时生成的报告导出文件）。
7. **沉淀排查工具**：本仓库已新增 `scripts/disk-usage.sh`，可直接复用；排查此类问题时，务必结合 `du`（定位目录）与 `docker system df`（定位 Docker 内部占用，含构建缓存）双视角，避免只看 `du` 漏掉内容库中的碎片缓存。
