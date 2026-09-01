# Talos 备份提速与容灾优化方案（方案一 + 二 + 三）

> 面向 VPS 生产环境的备份提速与磁盘优化设计稿。解决「升级备份 1.7GB storage 偏慢」与
> 「磁盘告警复发风险」两个痛点，产出「差异快照 + 迁移锚点」混合备份体系。
>
> 备份模型采用 **全量 + 差异（differential）**：日常差异快照直接基于最近一份迁移锚点，
> 新锚点生成后清空旧差异，以最新锚点重启差异链。
>
> 关联文档：`docs/DEPLOY.md`（部署/备份/迁移）、`docs/INCIDENT-20260831-disk-space.md`（磁盘告警复盘）。

---

## 0. 背景与目标

| 痛点 | 现状 | 目标 |
|---|---|---|
| 备份慢 | `backup.sh` 在 api 容器内 `tar czf` 用 gzip 单线程压缩 1.7GB 已压缩上传文件，收益近 0 且烧 CPU；db/storage 串行 | 单份备份提速 60%+，升级感知趋 0 |
| 磁盘压力 | 全量备份 + 保留 30 天，磁盘随天数线性增长（30 天 ≈ 54GB）；BuildKit 缓存曾撑爆磁盘 | 磁盘随「变化量」增长，稳态 ≤ 8GB |
| 迁移鲁棒 | `restore.sh` 依赖自包含全量备份，跨机零依赖（好，需保留） | 保留自包含「迁移锚点」兜底 |

**三条设计原则**：

1. **快**——方案一（多线程压缩 + 并行）做底座，所有备份路径复用。
2. **省**——方案二（差异快照 + 迁移锚点）做日常，磁盘只随变化量增长，回溯窗口 = 当前锚点周期。
3. **感知不到**——方案三（升级异步编排）让备份与 `docker compose build` 重叠。

---

## 1. 总体架构与三者职责边界

```
                    ┌─────────────────────────────────────────────┐
                    │           脚本层（scripts/）                 │
                    │                                             │
   cron 每日 ──────►│  backup-incremental.sh  方案二：差异快照     │
   cron 每月1日 ───►│  backup.sh              方案二：迁移锚点     │
   MAJOR 发版 ─────►│  backup.sh              方案二：迁移锚点     │
   upgrade.sh ─────►│  upgrade.sh（异步）      方案三：升级编排     │
                    │       │                                     │
                    │       └──► 复用 方案一 底座：                │
                    │           zstd 多线程 + db/storage 并行      │
                    └─────────────────────────────────────────────┘
```

| 层 | 脚本 | 职责 | 产物 | 触发 |
|---|---|---|---|---|
| 方案一（压缩加速底座） | `backup-common.sh` | zstd 多线程、并行、锁、校验、告警公共函数 | — | 被复用 |
| 方案二（差异快照） | `backup-incremental.sh` | 基于最近锚点的差异备份 | `backups/snapshots/...` | cron 每日 / upgrade 前 |
| 方案二（迁移锚点） | `backup.sh`（改造） | 自包含全量备份 | `backups/anchors/...` | cron 每月 1 日 / MAJOR 发版 / 手动 |
| 方案三（异步编排） | `upgrade.sh`（改造） | 升级前备份与 build 并行 | 见上 | 升级时 |

**职责边界（关键）**：

- 方案一只管「让单份更快更小」，不涉及「存几份、存多久」——那是方案二的事。
- 方案二只管「日常高频差异快照」，**不承担跨机迁移**——迁移由锚点 + `restore.sh` 负责。
- 方案三只改 `upgrade.sh` 编排，不改备份内容与格式。

---

## 2. 方案一：压缩加速底座

**改动**（`scripts/backup.sh`、`scripts/restore.sh`）：

1. 压缩从容器内移到宿主机：容器内只做归档 `tar cf -`（IO 快），宿主机 `zstd -T0` 多线程压缩。
2. db 与 storage 两步并行（`&` + `wait`）。

```bash
# db：pg_dump → zstd
sudo docker compose exec -T postgres sh -c 'pg_dump --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | zstd -T0 -6 > db.sql.zst &

# storage：容器内只归档，宿主机 zstd 压缩
sudo docker compose exec -T api sh -c 'tar cf - -C /app/storage .' | zstd -T0 -3 > storage.tar.zst &

wait
```

- storage 用 `-3`（快速档，已压缩文件无收益，只求快）；db 用 `-6`（文本 SQL 收益大）。
- `restore.sh` 对应改用 `zstd -dc` 解压。

**依赖**：宿主机 `apt install zstd`（一条命令）。镜像内无需装（压缩在宿主机）。

---

## 3. 方案三：升级编排异步层

**改动**（`scripts/upgrade.sh`）：

1. 升级前备份放入后台 `&`，记录 PID；主流程立即执行 `docker compose build`。
2. build 完成后 `wait $PID` 并检查退出码，按策略处理（默认 **fail-open**：失败告警但不阻断升级，因有每日差异快照兜底）。
3. 分级：升级前默认只做**差异快照**（快，秒级）；`--anchor` 参数可强制触发全量锚点（MAJOR 发版用）。

```bash
# [1/5] 升级前备份（后台，与 build 并行）
if [ "$DO_ANCHOR" -eq 1 ]; then
  bash scripts/backup.sh >backups/upgrade-backup.log 2>&1 &
else
  bash scripts/backup-incremental.sh >backups/upgrade-backup.log 2>&1 &
fi
BACKUP_PID=$!

# [2/5] git pull ...（快速，串行）
# [3/5] build（耗时，与备份重叠）
sudo docker compose build

# build 后回收备份 job
wait "$BACKUP_PID" || bash scripts/notify.sh "升级备份失败（已降级为每日差异快照兜底）"
```

**依赖**：方案二的 `backup-incremental.sh` 已就绪；`notify.sh` 告警通道已配置。

---

## 4. 方案二：差异快照 + 迁移锚点（核心设计稿）

### 4.1 触发机制

| 触发源 | 动作 | 频率 |
|---|---|---|
| cron 定时 | `backup-incremental.sh`（差异快照） | 每日 02:00 |
| cron 定时 | `backup.sh`（迁移锚点，全量） | 每月 1 日 03:00 |
| 发布事件 | `backup.sh`（迁移锚点） | MAJOR 发版时（升级前） |
| 升级事件 | `upgrade.sh` 后台触发差异快照（方案三） | 每次升级 |
| 手动 | 两个脚本均可手动执行 | 按需 |

**互斥与幂等**：所有备份脚本入口 `flock -n` 加锁，同一时刻只允许一份备份运行，冲突则退出并告警；脚本可安全重跑。

### 4.2 数据去重与版本管理策略（全量 + 差异模型）

**模型**：每次迁移锚点是「全量」；锚点之后每天的差异快照都**直接基于该锚点**做硬链接去重，快照之间相互独立、不依赖前一天。

**去重机制（rsync 硬链接，文件级）**：

```bash
# 差异快照：以「锚点基线」为 --link-dest 基准，未变文件硬链接复用
rsync -a --delete --link-dest=../baseline/storage /app/storage/ "$NEW/snapshot/storage/"
```

- storage 上传文件（PDF/docx/图片）是**追加型、写后不改**的数据，文件级去重已覆盖绝大多数场景。
- 硬链接复用 = 不重读、不重写、不占额外磁盘。

**基线物化（关键）**：锚点是 `storage.tar.zst` 单文件，无法直接当硬链接源。锚点生成后需**解包一份 `backups/baseline/storage/` 常驻目录**作为差异基线（约 1.7GB，是硬链接差异的必要代价）。

**db 的特殊处理**：`pg_dump` 每次产物都不同，硬链接无法复用 → db 每次**全量 dump**（数据量小，秒级），用 zstd 压缩；份数随快照/锚点自然裁剪。

**版本管理（锚点 + 周期内差异）**：

| 层 | 粒度 | 保留 | 说明 |
|---|---|---|---|
| 锚点（全量） | 每月 1 日 + MAJOR 发版 | 最近 3 份 | 跨机迁移 + 差异基线源 |
| 差异快照 | 每日（基于最近锚点） | 当前锚点周期内全保留 | 周期内任意天可回滚 |

**清空增量的时机（先建新、再拆旧）**：新锚点生成后，按以下顺序执行，**全部校验通过才清空旧数据**：

1. 生成新锚点 `anchors/<ts>/storage.tar.zst`；
2. 解包出新基线 `backups/baseline/storage/`；
3. 生成首份差异快照并校验 SHA256 通过；
4. **此时才**清空旧 `snapshots/*`，并裁剪旧锚点（保留最近 3 份）。

> 顺序不可颠倒：若新锚点解包/校验失败，旧差异仍在，可兜底。

**磁盘估算**（storage 1.7GB 追加型、日均变化量 ~1%）：

- 锚点：3 份 × ~1.6GB ≈ **4.8GB**；
- 差异基线（解包）：~1.7GB（与最新锚点内容重复，硬链接差异的必要代价）；
- 周期内差异变化量：~0.5GB；
- 合计稳态 **≤ 8GB**（对比原方案 30 天全量 ≈ 54GB）。

**回溯窗口权衡**：回溯窗口 = 当前锚点周期（约 1 个月）。锚点之间的「中间状态」会随清空丢失。若未来需要更长回溯，可调高锚点保留份数或提高锚点触发频率（磁盘相应增加）。

> 进阶可选：若未来出现「大文件整体重写」导致硬链接失效，可切换到 `borg`/`restic`（块级去重）。
> 注意 borg 对 db 必须直接备份**未压缩 SQL 文本**（让 borg 自己压缩），否则先 gzip 会导致块去重失效。

### 4.3 存储结构与命名规范

```
backups/
  anchors/                        # 迁移锚点（自包含全量，跨机零依赖）
    2026/09/
      20260901_030001/
        db.sql.zst
        storage.tar.zst           # 单文件 tar 归档（迁移用）
        SHA256SUMS
        MANIFEST.json
  baseline/                       # 当前锚点周期的差异基线（常驻，硬链接源）
    storage/                      # 解包自最新锚点 storage.tar.zst
    MANIFEST.json                 # 记录来源锚点时间戳
  snapshots/                      # 差异快照（基于 baseline，硬链接复用）
    2026/09/
      20260901_020001/            # 命名：YYYYMMDD_HHMMSS（字符串排序=时间排序）
        storage/                  # 硬链接目录（未变文件 hardlink 到 baseline）
        db.sql.zst                # 每次全量 dump
        SHA256SUMS
        MANIFEST.json
  latest -> snapshots/2026/09/20260901_020001   # 软链指向最新快照
```

**命名规范**：

- 目录名统一 `YYYYMMDD_HHMMSS`（UTC+8），类型前缀用目录层级区分（`snapshots/` / `anchors/` / `baseline/`）。
- 快照用 `storage/`（硬链接目录，可浏览）；锚点用 `storage.tar.zst`（单文件，便于整份拷贝）。
- 快照先写临时目录 `snapshots/.tmp-<ts>`，成功后原子 `mv` 为正式名并更新 `latest` 软链——**保证 `latest` 永远指向完整快照**。

**MANIFEST.json 结构**：

```json
{
  "type": "snapshot" | "anchor",
  "created_at": "2026-09-01T02:00:01+08:00",
  "git_commit": "446f5da",
  "db_size_bytes": 123456789,
  "storage_size_bytes": 1789569706,
  "storage_files": 12345,
  "checksum_alg": "sha256",
  "status": "complete",
  "completed_at": "2026-09-01T02:02:30+08:00"
}
```

### 4.4 断点续传与完整性校验

**完整性校验**：

- 每份备份生成 `SHA256SUMS`（对 `db.sql.zst`、`storage.tar.zst` 或 storage 目录内所有文件）；
- MANIFEST 记录 `status: complete` 作为**完成标记**——恢复时校验 `status`，拒绝半成品；
- 差异快照对 storage 目录可用 `rsync -c`（按校验和比对）做二次校验，可选开启。

**断点续传**：

- **差异快照**：天然「重跑即续」——失败后下次执行 `rsync --link-dest` 自动补齐差异，已复用硬链接不重传；
- **迁移锚点**：`zstd` 流式输出到临时文件，失败则丢弃重跑；`pg_dump` 无断点能力，但 db 小、重试代价低；
- **远程同步**（如异地备份，可选）：`rsync --partial --append-verify` 支持断点续传；
- **borg 路线**（可选）：`borg check` 分块校验 + 天然断点续传。

### 4.5 迁移锚点定义与生成规则

**定义**：自包含、可跨机独立恢复的**全量**备份——不依赖硬链接结构、不依赖差异链、不依赖任何非系统工具（`zstd` 除外，目标机需 `apt install zstd`）。

**生成规则**：

| 触发 | 条件 | 备注 |
|---|---|---|
| 定时 | 每月 1 日 03:00 | 常规锚点 |
| 发布 | MAJOR 发版时（升级前） | 破坏性变更前必做 |
| 手动 | 迁移/变更前；MINOR 涉及 DB 迁移时 | `bash scripts/backup.sh` |

**保留**：锚点保留最近 **3 份**（共池 FIFO 淘汰）。删除旧锚点前**先校验存在更新的完整锚点**（读 MANIFEST `status`）；删除旧锚点时同步触发 §4.2 的「清空增量 + 重建基线」流程。

**产物即现有 `backup.sh` 产物 + zstd 加速**，语义不变（`restore.sh` 兼容），迁移流程见 `docs/DEPLOY.md`「六、更换 VPS」。

### 4.6 锚点回滚与恢复流程

**同机回滚**（升级失败回退数据）：

```bash
# 1. 回退代码
git checkout <OLD_COMMIT>
# 2. 停写
docker compose stop api worker
# 3. 用锚点恢复（restore.sh 会清空重建 db + 解包 storage）
bash scripts/restore.sh backups/anchors/2026/09/20260901_030001
# 4. 起服 + 补迁移
docker compose up -d
bash scripts/migrate.sh
```

**周期内任意天回滚**（差异快照）：

```bash
# 还原 = 最近锚点 + 当天差异（一层，快）
docker compose stop api worker
bash scripts/restore.sh backups/snapshots/2026/09/20260915_020001
docker compose up -d && bash scripts/migrate.sh
```

**跨机迁移**（与 `docs/DEPLOY.md`「六」一致，只拷锚点）：

1. 旧机：`docker compose stop api worker` → `bash scripts/backup.sh` 生成锚点；
2. 拷贝到新机：仓库代码、`.env`、`backups/anchors/...` 整目录（**不拷 snapshots/**）；
3. 新机：`bash scripts/restore.sh backups/anchors/...`；
4. **恢复后先 `bash scripts/migrate.sh` 再访问**（见 `DEPLOY.md`「七、恢复后页面 500 排查」）。

**恢复演练**：每季度做一次「锚点 → 新目录 → restore → 数据抽查」演练，验证锚点可用与流程时效（目标 ≤ 15 分钟）。

### 4.7 失败重试与告警机制

**失败重试**：

- 脚本内：db dump / storage 打包失败 → 自动重试 3 次（间隔 10s/30s/60s）；
- 定时任务：cron 失败 → 下次 cron 自然重跑（差异快照幂等）；
- 差异快照失败**不阻断**后续快照（`--link-dest` 指向 `baseline/`，而非「最近一次尝试」）。

**告警**（新增 `scripts/notify.sh`，用 webhook 推送，复用项目已有的 webhook 通知通道配置）：

| 告警项 | 触发 | 通道 |
|---|---|---|
| 备份失败（重试后仍失败） | 退出码非 0 | webhook |
| 磁盘使用率超阈值（默认 80%） | `df` 检查 | webhook |
| 24h 无新快照 | 检查 `latest/MANIFEST.json` 时间戳 | webhook |
| 恢复/演练失败 | restore 退出码非 0 | webhook |

```bash
# notify.sh 示例：读取 .env 的 BACKUP_WEBHOOK_URL，POST 文本
curl -fsS -X POST "$BACKUP_WEBHOOK_URL" -H 'Content-Type: application/json' \
  -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"[Talos备份] $1\"}}" || true
```

---

## 5. 三者协同流程

### 5.1 升级流程（方案三 + 一 + 二）

```
upgrade.sh
 ├─ 校验容器在运行
 ├─ 后台触发备份（默认差异快照 / --anchor 则锚点）        ─┐ 并行
 ├─ git pull --ff-only                                     │
 ├─ docker compose build（方案三：与备份重叠）              │
 ├─ wait 备份 job ─ 失败则 notify（fail-open）              │
 ├─ builder prune（缓存清理，已有）                         │
 ├─ migrate.sh（Alembic 迁移）                             │
 └─ compose up -d
```

### 5.2 日常流程（方案二 + 一）

```
cron 02:00  backup-incremental.sh
  ├─ flock 互斥
  ├─ 方案一底座：db dump(zstd) 与 storage rsync 并行
  ├─ rsync --link-dest=baseline/storage 硬链接差异
  ├─ 原子 mv + 更新 latest
  ├─ SHA256 校验 + MANIFEST 完成标记
  └─ 失败则 notify

cron 03:00（每月 1 日）backup.sh
  ├─ 生成锚点 anchors/<ts>/（zstd 全量）
  ├─ 解包出新 baseline/storage/
  ├─ 生成首份差异并校验
  ├─ 校验通过 → 清空旧 snapshots/* + 裁剪旧锚点（留 3 份）
  └─ 失败则 notify（保留旧数据兜底）
```

---

## 6. 分阶段实施计划

### 阶段 0：准备与验证（依赖基线）

| 项 | 内容 |
|---|---|
| 依赖 | `apt install zstd rsync`；确认 `rsync`、`flock` 存在 |
| 前置 | 备份目录结构从 `backups/<时间戳>` 平铺迁移到 `snapshots/`/`anchors/` 分层（存量目录做一次性归档或保留兼容读取） |
| 风险 | 存量 `backups/<时间戳>` 被新结构遗漏 → **应对**：保留旧目录只读，`restore.sh` 兼容旧平铺路径 |

### 阶段 1：方案一落地（低风险，先做）

| 步骤 | 内容 |
|---|---|
| 1 | `backup.sh` 改 zstd + 并行；`restore.sh` 改 `zstd -dc` |
| 2 | 本地/测试机 `time bash scripts/backup.sh` 实测提速幅度 |
| 3 | 全量走一遍 restore 验证产物可恢复 |
| 依赖 | 阶段 0 |
| 风险 | zstd 未装 / 解压命令不匹配 → **应对**：脚本开头 `command -v zstd` 前置校验，缺失则告警并回退 gzip |
| 风险 | 并行写同一目录竞态 → **应对**：db 与 storage 写到不同临时文件再原子 mv |

### 阶段 2：方案三落地（依赖方案二，可先以「锚点」形态过渡）

| 步骤 | 内容 |
|---|---|
| 1 | `upgrade.sh` 备份后台化 + `wait` + fail-open + `--anchor` 参数 |
| 2 | 加 `notify.sh` 告警 |
| 依赖 | 阶段 1；`notify.sh` 与 webhook 通道 |
| 风险 | 备份与 build 争抢 CPU/磁盘拖慢 build → **应对**：`nice`/`ionice` 降低备份优先级 |
| 风险 | fail-open 下备份失败被忽视 → **应对**：有每日差异快照兜底 + 失败必告警 |

### 阶段 3：方案二落地（核心）

| 步骤 | 内容 |
|---|---|
| 1 | 新增 `backup-common.sh`（锁/校验/告警/公共函数） |
| 2 | 新增 `backup-incremental.sh`（rsync 硬链接差异 + baseline + MANIFEST + SHA256） |
| 3 | 改造 `backup.sh` 为「迁移锚点生成器」（输出 `anchors/` + 解包 `baseline/` + 触发清空/裁剪） |
| 4 | 接入 cron（每日差异 + 每月 1 日锚点） |
| 依赖 | 阶段 1；cron 配置；`.env` 增 `BACKUP_WEBHOOK_URL` |
| 风险 | 硬链接被普通复制展开导致磁盘爆炸 → **应对**：文档明确「跨机迁移只拷 anchors/，不拷 snapshots/」 |
| 风险 | 清空增量时机错误导致裸奔 → **应对**：严格「先建新锚点+基线+校验，再清旧」，删除顺序写进脚本并有校验闸门 |
| 风险 | baseline 与锚点内容不一致（解包中途失败）→ **应对**：解包后对 baseline 做 SHA256 与锚点 MANIFEST 比对 |
| 风险 | 3 份锚点被 MAJOR 频繁挤占、丢失月初锚点 → **应对**：共池 FIFO 可接受（迁移用最新），如介意可放宽到 4 份 |

### 阶段 4：恢复演练与监控收口

| 步骤 | 内容 |
|---|---|
| 1 | 季度恢复演练脚本 + 文档化 |
| 2 | 磁盘/快照时效监控接入 notify |
| 3 | 更新 `docs/DEPLOY.md` 备份/迁移章节，指向本方案 |

---

## 7. 脚本与文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `scripts/backup-common.sh` | 新增 | 公共函数：锁、zstd 封装、SHA256、MANIFEST、notify |
| `scripts/backup-incremental.sh` | 新增 | 差异快照（方案二日常，基于 baseline） |
| `scripts/backup.sh` | 改造 | 迁移锚点生成器（方案一底座 + 输出 `anchors/` + 解包 `baseline/` + 清空/裁剪） |
| `scripts/restore.sh` | 改造 | 支持 zstd 解压 + 兼容旧平铺路径 + 恢复后提示 migrate |
| `scripts/upgrade.sh` | 改造 | 方案三异步编排 + `--anchor` 参数 |
| `scripts/notify.sh` | 新增 | webhook 告警 |
| `cron` 配置 | 新增 | 每日差异快照 + 每月 1 日锚点 |
| `docs/BACKUP_OPTIMIZATION.md` | 新增 | 本文档 |
| `docs/DEPLOY.md` | 更新 | 备份/迁移章节引用 |

---

## 8. 验收标准

- [ ] 单份全量备份耗时下降 ≥ 60%（`time` 实测对比）。
- [ ] 升级流程中备份阶段感知耗时趋 0（备份与 build 重叠，`time bash scripts/upgrade.sh` 对比）。
- [ ] 备份稳态磁盘 ≤ 8GB（含 3 份锚点 + baseline + 周期差异）。
- [ ] 新锚点生成后旧差异被清空、旧锚点裁剪到 3 份，且清空前已完成新锚点 + 基线校验。
- [ ] `restore.sh` 能从锚点在新机器完成恢复，恢复后 `migrate.sh` 通过、页面无 500。
- [ ] 周期内任意天差异快照可独立回滚（锚点 + 当天差异）。
- [ ] 备份失败 / 磁盘超阈值能触发 webhook 告警。
- [ ] 季度恢复演练 ≤ 15 分钟完成。
