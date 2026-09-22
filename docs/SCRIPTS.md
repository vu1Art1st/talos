# Talos 脚本清单与运维手册

> 建立日期：2026-09-17 · 依据：对仓库内 22 个脚本（11 个 shell + 11 个 Python）的实际读取，以及全仓库引用关系检索。
> 配套文档：部署、备份与排障流程见 [`DEPLOY.md`](./DEPLOY.md)（§五 备份、附「文件与磁盘」）；发布史见 [`RELEASE.md`](./RELEASE.md)；规范与门禁见仓库根 `AGENTS.md`。
>
> **本文档是脚本用途/调用/依赖/场景的唯一登记处**：新增脚本必须在此登记；脚本改参数、改路径、改调用方时必须同步本文档。

## 〇、状态判定口径

| 状态 | 含义 | 判定依据 |
|---|---|---|
| **活跃·发布流程** | 每次发布/升级自动被调用 | 被 `scripts/upgrade.sh`、`scripts/migrate.sh` 等编排调用 |
| **活跃·常规运维** | 人工按场景执行，长期有效 | 文档中有明确章节 + 有引用方（cron、其他脚本、文档） |
| **活跃·开发辅助** | 仅开发环境使用 | 文档或脚本头部注明开发用途 |
| **一次性** | 针对某一历史版本数据的纠偏/回填，执行完即无需再跑 | 无自动调用方；头部写「存量…」；RELEASE/DEPLOY 有版本号锚点 |
| **已失效** | 运行时必然报错，不可用 | 实测运行/导入失败 |

---

## 一、总览

### 1.1 部署与开发/测试脚本 `scripts/`（12 个部署脚本 + `test` / `clean` / `e2e` 三个辅助脚本的 sh+ps1 双份，合计 1 664 行）

| 脚本 | 行数 | 状态 | 调用方 / 出处 |
|---|---|---|---|
| `upgrade.sh` | 126 | 活跃·发布流程 | README.md:85 / DEPLOY.md:81,336,377 |
| `migrate.sh` | 14 | 活跃·发布流程 | `upgrade.sh:105`、`restore.sh:77`、DEPLOY.md:90,118,320 |
| `backup.sh` | 98 | 活跃·常规运维 | `install-cron.sh:13`、`upgrade.sh:55`、DEPLOY.md:227,249 |
| `backup-incremental.sh` | 74 | 活跃·常规运维 | `install-cron.sh:12`、`upgrade.sh:58` |
| `backup-common.sh` | 85 | 活跃·库文件 | 被 `backup.sh`/`backup-incremental.sh`/`restore.sh` source |
| `docker-cmd.sh` | 13 | 活跃·库文件（2026-09-17 新增） | 被 `backup-common.sh`、`migrate.sh`、`upgrade.sh` source（S-5：`$DOCKER` 前缀统一实现） |
| `restore.sh` | 77 | 活跃·常规运维 | README.md:85、DEPLOY.md:258 |
| `notify.sh` | 27 | 活跃·库依赖 | `backup-common.sh:45-49`、`upgrade.sh:99` |
| `install-cron.sh` | 27 | 活跃·一次性安装 | RELEASE.md:385 |
| `disk-usage.sh` | 127 | 活跃·排障工具 | DEPLOY.md 附「文件与磁盘」（磁盘排查双视角判据） |
| `swap-manager.sh` | 199 | 活跃·排障工具 | RELEASE.md:434 |
| `setup-docker-mirror.sh` | 59 | 活跃·部署前配置 | DEPLOY.md:198,203、RELEASE.md:964 |
| `test.sh` | 126 | 活跃·开发辅助（2026-09-21 新增） | 后端测试统一入口（WSL/Linux/macOS）：`--workers N` 并行、`--prune` 回收残留；AGENTS.md「常用命令」 |
| `test.ps1` | 105 | 活跃·开发辅助（2026-09-21 新增） | Windows 侧同上（`-Workers` / `-Prune -Yes`）；按 `.codebuddy/rules/pwsh7.md` 以 **pwsh 7** 调用、文件 UTF-8 无 BOM |
| `e2e.sh` | 133 | 活跃·开发辅助（2026-09-22 新增） | 端到端测试编排（起独立 E2E 栈 + Playwright）；详见 §2.13 |
| `e2e.ps1` | 150 | 活跃·开发辅助（2026-09-22 新增） | Windows 侧同上（`-Headed` / `-Keep` / `-PlaywrightArgs`）；详见 §2.13 |
| `clean.sh` | 104 | 活跃·开发辅助（2026-09-22 新增） | 本地垃圾清理（默认预演，`--apply` 执行）；详见 §2.14 |
| `clean.ps1` | 115 | 活跃·开发辅助（2026-09-22 新增） | Windows 侧同上（`-Apply`）；详见 §2.14 |

### 1.2 后端脚本 `backend/scripts/`（18 个，2 192 行）

> 2026-09-17 审计修复后：删除 `migrate_from_insight2.py`（已失效，见 §4.1）与 `seed_knowledge.py`（已并入 `knowledge_data.py`，见 §4.2 M-1）；新增 `_common.py`（一次性脚本公共助手，见 §4.2 M-2）。2026-09-19 新增 `backfill_retest_src_report.py`（结论优化配套回填，已写入升级流程）。

| 脚本 | 行数 | 状态 | 调用方 / 出处 |
|---|---|---|---|
| `migrate.py` | 50 | 活跃·发布流程 | `scripts/migrate.sh:10`、DEPLOY.md:121,321 |
| `backfill_retest.py` | 47 | 活跃·发布流程 | `upgrade.sh:109`（每次升级自动执行）；已改用 `_common.run`（M-2） |
| `sync_knowledge_templates.py` | 154 | 活跃·常规运维 | USER_GUIDE.md:251-257、RELEASE.md:166 |
| `seed_dev_data.py` | 582 | 活跃·开发辅助 | RELEASE.md:706 |
| `knowledge_data.py` | 42 | 活跃·共享模块 | 被 `seed_dev_data.py` 导入（模板库数据唯一加载实现） |
| `_common.py` | 86 | 活跃·共享模块（2026-09-17 新增） | 被 6 个一次性脚本导入（`bootstrap` / `dry_run_flag` / `save_backup` / `run`）；2026-09-18 修正 `save_backup` 落盘目录为 `settings.storage_sub("backups")`（延迟导入 settings） |
| `_check_imports.py` | 97 | 活跃·开发辅助（2026-09-19 新增） | 静态校验 `scripts/*.py` 对 app 模块的引用是否仍有效（`from app.x import y` 与「模块别名.属性」两类），可 `python -m scripts._check_imports` 自检；守卫 `tests/test_source_guard.py::test_scripts_app_references_resolve`。起因：`backfill_retest.py` 在批次 D 重构后导入断链，脚本不参与测试收集故 CI 未发现 |
| `fix_retest_section_dup.py` | 98 | 一次性（已写入升级步骤） | DEPLOY.md:139-172、RELEASE.md:253；已改用 `_common`（M-2） |
| `repair_report_section_order.py` | 83 | 一次性 | RELEASE.md:305；已改用 `_common`（M-2） |
| `backfill_vul_submit_time.py` | 69 | 一次性 | RELEASE.md:546；已改用 `_common.run` + `dry_run_flag`（M-2） |
| `migrate_utc_to_utc8.py` | 76 | 一次性 | RELEASE.md:957；已改用 `_common`（M-2） |
| `fix_plan_retest_state.py` | 100 | 一次性 | RELEASE.md:65；已改用 `_common`（M-2） |
| `backfill_retest_src_report.py` | 88 | 活跃·发布流程（2026-09-19 新增） | `upgrade.sh:118`（每次升级自动执行，失败不阻断）；按 `source` 文本回填 `testing_plan_retest_rounds.src_report_id`，使报告复测三态对存量和新数据一致（幂等、`--dry-run`） |
| `fix_attachment_paths.py` | 78 | 一次性（2026-09-19 安全整改） | RELEASE.md `[2.18.1]` 安全条款；置空春耕行动/远程检测中不符合上传白名单的存量附件路径（`--dry-run` 仅统计，落库前备份 `storage/backups/`） |
| `fix_retest_title_html.py` | 78 | 一次性（2026-09-19 安全整改） | RELEASE.md `[2.18.1]` 安全条款；转义存量复测记录标题（HTML 注入）并按新口径重算 `vulns.retest_html`（幂等：只处理含 `<`/`>` 的标题） |
| `probe_api.py` | 110 | 活跃·开发辅助（2026-09-21 新增） | AGENTS.md「验收口径·接口探针」（本地 / 容器 / CI 共用一份口径）；详见 §3.12 |
| `prune_test_schemas.py` | 99 | 活跃·开发辅助（2026-09-21 新增） | `scripts/test.sh --prune` / `test.ps1 -Prune`；详见 §3.14 |
| `check_api_contract.py` | 216 | 活跃·开发辅助（2026-09-22 新增） | 前后端契约检查（OpenAPI ↔ `src/types/index.ts`）；`.githooks/pre-push` 与 AGENTS.md「常用命令」；详见 §3.13 |

### 1.3 依赖矩阵

| 依赖 | 被哪些脚本需要 |
|---|---|
| `docker` / `docker compose` | 备份三件套、`restore.sh`、`migrate.sh`、`upgrade.sh`、`migrate.py`(间接，容器内执行) |
| `rsync` | `backup.sh:19`、`backup-incremental.sh:18` |
| `sha256sum` | `backup.sh:20`、`backup-incremental.sh:19`、`backup-common.sh:76` |
| `zstd`（可选） | `backup-common.sh:28`（缺失自动回退 gzip，仅提示变慢） |
| `flock` | `backup-common.sh:53`（缺失直接 `die`） |
| `curl` | `notify.sh:22` |
| `crontab` | `install-cron.sh` |
| `python3` | `setup-docker-mirror.sh:25`（用于合并 `daemon.json`） |
| `df` / `du` / `find` / `awk` | `disk-usage.sh` |
| `fallocate`\|`dd` / `mkswap` / `swapon` / `swapoff` | `swap-manager.sh` |
| `.env` 中 `BACKUP_WEBHOOK_URL` | `notify.sh:14`（缺失则静默跳过） |
| 运行中的 `postgres` + `api` 容器 | `backup.sh:25-26`、`backup-incremental.sh:30-31`（缺失直接失败/跳过） |
| `backups/baseline/storage` | `backup-incremental.sh:22`（缺失自动降级为锚点备份） |

---

## 二、部署脚本详述（`scripts/`）

### 2.1 `upgrade.sh` — 一键升级编排

- **用途**：拉代码 → 备份 → 重建镜像 → 清理构建缓存 → 迁移数据库 → 回填复测标题 → 回填复测轮次源报告 → 重启服务。
- **调用**：`bash scripts/upgrade.sh [--no-backup] [--no-pull] [--anchor]`（仓库根目录，见脚本 3-8 行）。
- **依赖**：`.env`（33 行强制校验）、`git`、`docker`；内部依次调用 `scripts/backup.sh` 或 `backup-incremental.sh`（55/58 行）、`scripts/notify.sh`（99 行）、`scripts/migrate.sh`（109 行）、`python -m scripts.backfill_retest`（113 行）、`python -m scripts.backfill_retest_src_report`（118 行）。
- **执行场景**：服务器版本升级；**不要**只 `git pull` 后 `up -d`（DEPLOY.md:336）。
- **关键顺序约定**：数据库迁移在 api 启动**之前**用一次性容器执行（脚本 10-11 行注释），避免 `create_all` 抢先建表导致迁移冲突。
- **失败影响**：升级前备份失败不阻断流程（fail-open，由每日差异快照兜底，92-101 行）；两个回填步骤仅打印提示（114/119 行）。
- **备注**：**2026-09-17 已修复 S-5** —— 原 `sudo docker compose …` 硬编码（50-51、84、105、113、120、126 行）全部改为 `$DOCKER`，并在脚本第 15-17 行 source `scripts/docker-cmd.sh`（root → `docker`，非 root → `sudo docker`，且尊重调用方预设的 `$DOCKER`）。

### 2.2 `migrate.sh` — 生产库结构迁移

- **用途**：在 api 容器内以 Alembic 为准演进 PostgreSQL 表结构（幂等）。
- **调用**：`bash scripts/migrate.sh`（脚本正文仅一条命令：`$DOCKER compose run --rm api python -m scripts.migrate`，见第 14 行）。
- **依赖**：`docker`、`.env`、已完成构建的 api 镜像。
- **执行场景**：每次发布后；`restore.sh:77` 提示恢复数据后须先跑本脚本再访问页面。
- **失败影响**：`set -euo pipefail`，迁移失败即中断（发布流程应中止）。
- **备注**：**2026-09-17 已修复 S-5** —— 命令不再硬编码 `sudo`，改为 source `scripts/docker-cmd.sh` 后使用 `$DOCKER`（root 环境自动省去 sudo，本地非 root 亦可直接执行，DEPLOY.md:392 的人工去 sudo 步骤已成历史）。

### 2.3 `backup.sh` — 迁移锚点（全量自包含备份）

- **用途**：生成自包含全量备份（db 逻辑备份 + storage 归档），并重建差异基线、清空旧差异快照、只保留最近 3 份锚点。
- **调用**：`bash scripts/backup.sh`（非 root 自动 `sudo` 重执行自身，9-11 行）。
- **依赖**：`docker`/`rsync`/`sha256sum`/（`zstd` 优先）/`flock`；运行中的 `postgres` 与 `api` 容器；`storage` 卷宿主机路径可解析（`backup-common.sh:61`）。
- **产物**：`backups/anchors/<年>/<月>/<时间戳>/{db.sql.zst|gz, storage.tar.zst|gz, MANIFEST.json}`、`backups/baseline/storage/`、软链 `backups/latest`。
- **执行场景**：每月 1 日 03:00（`install-cron.sh:13`）、MAJOR 发版（`upgrade.sh --anchor`）、跨机迁移前手工执行。
- **失败影响**：任一步失败即 `set -e` 退出；失败时通过 `notify.sh` 告警（98 行）。
- **安全设计**：`acquire_lock` 用 `flock` 保证同一时刻仅一份备份（`backup-common.sh:52-58`）。

### 2.4 `backup-incremental.sh` — 差异快照

- **用途**：基于最近锚点基线用 `rsync --link-dest` 做硬链接差异，只存变化文件。
- **调用**：`bash scripts/backup-incremental.sh`（同样自动 sudo 重执行，8-10 行）。
- **依赖**：同 `backup.sh`，且需 `backups/baseline/storage` 存在；**缺失时自动降级调用 `backup.sh`**（22-25 行，且在加锁之前以避免锁重入）。
- **产物**：`backups/snapshots/<年>/<月>/<时间戳>/{storage/, db.sql.zst, MANIFEST.json}`。
- **执行场景**：每日 02:00（`install-cron.sh:12`）、`upgrade.sh` 升级前（默认）。
- **失败影响**：失败不阻断升级（`upgrade.sh:93-101` 会告警）；cron 场景下次自然重跑（幂等）。

### 2.5 `backup-common.sh` — 备份公共函数库

- **用途**：被 `backup.sh` / `backup-incremental.sh` / `restore.sh` source 的函数与变量集合，**本身不执行顶层逻辑**（可安全多次 source）。
- **提供**：`DOCKER` 前缀自适应（root→`docker`，否则 `sudo docker`）、`now_ts`/`log`/`die`/`require_cmd`、`pick_compressor`（zstd→gzip）、`decompress_for`（按扩展名兼容历史 `.gz`）、`notify`（转调 `notify.sh`）、`acquire_lock`、`storage_volume_path`、`dump_db`、`file_sha256`、`write_manifest`。
- **调用方顺序约束**：必须先 `source` 再调用任何函数；`acquire_lock` 使用 fd 9 并在 EXIT 时解锁。

### 2.6 `restore.sh` — 数据恢复 / 跨机迁移

- **用途**：从迁移锚点（`storage.tar.*`）或差异快照（`storage/` 目录）恢复；兼容历史 `.gz` 产物。
- **调用**：`bash scripts/restore.sh <备份目录>`（如 `backups/anchors/2026/09/20260901_030001`），缺参即报错退出（20 行）。
- **依赖**：`.env`、`docker`；快照目录为 root 所有，故强制以 root 执行（11-13 行）。
- **执行场景**：更换 VPS、灾难恢复、整库回退（DEPLOY.md:249-271 六、更换 VPS）。
- **破坏性**：会 `docker compose down`、`DROP SCHEMA public CASCADE; CREATE SCHEMA public;`（46、57 行）——**目标库现有数据全部清除**。
- **收尾提示**：脚本末尾要求恢复后先执行 `bash scripts/migrate.sh`（77 行）。

### 2.7 `notify.sh` — webhook 告警

- **用途**：向企业微信机器人推送文本告警。
- **调用**：`bash scripts/notify.sh "消息内容"`（也被 `backup-common.sh:47` 的 `notify()` 调用）。
- **依赖**：`.env` 的 `BACKUP_WEBHOOK_URL`、`curl`；未配置时打印「跳过告警」并 `exit 0`（17-20 行）。
- **失败影响**：发送失败仅打印提示，不改变调用方退出码（24-27 行），故备份/升级流程不会被告警失败阻断。

### 2.8 `install-cron.sh` — 安装备份定时任务

- **用途**：幂等安装两条 root crontab（按 `# talos-backup-cron` 标记先删后写，11-23 行）。
- **安装内容**：每日 02:00 `backup-incremental.sh`；每月 1 日 03:00 `backup.sh`；日志写 `backups/cron.log`。
- **调用**：`sudo bash scripts/install-cron.sh`。
- **依赖**：`crontab`；脚本会 `mkdir -p backups`（9 行）。
- **注意**：cron 行内路径取自脚本执行时的 `pwd`（7-8 行），因此**必须在目标仓库根目录执行**，否则会写入错误路径。

### 2.9 `disk-usage.sh` — 磁盘占用分析

- **用途**：按占用降序输出前 N 大目录/文件，并单列大于阈值的大文件；结果同时输出终端与日志。
- **调用**：`sudo bash scripts/disk-usage.sh [-d 目录] [-l 日志] [-n 前N名] [-s 大文件阈值]`（默认 `/`、`/var/log/disk_usage_analysis.log`、20、`100M`）。
- **依赖**：`df`/`du`/`find`/`awk`；`-xdev` 限定同一文件系统（不跨挂载点，见 35-37 行说明）。
- **执行场景**：磁盘告警排障（判据见 `DEPLOY.md` 附「文件与磁盘」的「双视角」说明）、配置每日巡检。
- **容错**：日志目录不可写时自动降级为仅终端输出（72-78 行）。

### 2.10 `swap-manager.sh` — swap 开关

- **用途**：一键开启/关闭固定 4GB swap 文件 `/swapfile`，并管理 `/etc/fstab` 开机挂载。
- **调用**：`sudo bash scripts/swap-manager.sh <on|off|status>`（`enable|start`、`disable|stop`、`show` 为别名，191-193 行）。
- **依赖**：`fallocate`（失败自动回退 `dd`）/`mkswap`/`swapon`/`swapoff`/`free`。
- **安全设计**：已有活动 swap 时拒绝创建（66-72 行）；创建/删除前二次人工确认（`confirm()`）；改 `/etc/fstab` 前自动备份为 `/etc/fstab.bak.<时间戳>`（115、151 行）。
- **执行场景**：VPS 内存不足导致构建 OOM 时临时扩容。

### 2.11 `setup-docker-mirror.sh` — Docker 镜像加速

- **用途**：向 `/etc/docker/daemon.json` 合并 `registry-mirrors`（保留已有配置）。
- **调用**：`sudo bash scripts/setup-docker-mirror.sh`，可用 `DOCKER_MIRROR` 覆盖加速地址（默认 `https://mirror.ccs.tencent.com`，腾讯云 CVM 内网可用 `https://mirror.ccs.tencentyun.com`）。
- **依赖**：`python3`（32 行，缺失直接报错）、root。
- **执行场景**：新机首次部署前（DEPLOY.md:198-203）。
- **收尾要求**：必须 `sudo systemctl restart docker` 才生效（脚本会提示）。

### 2.12 `test.sh` / `test.ps1` — 后端测试统一入口（活跃·开发辅助）

- **用途**：把「跑后端测试」的正确姿势固化为命令 —— 关闭受管终端删除守卫、每次运行唯一 `--basetemp`（仓库内）、
  依赖服务（5432/6379）预检、可选并行与残留回收。
- **为什么需要**：手工跑 pytest 有三处「记错就得到误导性结果」的陷阱：① 受管终端的删除守卫会打断 pytest 清理
  basetemp，症状是「单文件全绿、全量几十个 ERROR」；② `--basetemp` 用系统临时目录会被守卫视为越界；③ 固定
  basetemp / 固定 schema 下并发跑两份测试会互相破坏。
- **调用**：
  - `bash scripts/test.sh` / `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`
  - 并行：`--workers 4` / `-Workers 4`（pytest-xdist，`--dist loadscope` 保证同一模块不拆散）
  - 回收：`--prune --yes` / `-Prune -Yes`（删除残留 `test_*`/`mig_*` schema 与 basetemp）
  - 跳过依赖预检：`--no-deps-check` / `-NoDepsCheck`（由 services 容器保证，仅临时流水线场景）
  - 其余参数原样透传给 pytest（如 `--cov=app`）
- **依赖**：`backend/.venv`（宿主机一律用项目 venv）；PG + Redis 在跑（可用 `--no-deps-check` 跳过检查）。
- **测试库隔离**：schema 由 `conftest.py` 按「进程 + xdist worker」派生（`test_<pid>[_gwN]`），本脚本不再干涉；
  详见 `docs/LOCAL_DEV_SETUP.md` 第四节。

### 2.13 `e2e.sh` / `e2e.ps1` — 端到端测试编排（活跃·开发辅助）

- **用途**：一条命令起**独立于开发栈**的 E2E 环境并跑 Playwright（系统 Chrome）：
  `vulnplatform_e2e` 库 → 迁移（`scripts.migrate`）→ 种子（`seed_dev_data --reset`）→ api(27016) →
  前端(27017，代理指向 27016) → `playwright test` → 收摊。**不同库、不同端口、独立 storage**，
  因此跑 E2E 不动开发数据，也不受"开发库正在被用"影响。
- **调用**：`bash scripts/e2e.sh` / `pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\e2e.ps1`
  （`--headed`/`-Headed` 带界面、`--keep`/`-Keep` 跑完保留栈、`--` 之后/`-PlaywrightArgs` 透传给 playwright）。
- **前置**：本机 PG 5432 + Redis 6379（DBngin）；`vulnplatform_e2e` 库已创建（一次即可，
  SQL 见 `docs/LOCAL_DEV_SETUP.md` 第六节）；根目录 `pnpm install`（Playwright 装在**仓库根**
  工具包里，不进 `frontend/`，避免污染前端三门禁）。
- **关键坑（都已踩过并固化）**：① 受管终端的删除守卫会拦截 Playwright 清理 `outputDir` → 脚本内设
  `CODEBUDDY_SAFE_DELETE_ENABLED=0`；② `pwsh -File` 下数组参数**不按逗号拆分** → 脚本内显式拆分；
  ③ PowerShell 变量名不区分大小写，局部变量不能叫 `$playwrightArgs`（会与参数同名而被覆盖）；
  ④ **收摊必须杀整棵进程树** —— `pnpm dev` 会派生 node/vite，只杀 pnpm 会留下孤儿继续监听 27017，
  下次运行会"静默复用旧栈"（旧前端代理指向旧 api）拿到似是而非的结果；故：收摊用 `taskkill /T`（Win）、
  `pkill -P` + 端口兜底（*nix），并在启动前**校验端口空闲**，被占用直接报错退出。
- **实测**：2026-09-22 首次落地 **3 passed / 1.4 min**（用例本体各 ~2.5 s，其余为起栈 + 种子）。

### 2.14 `clean.sh` / `clean.ps1` — 本地垃圾清理（活跃·开发辅助）

- **用途**：清理**可再生的本地产物** —— `__pycache__`（默认跳过 `.venv`）、`.pytest_cache` / `.ruff_cache`、
  `backend/_pytest_tmp`、`frontend/dist`、`backend/tests/test_storage` 内容、仓库内 `_*.txt` / `_*.log` 临时日志。
- **为什么需要**：此前清理靠临时命令 —— 实测 `Get-ChildItem -Recurse __pycache__ | Remove-Item` 会**静默跳过**
  且无法核对（数量对不上）；本脚本把「哪些该删、哪些绝不能删、删了多少」固化为可复核口径。
- **调用**：`bash scripts/clean.sh`（预演）/ 加 `--apply` 执行；`pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean.ps1 [-Apply]`；
  `--include-venv` / `-IncludeVenv` 才连 `.venv` 内的缓存一起清。
- **安全设计（硬白名单）**：`.git` / `.env` / `dev-database`（DBngin 活库）/ `backups` / `backend/storage` /
  `backend/.venv` / `frontend/node_modules` / `.codebuddy` / `.qoder` / `.workbuddy` / `design-demos`
  —— 任何目标命中即**中止**（防脚本被改坏后误删数据）。默认预演，删除前打印清单与合计体积。
- **实测**：2026-09-22 首次执行释放 **7.9 MB**（含 `frontend/dist` 3.5 MB），复跑输出「仓库已干净」。

---

## 三、后端脚本详述（`backend/scripts/`）

> 统一执行前提：**宿主机用项目 venv**（`backend/.venv/Scripts/python.exe -m scripts.<name>`，工作目录 `backend/`）；**容器内**用 `docker compose run --rm api python -m scripts.<name>` 或 `docker compose exec -T api python -m scripts.<name>`。
> 除 `seed_dev_data.py` 外，其余脚本均通过 `sys.path.insert(0, parent)` 自行补全导入路径。

### 3.1 `migrate.py` — 生产库结构迁移（活跃·发布流程）

- **用途**：以 Alembic 为唯一真相源演进 PostgreSQL 结构，并自动纳管「由 `create_all` 建的旧库」。
- **调用**：`python -m scripts.migrate`（生产上由 `scripts/migrate.sh` 包装）。
- **决策逻辑**（36-46 行）：存在 `alembic_version` → `upgrade head`；无版本表但 `users` 表存在 → `stamp head`（旧库一次性纳管）；全新空库 → `upgrade head`。
- **依赖**：`app.db.engine`、容器内已安装 alembic（由 `subprocess` 调 `python -m alembic`，31-33 行）。
- **关键约束**：为使「无版本表 + 业务表已存在 → stamp head」成立，**每次发布后都必须执行本脚本**，否则跨版本升级可能被误判纳管到 head 而漏掉中间 ALTER（脚本 11-12 行明确警告）。
- **幂等性**：是。

### 3.2 `backfill_retest.py` — 复测聚合标题回填（活跃·发布流程）

- **用途**：把旧格式「复测记录 N」标题重建为「复测记录yymmdd」（同日追加 `-1`、`-2` 后缀）。
- **调用**：`python -m scripts.backfill_retest`；**`scripts/upgrade.sh:109` 每次升级自动执行**（失败不阻断，110 行提示可手工补跑）。
- **依赖**：`app.api.v1.vulns._sync_vul_retest_html`（复用业务侧聚合实现，保证与线上同口径）、`VulRetestRecord` 表。
- **幂等性**：是——只处理 `retest_html` 中仍含旧式编号（`复测记录\s*\d+\s*：`，28 行）的漏洞，且刻意**不重写**「报告复测处理」直接写入的内容。
- **执行场景**：升级流程内置；数据修复时手工执行。

### 3.3 `sync_knowledge_templates.py` — 漏洞模板库同步（活跃·常规运维）

- **用途**：以 `backend/knowledge-import-vulnerabilities.json` 为唯一权威源，按「漏洞名称」upsert `knowledge_entries`。
- **调用**：
  - `python -m scripts.sync_knowledge_templates --dry-run`（只打印差异）
  - `python -m scripts.sync_knowledge_templates`（仅 upsert）
  - `python -m scripts.sync_knowledge_templates --prune`（同时删除文件外的存量条目）
  - `--file <路径>` 可指定其他数据文件（78 行）
- **依赖**：`app.constants.VUL_LEVEL`、`app.core.sanitize.sanitize_html`、`vuln_types` 表真实码值（94-97 行校验）。
- **数据校验**（`_load_items`，36-62 行）：必须为非空数组、条目为对象、`vulnerability_name` 非空且唯一、`severity_level` 在字典内、`references` 为数组且仅接受 http/https。
- **幂等性**：是；`--dry-run` 分支不触碰 ORM 实例（99 行注释，规避 rollback 后的 `MissingGreenlet`）。
- **执行场景**：模板库内容变更后的唯一入口（USER_GUIDE.md:251-257）；**不要在页面上单条修改**，否则下次同步会被覆盖。

### 3.4 `seed_dev_data.py` — 开发种子数据（活跃·开发辅助）

- **用途**：清空全部业务表后重建高质量演示数据（近 12 个月时间线、7 种工单状态、6 种漏洞状态、5 类来源、资产-漏洞-工单-报告完整关联、知识库复用 JSON 数据源）。
- **调用**：`python -m scripts.seed_dev_data --reset` —— **不追加 `--reset` 会直接退出**（620-623 行）。
- **依赖**：`scripts.knowledge_data.SEED_DATA`（68 行）、`app.models`、`app.core.security.hash_password`。
- **环境处理**：先解析仓库根 `.env` 得到本机开发库 DSN（`postgresql+asyncpg://…@127.0.0.1:5432/vulnplatform`，26-49 行），再以 `setdefault` 注入；另注入 `VP_DISABLE_QUEUE=1`、`VP_SECRET_KEY=dev-…`（51-52 行）。必须在导入 app 之前设置。
- **破坏性**：先 `create_all` 再对 `ALL_TABLES`（71-79 行，26 张业务表）逐表 `DELETE`。
- **账号**：`admin / admin123`（管理员）；其余测试账号密码统一 `Talos@2026`。
- **✅ 目标库守卫（原 P1 风险，2026-09-17 已修复；2026-09-21 随 SQLite 收口改造）**：`setdefault` 注入**只在变量缺失时生效**，若环境中已导出指向生产库的 DSN，本脚本会清空该库并写入演示数据。现启动时调用 `_assert_dev_database()`（590-617 行）：要求**库名 ∈ {`vulnplatform`, `vulnplatform_test`} 且主机为回环地址**，二者缺一即以**退出码 2 拒绝执行**；缺失/非法的 DSN 一律 fail-closed（守卫用例 `tests/test_seed_dev_data_guard.py`）。

### 3.5 `knowledge_data.py` — 模板库数据加载（活跃·共享模块）

> 2026-09-17 由 `seed_knowledge.py` 合并而来（审计 M-1）：加载逻辑此前在 `seed_knowledge` 与
> `sync_knowledge_templates` 中各有一份，现统一到本模块；`seed_knowledge.py` 的 upsert CLI
> 是 `sync_knowledge_templates` 的子集，已随之删除。

- **用途**：把 `knowledge-import-vulnerabilities.json`（135 条，唯一权威数据源）加载为 `SEED_DATA` 元组视图。
- **调用**：无独立入口，被脚本导入：`from scripts.knowledge_data import SEED_DATA`（当前唯一使用方 `seed_dev_data.py`）。
- **依赖**：仓库内 JSON 数据文件；模块导入即校验「非空数组」，避免静默写入空数据。
- **执行场景**：开发种子数据；**正式环境模板库同步请用 `sync_knowledge_templates`**（支持 `--dry-run` / `--prune`，且按 `vuln_types` 表真实码值校验）。

### 3.6 `fix_retest_section_dup.py` — 章节内嵌复测详情清理（一次性）

- **用途**：幂等剥离 `report_sections.content_html` 中内嵌的「复测详情」副本（历史上 `vuln_section_html` 曾把 `vul.retest_html` 追加到章节尾部，导致面板重复且导出停留在旧快照）。
- **调用**：`python -m scripts.fix_retest_section_dup [--dry-run]`。
- **依赖**：`app.services.report_html.RETEST_LABEL_HTML / strip_embedded_retest`（与业务侧同一剥离实现）。
- **产物**：改动前把原值备份到 `storage/backups/report_sections_retest_<时间戳>.json`（92-100 行）；剥离后正文为空的章节会单独列出待人工复核（107-108 行）。
- **幂等性**：是（剥离逻辑对已清理内容不再产生变更）。
- **调用出处**：DEPLOY.md:139-172（2.12.2 升级步骤）、RELEASE.md:253。
- **注意**：`--dry-run` 分支刻意先取纯数据快照再 rollback，以规避异步会话 `MissingGreenlet`（60-63 行注释）。

### 3.7 `fix_plan_retest_state.py` — 工单复测状态纠偏（一次性）

- **用途**：把「已标记复测完成、但仍存在未闭环漏洞」的工单回退为「复测中(50)」，清空 `retest_done_time` 并撤销最近一轮复测完成点。
- **调用**：`python -m scripts.fix_plan_retest_state [--dry-run]`。
- **依赖**：`app.constants.PlanStatus/VulStatus`、`app.services.plan_service.reopen_retest_round`、`settings.storage_sub("backups")`。
- **幂等性**：是；**只向下纠偏，不反向把 50 改成 60**（脚本 10 行明确说明，避免覆盖人工状态）。
- **产物**：`storage/backups/plan_retest_state_<时间戳>.json`。
- **调用出处**：RELEASE.md:65（v2.17.1 工单级复测口径修复）。

### 3.8 `repair_report_section_order.py` — 报告章节顺序修复（一次性）

- **用途**：按 `import_records.seq` 重排因历史乱序写入导致的章节 `order`；无导入记录的手工章节保持相对顺序排在末尾。
- **调用**：`python -m scripts.repair_report_section_order [--dry-run]`。
- **依赖**：`Report`/`ReportSection`/`ImportRecord`；同一漏洞取最小 `seq`（首次导入序号，55-60 行）。
- **幂等性**：是（无变更即跳过）。
- **调用出处**：RELEASE.md:305。

### 3.9 `backfill_vul_submit_time.py` — 漏洞提交时间更正（一次性）

- **用途**：把历史已确认报告导入批次关联漏洞的 `submit_time` 回填为批次 `meta.report_date` 的 14:00（与报告 `create_time` 口径一致）。
- **调用**：`python -m scripts.backfill_vul_submit_time [--dry-run]`。
- **幂等性**：是（`vul.submit_time == target` 则跳过，59-60 行）；缺 `report_date` 的批次计入跳过数并打印（65、68 行）。
- **调用出处**：RELEASE.md:546。

### 3.10 `migrate_utc_to_utc8.py` — UTC→UTC+8 历史数据迁移（一次性）

- **用途**：把存量 naive UTC 时间整体 +8 小时，遍历 `Base.metadata.sorted_tables` 中所有 `DateTime` 列（37-47 行），统一用 `INTERVAL '8 hours'`（48 行；原 SQLite 分支已随「统一 PostgreSQL 单栈」收口删除）。
- **调用**：`python -m scripts.migrate_utc_to_utc8 [--dry-run]`。
- **依赖**：`app.models`（须先导入以注册全部模型，22 行）、`app.core.config.settings.DATABASE_URL`、`app.db.Base`。
- **重要限制**：纯日期字符串列（如 `reports.test_start/test_end`）无法精确换算，**脚本不处理，需人工核对**（14-15 行）。
- **幂等性**：**否** —— 会对所有 DateTime 列重复 +8h，**只能执行一次**；全新空库无需执行（16 行）。
- **调用出处**：RELEASE.md:957。

### 3.11 `migrate_from_insight2.py` — 洞察 2.0 数据迁移（**已于 2026-09-17 删除**）

- **原用途**：从旧系统 MySQL 迁移用户/组/应用/资产/漏洞/漏洞日志。
- **失效证据（2026-09-17 实测，项目 venv）**：
  - 脚本 31 行 `from app.models import App, …`，而 `app.models` 已无 `App` → `hasattr(app.models, "App") == False`；
  - 依赖的 `Asset.value / asset_type / is_open / is_https` 字段均已不存在（`Asset` 已合并原 App 语义，见 `backend/app/models/business.py:20-55`）；
  - 依赖的 `Vul.app_id` 已不存在。
  - 结论：**运行时第一步 import 即抛 `ImportError`**，语法可编译但功能不可用。
- **处置**：已删除（见 §4.1 D-1），`README.md` / `README_EN.md` 的「旧数据迁移」章节已同步改写为重写指引。

---

## 四、合并与废弃清单

### 4.1 废弃 / 删除

| 编号 | 对象 | 结论 | 理由与执行步骤 |
|---|---|---|---|
| **D-1** | `backend/scripts/migrate_from_insight2.py`（196 行） | ✅ **已于 2026-09-17 删除** | 实测必然 `ImportError`（§3.11）。已同步改写 `README.md` / `README_EN.md` 的「旧数据迁移」章节为重写指引（含按当前 `Asset`/`Vul` 模型重写的要点）。 |

### 4.2 合并

| 编号 | 对象 | 结论 | 执行步骤 |
|---|---|---|---|
| **M-1** | `seed_knowledge.py` + `sync_knowledge_templates.py` | ✅ **已于 2026-09-17 完成合并** | 新增 `backend/scripts/knowledge_data.py`（`DATA_FILE` + `load_seed_data()` + `SEED_DATA`，模板库数据唯一加载实现）；`seed_dev_data.py` 改为 `from scripts.knowledge_data import SEED_DATA`；`seed_knowledge.py` 已删除（其 upsert CLI 是 `sync_knowledge_templates` 的子集，而后者按 `vuln_types` 表真实码值校验、口径更严；`USER_GUIDE.md` 早已指向 sync）。 |
| **M-2** | 6 个一次性脚本的重复样板 | ✅ **2026-09-18 完成（6/6）** | `backend/scripts/_common.py`（86 行）提供 `bootstrap()`（静默 SQLAlchemy 回显 + 幂等注入 sys.path）、`dry_run_flag()`、`save_backup(records, prefix, indent=2)`、`run(main, **kwargs)`。**6 个脚本全部迁移**：`backfill_retest.py`（50→47）、`backfill_vul_submit_time.py`（73→69）、`fix_plan_retest_state.py`（109→100）、`fix_retest_section_dup.py`（112→98）、`repair_report_section_order.py`（87→83）、`migrate_utc_to_utc8.py`（81→76）；`backend/scripts/` 合计 **1 403 → 1 387 行**。**关键修正**：`save_backup` 原先写死 `backend/storage/backups`，与既有脚本的 `settings.storage_sub("backups")`（尊重 `VP_STORAGE_DIR`，容器内 `/app/storage/backups`）不一致 → 已统一，且 `settings` 改为**函数内延迟导入**（避免 `import scripts._common` 时因必填环境变量缺失连带影响只用 `run()` 的脚本）。`run()` 的 docstring 固化「dry-run 须先取纯数据快照再 rollback（规避 `MissingGreenlet`）」约定。**验证**：ruff 全绿；dev.db 副本上 8 次运行（4 脚本 × dry/real）输出与退出码**与改造前逐字一致**（该验证发生于 2026-09-18，当时本地库仍为 SQLite；SQLite 已于 2026-09-21 收口）；另以造数运行触发两个备份分支，确认备份落在配置目录且为合法 JSON。 |
| **M-3** | shell：三处「非 root 自动 sudo 重执行自身」 | **抽取**到 `backup-common.sh::ensure_root()` | 现存三份几乎相同的代码块：`backup.sh:9-11`、`backup-incremental.sh:8-10`、`restore.sh:11-13`。调用顺序需调整为「先 source common（无副作用，仅计算 `DOCKER`）→ `ensure_root` → 再 `cd`」。优先级 P3（收益小、需回归验证备份流程）。 |
| **M-4** | shell：`backup.sh` 与 `backup-incremental.sh` 公共序列 | **可选抽取** `prepare_backup_env()` / `finalize_manifest()` | 重复项：容器前置检查 2 行、`ts`/`ym` 生成、`VOL_PATH` 解析、`mkdir -p`、`MANIFEST.json` 写入、`backups/latest` 软链、`notify` 收尾（约 15 行）。优先级 P3。 |

### 4.3 明确「不建议合并」（含理由，避免后续重复讨论）

| 编号 | 对象 | 结论与理由 |
|---|---|---|
| **S-5（问题）** | `scripts/migrate.sh`、`scripts/upgrade.sh` 硬编码 `sudo docker` | ✅ **2026-09-17 已修复**：新增 `scripts/docker-cmd.sh`（13 行，root → `docker`、非 root → `sudo docker`、尊重调用方预设的 `$DOCKER`）；`backup-common.sh:6-8` 改为 source 该文件（保留原 `$DOCKER` 语义），`migrate.sh`/`upgrade.sh` 同步 source 并把 12 处硬编码改为 `$DOCKER`。**验证**：`bash -n` 4 个脚本全过；`backup-common.sh`/`docker-cmd.sh` 在非 root 下实测得到 `DOCKER=[sudo docker]`；显式预设 `DOCKER=podman` 时被尊重；`grep -rn 'sudo docker' scripts/` 已无真实调用点（仅注释与本地赋值）。 |
| **S-6（不合并）** | `install-cron.sh`（23 行）、`notify.sh`（21 行） | 体量虽小但职责独立：`notify.sh` 被 `backup-common.sh:47` 作为库依赖调用，`install-cron.sh` 是一次性安装器。合并会引入无谓耦合。 |
| **S-7（不合并）** | `disk-usage.sh`、`swap-manager.sh`、`setup-docker-mirror.sh` 合并为 `ops.sh <sub>` | 三者均被文档以完整命令形式单独引用（`DEPLOY.md:198,203` 与附「文件与磁盘」；`RELEASE.md:434,964`），合并会使文档中所有可复制命令失效，收益（减少 2 个文件）远低于迁移成本。保持独立，仅在本文档集中登记。 |

### 4.4 一次性脚本的处置方式（推荐轻量方案）

对 `backfill_vul_submit_time.py`、`repair_report_section_order.py`、`migrate_utc_to_utc8.py`、`fix_plan_retest_state.py`、`fix_retest_section_dup.py`：

- **推荐（轻量）**：**原地保留**，在文件头首行补注「一次性脚本，见 docs/SCRIPTS.md §3.x」，并在本文档登记状态。理由：生产现场文档中已出现 `python -m scripts.<name>` 形式的命令（如 `DEPLOY.md:139-172`），物理移动模块路径会使这些命令失效。
- **可选（物理归档）**：迁入 `backend/scripts/archive/`（新增 `__init__.py`），调用方式变为 `python -m scripts.archive.<name>`；**必须同步修改** `DEPLOY.md` / `RELEASE.md` 中的命令，否则现场升级步骤会直接失败。
- **不建议直接删除**：这些脚本尚未穷尽所有部署现场（例如 2.12.2 的章节清理步骤仍写在 DEPLOY 升级流程里），删除会让「从旧版本升级」的路径断裂。

### 3.12 `probe_api.py` — 关键接口探针（活跃·开发辅助）

- **用途**：把 AGENTS.md 验收口径里的「22 个关键接口全 200」固化为可重复执行的命令，取代此前「每次临时写探针
  脚本、跑完即删」的做法（口径不再随人漂移）。
- **调用**：`python -m scripts.probe_api --base-url <地址>`（可 `--username/--password` 覆盖账号、`--quiet` 只打印失败项）。
  地址：本地开发 `http://127.0.0.1:27015`、容器经前端反代 `http://127.0.0.1:27012`、容器内直连 `http://127.0.0.1:8000`。
- **依赖**：仅 `httpx`（**不导入 app 配置**，故无需 `VP_SECRET_KEY`，容器内外均可跑）。
- **退出码**：0 = 全部 200；1 = 登录失败或任一接口非 200（打印明细）。
- **已知坑**：输出标记刻意用 ASCII（`OK` / `FAIL`）而非 `✓`/`✗` —— Windows 控制台默认 GBK，非 GBK 字形会抛
  `UnicodeEncodeError`（2026-09-21 实测）。

### 3.13 `check_api_contract.py` — 前后端契约检查（活跃·开发辅助）

- **用途**：把「API 到底返回哪些字段」与「前端 TS 声明了哪些字段」做**双向集合比对**，拦住契约漂移。
  前端 160 个 vitest 用例全部 mock axios、浏览器冒烟按页面抽检，两层都覆盖不到字段级契约。
- **调用**：`python -m scripts.check_api_contract [--strict] [--verbose]`（**不连数据库**，只读 `app.openapi()`；
  自带占位 `VP_SECRET_KEY`，任意环境可跑）。
- **两方向严重性刻意不同**：**TS 有 / API 无 → 失败**（前端读永不返回的字段，运行时静默 undefined ——
  本项目 `el-table` 插槽是 `any`，`vue-tsc` 抓不到）；**API 有 / TS 无 → 默认告警**（本项目 TS 只声明
  实际消费字段，属有意为之），加 `--strict` 才视为失败。
- **边界**：带索引签名（`[key: string]: any`）的 TS 类型视为开放类型并跳过（如 `ReportSection`）。
- **已登记的有意差异**：脚本内 `TS_ONLY_ALLOW`（每条附理由）。
- **首运行战果（2026-09-22）**：24 组映射中发现 `NonpenPlan.asset_names` **两端皆无来源** ——
  `NonpenPlanOut` 不返回该字段、前端也无赋值，`NonpenPlanWorkflowDrawer` 的「关联资产」块因此永不渲染
  （死代码）。**已按方案①修复**：`NonpenPlanOut` 新增 `asset_names`，由 `nonpen_service.asset_name_map` /
  `to_out` 在创建 / 列表 / 详情 / 更新 / 流转五类响应中统一填充（按 `asset_ids` 原顺序，资产已删则跳过），
  并由 `tests/api/test_api_nonpen.py` 固化回归。

### 3.14 `prune_test_schemas.py` — 测试残留 schema 回收（活跃·开发辅助）

- **用途**：回收被强杀进程（CI 取消、`kill -9`）遗留的 `test_*` / `mig_*` schema。测试改为「每进程独占 schema」后
  互不干扰，但异常终止不会执行 teardown，故需要本工具。
- **调用**：`python -m scripts.prune_test_schemas`（**默认只列出**）/ `--yes` 删除；也可经
  `scripts/test.sh --prune --yes`、`scripts/test.ps1 -Prune -Yes` 调用（同时清理 basetemp）。
- **安全设计**：只处理 `test_*` / `mig_*`，绝不动 `public` 与业务 schema；目标库必须是**回环地址上的 `*_test` 库**
  （与 `seed_dev_data.py` 同口径，fail-closed）；「确认无并发测试在跑」由人拍板（加 `--yes`）。
- **依赖**：仅 SQLAlchemy + 自身解析的 DSN（`VP_DATABASE_URL` 优先，否则读仓库根 `.env`），**不导入 app 配置**。

---

## 五、维护约定（新增 / 修改脚本时）

1. **单一入口**：新增运维能力优先扩展既有脚本的子命令或参数，而不是新建文件；确需新建时，同步更新本文档总览表与详述章节。
2. **幂等优先**：数据类脚本必须支持重复执行（参考 `sync_knowledge_templates`、`fix_*` 系列），并提供 `--dry-run`；`migrate_utc_to_utc8.py` 属例外，其头部已明确「只能执行一次」。
3. **破坏性操作三件套**：显式确认参数（如 `--reset`）+ 落库前备份到 `storage/backups/`（或 `/etc/fstab.bak.*`）+ 打印将变更的对象清单。
4. **敏感环境防护**：涉及清库/大批量写库的脚本必须校验目标 DSN（参照 `seed_dev_data.py::_assert_dev_database()` 的实现与 `tests/test_seed_dev_data_guard.py`），禁止仅依赖 `setdefault`。
5. **文档同步**：脚本的参数、产物路径、调用方发生变化时，必须同时更新 `docs/DEPLOY.md`（现场操作）、`docs/RELEASE.md`（版本记录）与本文档。
6. **命名**：一次性/纠偏脚本统一 `fix_*` / `backfill_*` / `repair_*` / `migrate_*` 前缀（现状已符合）；shell 脚本用短横线（`backup-incremental.sh`），Python 模块用下划线。
