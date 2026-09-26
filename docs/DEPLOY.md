# Talos 部署与运维手册

面向在 VPS 上用 Docker 部署、升级、备份与迁移 Talos 的操作指引。生产采用
`docker-compose.yml` 编排的 **PostgreSQL 16**（与本地开发/测试同方言同大版本，仅部署形态不同：
容器 vs 本机 DBngin）。

- 生产数据只存放在两个 Docker 命名卷：`pg_data`（数据库）、`storage_data`（上传图片 / 导入导出原始文档）。
- 后端启动时会自动建表并写入内置角色 / admin / 字典预设（`init_db`，幂等）。
- 版本化的表结构演进由 **Alembic** 负责（见「三、版本升级」）。

---

## 一、首次部署

前置：服务器已装 Docker 与 Docker Compose 插件，并已拉取本仓库代码。

1. 准备环境变量（`.env` 已被 `.gitignore` 忽略，切勿入库）：

   ```bash
   cp .env.example .env
   # 编辑 .env，至少填写：
   #   VP_SECRET_KEY     —— >=32 位强随机，生成： openssl rand -hex 32
   #   POSTGRES_PASSWORD —— 数据库口令
   # 可选（安全相关，默认值已按「浏览器 → 前端 Nginx → API」单层代理校准）：
   #   VP_NOTIFY_HOST_ALLOWLIST  —— 通知渠道 webhook 主机白名单（逗号分隔）。
   #     默认只允许公网地址（防 SSRF）；如告警需经企业内网中继转发，在此显式放行该主机名。
   #   VP_TRUSTED_PROXY_HOPS     —— 本服务前方**可信反向代理层数**（默认 1）。
   #     客户端 IP 取 X-Forwarded-For 右起第 N 项；外层还有宿主 Nginx/CDN 时调大，
   #     且每层都必须用 $proxy_add_x_forwarded_for 追加真实对端。0 = 完全不信任转发头。
   #   VP_COOKIE_SECURE          —— HTTPS 部署时设为 true（图片 Cookie 加 Secure）。
   #     HTTP 部署下开启会被浏览器拒收，表现为富文本图片不显示。
   #   VP_ARCHIVE_MAX_*          —— docx/xlsx 解压配额（条目数/解压总量 MB/压缩比），防 zip 炸弹。
   ```

   > **API 端口不得直接对外暴露**：`VP_TRUSTED_PROXY_HOPS` 的正确性依赖「每一层代理都追加
   > 真实对端」，仅暴露前端（27012）即可；同时 API 侧业务接口均需登录，直连会绕过来源 IP 口径。
   >
   > **图片访问需要登录**（安全整改 批次 E）：富文本图片由 `/storage/uploads/images/<name>`
   > 鉴权下发，浏览器凭证是登录时下发的 `vp_img` Cookie（HttpOnly、作用域限定到该路径）。
   > 若反向代理改写了 Cookie 域/路径或剥离 Cookie，会导致图片 401（表现为图片不显示）。
   >
   > **首次升级到该版本时**：升级前已打开的页面还没有这个 Cookie，会出现「整页图片不显示」，
   > 让在线用户**刷新一次页面**（或重新登录）即可恢复；新版前端已内置自愈
   > （图片失败时自动补发凭证并重试一次，见 `frontend/src/utils/imageAuth.ts`）。

   > `docker-compose.yml` 对 `VP_SECRET_KEY` / `POSTGRES_PASSWORD` 使用了 `:?` 强校验，
   > 未设置会直接拒绝启动。仓库内 `.env` 若已配置好可直接复用。

2. 一键启动：

   ```bash
   docker compose up -d --build
   ```

   表结构、内置角色 / 字典、admin 账号都会自动创建，**无需手工初始化数据库**。

3. 取初始 admin 口令（若 `.env` 未设 `VP_INITIAL_ADMIN_PASSWORD`，随机生成且仅打印一次）：

   ```bash
   docker compose logs api | grep -i "初始密码"
   ```

4. 访问：前端 `http://<VPS_IP>`（80 端口）。前端 nginx 已把 `/api` 同源反代到后端，
   通常无需对外暴露 8000 端口，也无需额外配置 CORS。

---

## 二、是否需要清除数据？

首次部署**不需要**任何清理：postgres 是全新空卷，天然干净。

仅当你想丢弃某个**旧 `pg_data` 卷**里的历史数据、重新开局时才需清库：

```bash
docker compose down -v   # ⚠️ 会删除全部卷及业务数据，确认无数据后再执行
```

---

## 三、版本升级（前后端更新）

### 3.1 版本号同步（发布约定）

每次发布需同步三处版本号，并打标签（详见 `docs/RELEASE.md`）：

1. `docs/RELEASE.md`：把 `Unreleased` 条目移入新版本段落
2. `backend/app/core/config.py` 的 `APP_VERSION`
3. `frontend/package.json` 的 `version`

```bash
git tag -a v0.9.0 -m "release 0.9.0"
```

### 3.2 部署新版本

一键升级（推荐，等价于「备份 → 拉代码 → 重建镜像 → 迁移数据库 → 重启」全流程）：

```bash
bash scripts/upgrade.sh
# 可选： --no-backup 跳过升级前备份， --no-pull 跳过 git pull
```

或手动分步执行：

```bash
git pull
docker compose build              # 重建镜像
bash scripts/migrate.sh           # 先迁移数据库结构（见下）
docker compose up -d              # 再启动服务
```

> `upgrade.sh` 会把数据库迁移放在 api 服务启动【之前】用一次性容器执行，确保 Alembic 先于
> 后端 `create_all` 应用结构变更，避免新增表冲突。

### 3.3 数据库结构升级（关键）

- **新增整张表**：后端启动的 `create_all` 会自动建出缺失的表，无需额外操作。
- **改动已有表的字段**（加 / 改 / 删列）：`create_all` 不会修改已存在的表，
  必须通过 Alembic 迁移。已在仓库建立基线迁移（`backend/alembic/versions/e9054a84d196_baseline_schema.py`）。

开发侧——当本次发布改动了已有表结构时，生成迁移并提交：

```bash
cd backend
# 用一次性空库自动比对模型与基线，生成增量迁移（连到线上库或临时库均可）
python -m alembic revision --autogenerate -m "描述本次结构变更"
# 打开 alembic/versions/ 下新生成的文件人工核对：
#   - 只保留本次真实的 ALTER / 新增表操作，删除误报
#   - 给「已有数据的表新增 NOT NULL 列」补 server_default，避免存量行报错
git add alembic/versions/xxxx_*.py
```

运维侧——每次发布后在服务器执行（幂等、自动纳管旧库）：

```bash
bash scripts/migrate.sh
```

`scripts/migrate.sh` 内部调用 `backend/scripts/migrate.py`，决策逻辑：

| 库状态 | 动作 |
| --- | --- |
| 已有 `alembic_version` 表 | `alembic upgrade head`，应用增量迁移 |
| 无版本表但业务表已存在（历史 `create_all` 库） | `alembic stamp head`，一次性纳管 |
| 全新空库 | `alembic upgrade head`，从基线建全表 |

> 注意：为保证纳管判断成立，**每次发布后都要执行 `migrate.sh`**；跨多个版本一次性升级时尤其不能跳过，
> 否则旧库可能被误纳管到 head 而漏掉中间版本的 ALTER。

**放宽列类型（如 `varchar(512)` → `TEXT`）**：`migrate.sh` 会自动应用，无需回填数据、无需停机维护。

```bash
# 迁移 d9e0f1a2b3c4：vulns.affected_url / import_records.affected_url 由 varchar(512) 放宽为 TEXT
bash scripts/migrate.sh
# 核对：两列应显示 text
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d vulns" | grep affected_url'
```

> ⚠️ **回滚注意**：该迁移的 `downgrade` 把列改回 `varchar(512)`，**若库中已存在超过 512 字符的数据，
> PostgreSQL 会直接拒绝该 DDL**。紧急回滚请只回退应用代码（`git checkout <旧提交> && docker compose up -d --build`）
> 并**保留 TEXT 列**——列变宽对旧代码完全无害；确需整库回退则用升级前备份走 `scripts/restore.sh`。

### 3.4 版本相关的一次性数据维护（按需执行）

部分版本除代码与结构迁移外，还需对**存量数据**做一次性规整。已内置脚本的版本见下表；
命令须在 `upgrade.sh` 完成之后执行（新镜像已生效，容器内才有对应脚本）。

| 版本 | 脚本 | 用途 |
| --- | --- | --- |
| 2.12.2 | `scripts.fix_retest_section_dup` | 剥离存量报告章节正文尾部内嵌的「复测详情」副本（见下） |
| 2.20.3 | `scripts.enable_trgm_indexes` | 建立前后通配符检索的 pg_trgm GIN 索引（可选，见「十、」） |
| — | `scripts.backfill_retest` | 复测聚合标题回填，`upgrade.sh` 已自动执行（见 3.2） |

#### 2.12.2 清理存量报告章节的复测详情副本

**背景**：早期 `vuln_section_html` 会把 `vulns.retest_html` 追加为章节正文的最后一个元素，
导致同一份复测详情既内嵌在章节正文（漏洞详情框）尾部、又出现在复测详情框，界面重复展示；
且章节快照不随复测更新，导出报告会因「正文已含复测详情」跳过追加最新内容，造成**导出遗漏最新复测结论**。
2.12.2 起新生成章节不再内嵌，存量数据用本脚本清理（幂等，可重复执行）。

```bash
# 在 VPS 仓库根目录（docker-compose.yml 所在处）执行；路径按实际部署替换
cd /opt/talos

# 1) 试运行：只统计将清理的章节数并逐条打印长度变化，不写库
sudo docker compose run --rm api python -m scripts.fix_retest_section_dup --dry-run

# 2) 确认无误后执行清理；落库前会自动把被修改章节的原值备份为 JSON
sudo docker compose run --rm api python -m scripts.fix_retest_section_dup
```

执行输出示例：

```text
含内嵌复测详情段的章节：227 个
清理完成：已剥离 227 个章节的内嵌复测详情段
原值备份：/app/storage/backups/report_sections_retest_20260910125131.json
```

**验证**（用同一个脚本的试运行即可，无需手写 SQL）：

```bash
# 再跑一次 dry-run，应输出「含内嵌复测详情段的章节：0 个」
sudo docker compose run --rm api python -m scripts.fix_retest_section_dup --dry-run

# 复测详情本身不丢：内容仍保存在 vulns.retest_html
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) AS vulns_with_retest FROM vulns WHERE length(retest_html) > 0"'
```

**备份与回滚**：

```bash
# 备份文件位于 storage_data 卷内（不会随容器删除），可列目录或拷出留档
sudo docker compose exec -T api ls -l /app/storage/backups/
sudo docker compose cp api:/app/storage/backups/report_sections_retest_<时间戳>.json ./
```

> 备份 JSON 内含每条章节的 `id` / `report_id` / `vul_id` / `before` / `after` 原文，可据此逐条还原；
> 若需整库回退，使用升级前备份（`upgrade.sh` 已自动生成）走 `scripts/restore.sh`（见「六、更换 VPS」）。

#### 2.20.3 遗留惰性列清理（迁移自动完成，需先备份）

该版本删除 5 个历史列：`assets.ports / services / middleware / database_type` 与
`testing_plans.create_nonpen`。**每列一个独立迁移**（`a5b6c7d8e9f0` → `c8d9e0f1a2b3` → `d3e4f5a6b7c8`），
`upgrade.sh` 会随 `alembic upgrade head` 自动执行，无需手工脚本。

- 删列前已核查全仓无读写（值早已迁入 `port_services` / `middlewares` / `databases`；
  `create_nonpen` 改为仅入参不落库），且各迁移的 `downgrade` 会按原定义重建列。
- **升级前请确保已有一份可用备份**（`upgrade.sh` 默认生成）；如需回退某一列，执行
  `alembic downgrade <该迁移的 down_revision>` 即可恢复该列定义（数据不可恢复，故备份是关键）。

---

## 四、Docker 镜像加速（腾讯云，可选但推荐）

默认 Docker 从 docker.io 官方源拉取镜像，在国内通常较慢。用腾讯云镜像加速：

1. **一键配置**（仓库已提供脚本，合并保留 `daemon.json` 已有配置）：

   ```bash
   sudo bash scripts/setup-docker-mirror.sh
   ```

   - 默认公网加速地址 `https://mirror.ccs.tencent.com`；
   - 腾讯云 CVM 内网更快（免公网流量）：
     `sudo DOCKER_MIRROR=https://mirror.ccs.tencentyun.com bash scripts/setup-docker-mirror.sh`

2. **重启 Docker 生效**：

   ```bash
   sudo systemctl restart docker
   ```

3. **验证**：

   ```bash
   docker info | grep -A3 'Registry Mirrors'
   ```

   之后 `docker compose build` / `docker pull` 均走腾讯云加速，构建 `worker`
   镜像时拉取 `python:3.12-slim-bookworm` 等基础镜像明显提速。

---

## 五、备份（迁移锚点 + 每日差异快照）

实现为「**全量锚点 + 差异快照**」：数据库每次全量 `pg_dump`，`storage` 卷用 `rsync --link-dest` 硬链接复用未变文件，因此每日只增量占盘。脚本细节见 `docs/SCRIPTS.md` §2.3~2.8。

在运行中的服务器、仓库根目录执行：

```bash
bash scripts/backup.sh              # 迁移锚点（全量自包含）：每月 1 日 03:00 / MAJOR 发版 / 跨机迁移前
bash scripts/backup-incremental.sh  # 差异快照：每日 02:00 + 每次 upgrade.sh 升级前（默认）
```

产物（均在 `backups/`，已 `.gitignore`）：

| 路径 | 内容 | 保留策略 |
|---|---|---|
| `backups/anchors/<年>/<月>/<时间戳>/` | `db.sql.zst` + `storage.tar.zst`（无 `zstd` 的机器上产物为 `.gz`）| 只保留**最近 3 份**锚点；清空旧产物前先完成新锚点与基线校验 |
| `backups/baseline/storage/` | 差异比对基线（由最近锚点重建） | 随锚点更新 |
| `backups/snapshots/<年>/<月>/<时间戳>/` | `db.sql.zst`（或 `.gz`）+ `storage/`（硬链接差异）+ `MANIFEST.json` | 生成新锚点时清空旧差异 |
| `backups/latest` | 指向最近一次备份的软链 | — |

要点：

- **必须先有锚点**：`backups/baseline/storage` 缺失时 `backup-incremental.sh` 会自动降级为锚点备份（脚本 22-25 行），不会静默什么都不做。
- **定时**：`sudo bash scripts/install-cron.sh` 幂等安装两条 root crontab（每日差异 + 每月锚点），日志 `backups/cron.log`；**必须在仓库根目录执行**（cron 行取执行时的 `pwd`）。
- **告警**：`.env` 配置 `BACKUP_WEBHOOK_URL`（企业微信机器人）后，备份失败/升级异常经 `scripts/notify.sh` 推送；未配置则静默跳过，不影响主流程。
- **并发保护**：备份三件套用 `flock`，保证同一时刻只有一份备份在跑。
- **恢复 / 回滚**：`bash scripts/restore.sh <备份目录>`（锚点或差异快照皆可）→ 完成后**必须先 `bash scripts/migrate.sh`** 再访问页面。注意 `restore.sh` 是**破坏性**的（`DROP SCHEMA public CASCADE`），目标库现有数据全部清除。
- **异地**：建议定期把 `backups/` 同步到异地存储。
- **`zstd` 备份侧可选、恢复侧必需**（2026-09 起产物默认 `.zst`）：备份机有 `zstd` 时产出 `db.sql.zst` / `storage.tar.zst`（多线程，较 gzip 提速 3~5 倍）；缺失则自动回退 gzip 产出 `.gz`，只提示变慢。但**要恢复 `.zst` 产物的机器必须自带 `zstd`**（`restore.sh` / `restore-local.sh` 都按扩展名选解压器，缺 `zstd` 时解压即失败，不存在回退路径）——迁移/换机前先在目标机 `apt install zstd`（Windows 见「九」）。

> 备份不含 `.env`（内含密钥）。迁移 / 灾备时请另行安全保管 `.env`。

---

## 六、更换 VPS：平滑迁移不丢数据

需要迁移的只有三样：**数据库**、**上传文件**、**`.env`**。步骤：

1. 旧机器（建议先停写以保证一致性）：

   ```bash
   docker compose stop api worker    # 暂停写入
   bash scripts/backup.sh            # 生成 backups/<时间戳>/
   docker compose start api worker   # 如需继续对外服务可重新拉起
   ```

2. 把这些拷到新机器：仓库代码、`.env`（凭证必须与备份来源一致）、`backups/<时间戳>/` 整个目录。

3. 新机器（仓库根目录，已放好 `.env`）：

   ```bash
   bash scripts/restore.sh backups/<时间戳>
   ```

   脚本会：起 postgres → 导入 `db.sql.zst`（历史备份为 `.gz`，脚本按扩展名自动选解压器）到空库 →
  起 api 并解包 `storage.tar.zst` 到 `/app/storage` → 拉起全部服务。**目标机需已装 `zstd`**（见「五、备份」要点）。

4. 用原 admin 账号登录验证数据完整。

要点：

- **只想把备份数据导入本地开发库**（不起容器栈、目标是 DBngin）：见「九、把生产备份导入本地开发库」，不要在本地用本节的 `restore.sh`（它面向容器栈）。
- **`POSTGRES_USER/DB/PASSWORD` 必须与备份来源一致**，否则库名 / 连接对不上。
- `VP_SECRET_KEY` 保持一致可避免已登录用户令牌失效（改了不会丢数据，仅需重新登录）。
- `redis` / `gotenberg` 无状态，不用迁移。
- 恢复务必对准**空库**（新卷）执行，不要在已有业务数据的库上导入。
- **恢复完成后先跑一次 `bash scripts/migrate.sh` 再访问页面**（见「七、恢复后页面 500 排查」），
  否则备份库结构落后于代码版本时，新功能页面会因缺列报 500。

---

## 七、恢复后页面 500 排查（数据库结构不匹配）

### 现象

用 `restore.sh` 从旧备份 / VPS 恢复到新机器后，登录能进，但部分页面（如
测试计划页、报告中心页）接口返回 **500**。

### 根因

`restore.sh` 只恢复**数据**（`pg_dump` 导入），**不会执行 Alembic 迁移**。
而备份库的结构只代表备份时的代码版本：

- 备份库 `alembic_version` 停在旧版本（如 `b2c3d4e5f6a7`）；
- 当前代码已升级（head 如 `d4e5f6a7b8c9`），查询新增列时报：

  ```text
  sqlalchemy.exc.ProgrammingError: column reports.vul_edit_snapshot does not exist
  ```

后端的 `create_all` 只会补**缺失的表**，不会给已有表加列；而 schema 演进自 2026-09-21 起
只有 **Alembic 单轨**（SQLite 开发库专用的轻量迁移已随单数据库栈收口删除，**没有第二条兜底路径**）。
因此缺列必须靠 Alembic 补齐。

### 排查步骤

1. 看 api 日志定位具体报错列：

   ```bash
   docker compose logs api --tail 200 | grep -E "Error|UndefinedColumn|does not exist"
   ```

2. 对比数据库当前迁移版本与代码所需 head：

   ```bash
   docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT version_num FROM alembic_version"'
   docker compose exec api python -m alembic current     # 应与上一条一致
   ```

   同时核对 `backend/alembic/versions/` 下最新迁移的 `revision` 是否为 head。

### 修复

对恢复后的库执行一次数据库迁移（幂等，可重复执行）：

```bash
bash scripts/migrate.sh
# 等价： docker compose run --rm api python -m scripts.migrate
# 其内部按库状态决策：有 alembic_version → alembic upgrade head
```

完成后重新验证：

```bash
docker compose exec api python -m alembic current   # 应显示 head 版本号
```

回到前端刷新页面即可。

### 预防

- **恢复 / 迁移数据后必须先跑 `migrate.sh`**，再访问页面。
- VPS 升级走 `bash scripts/upgrade.sh`（内部已含备份 + 迁移），不要只 `git pull` 后直接 `up compose up`。
- 生产升级与本地恢复库升级使用同一套 Alembic 迁移，两端 head 需保持一致。

---

## 八、升级后功能未生效排查（代码未提交 / 未拉到）

### 现象

在服务器执行 `bash scripts/upgrade.sh` 后，页面仍是旧行为（筛选条件、时间口径、新增字段等不生效），
或数据库缺少本次发布新增的列 / 表。

### 根因

`upgrade.sh` 用 `git pull --ff-only` 拉取**远程已有提交**。若开发机的改动只存在于本地工作区
（未 `git commit` / 未 `git push`），VPS 拉到的是上一次提交，自然还是旧代码——即使执行了
`docker compose build` 重建镜像也一样（镜像只是把仓库里的旧代码重新烘焙了一遍）。

### 排查步骤

```bash
# 1) 服务器当前代码版本：与开发机 git log -1 --oneline 对比是否一致
git log -1 --oneline

# 2) 是否有远程提交未拉取：出现 "behind" 即说明远程有新提交
git fetch origin && git status -sb

# 3) 容器内实际版本号：判断镜像是否已重建到目标版本
sudo docker compose exec -T api python -c "from app.core.config import settings; print(settings.APP_VERSION)"

# 4) 数据库迁移版本：应等于代码 backend/alembic/versions/ 下的 head
sudo docker compose exec -T api python -m alembic current
```

### 修复

```bash
# 开发机：先把本地改动提交并推送（务必先推送，VPS 才拉得到）
git add -A && git commit -m "..." && git push origin main --tags

# 服务器：重走一遍升级（内部含 git pull → 重建镜像 → 迁移 → 重启 → 打印版本）
bash scripts/upgrade.sh
```

### 预防

- 每次发布**先在开发机 `git push`**，再到 VPS 执行 `upgrade.sh`；不要在服务器上直接改代码。
- 升级收尾务必核对三处一致：`git log -1`、容器内 `APP_VERSION`、`alembic current`。
- **只 `git pull` + `docker compose up -d` 不会让代码改动生效**：镜像已烘焙代码，必须重建
  （`docker compose build` 或 `docker compose up -d --build`），或直接走 `upgrade.sh`。
- 端口占用 / 构建失败等中断后重试是安全的：`upgrade.sh` 各步骤幂等，可重复执行。

---

## 九、把生产备份导入本地开发库（Windows / WSL-Kali）

把 VPS 的备份产物（`backups/anchors/...` 或 `backups/snapshots/...`）导入**本地开发库**，用真实数据做开发/复现。
与「六、更换 VPS」的区别：**只写数据、不起容器栈**，目标是由 DBngin 托管的 `vulnplatform` 开发库
（本地环境搭建见 `docs/LOCAL_DEV_SETUP.md`）。两方案选一个即可，也可以「Windows 导入 + WSL 验证」组合。

### 9.1 先看清备份里有什么（两方案共用）

以本机实测的 `backups/anchors/2026/09/20260910_101126/` 为例：

| 文件 | 内容 | 实测 |
|---|---|---|
| `db.sql.zst` | `pg_dump --clean --if-exists` 纯文本 SQL（UTF8） | 293 KB → 解压 3.2 MB / 6 206 行 / 30 张表 / 30 段 `COPY` |
| `storage.tar.zst` | `/app/storage` 整卷（`uploads/` + `previews/` + 导出产物） | 1.8 GB |
| `MANIFEST.json` | `git_commit` / `db_sha256` / `storage_sha256` / `status=complete` | `git_commit=2f0fa7e` |

落库前先做三项检查（**落库本身是破坏性的**：会清空目标库）：

```powershell
# 1) 完整性：文件 SHA256 应与 MANIFEST.json 的 db_sha256 一致（实测一致）
(Get-FileHash .\backups\anchors\2026\09\20260910_101126\db.sql.zst -Algorithm SHA256).Hash.ToLower()

# 2) 备份的代码版本 vs 本地：备份落后就 git pull（避免入库后页面缺字段/缺功能）
git rev-parse --short HEAD        # 本地 9f56530（2.20.0）／备份 2f0fa7e

# 3) 备份库的迁移版本 → 决定恢复后要补几个迁移
#    实测：dump 内 alembic_version = d6e7f8a9b0c1，本地 head = e1f2a3b4c5d6 → 需补 5 个迁移
```

> 备份库结构落后于本地代码是**常态**：恢复完必须补迁移，否则新功能页面 500（根因与「七」相同）。

**格式转换（按需）**：备份是纯文本 SQL 的压缩流，`db.sql.zst` / `db.sql.gz` / `db.sql` 三者内容等价，
脚本按扩展名选解压器，因此「转换」只是换个封装，不涉及 dump 内容：

```powershell
# .zst → .sql（Windows，zstd 自写文件，最稳）
zstd -d -f -o db.sql db.sql.zst
# .sql → .zst（把手工/旧格式 SQL 重新压成脚本可识别的产物名）
zstd -q -T0 -o db.sql.zst db.sql
# .gz → .sql：Windows 无 gunzip 时借 WSL/Git-Bash
wsl -d kali-linux gunzip -c /mnt/e/GitRepo/Talos/backups/.../db.sql.gz > "$env:TEMP\db.sql"
```

> 转换时**不要让 PowerShell 管道串联两个压缩器**（`gunzip -c a.gz | zstd -o b.zst`）：PowerShell 会按文本
> 解码中间流，产物必然损坏。分两步走（先落盘 `.sql`，再压缩），或把整条命令交给 `wsl bash -lc '...'` 执行。

### 9.2 方案一：Windows + PowerShell 7（原生，不依赖 WSL / Docker）

工具链：

| 工具 | 用途 | 获取方式 / 本机实测 |
|---|---|---|
| `zstd` | 解压 `db.sql.zst`（**必需**） | `winget install --id Facebook.ZStandard -e`（装完重开终端）；本机未装 → 也可用 9.3 的解压回退 |
| `psql` 16 | 导入 SQL | DBngin 自带：`%LOCALAPPDATA%\com.tinyapp.DBngin\Binaries\postgresql\16.14\bin\psql.exe`（实测 16.14，支持新版 `pg_dump` 的 `\restrict`） |
| `tar`（bsdtar） | 解 `storage.tar.zst` | Windows 自带（实测 3.8.8，含 `libzstd/1.5.7`，**原生支持 `.tar.zst`**，无需额外装 zstd） |

```powershell
# 0) 路径常量（按机器调整）
$BK   = 'E:\GitRepo\Talos\backups\anchors\2026\09\20260910_101126'
$PSQL = "$env:LOCALAPPDATA\com.tinyapp.DBngin\Binaries\postgresql\16.14\bin\psql.exe"
$PG   = @('-h','127.0.0.1','-U','vulnplatform','-d','vulnplatform')

# 1) 解压 db（务必用 -o 让 zstd 自己写文件；不要用 `zstd -dc x.zst > x.sql` 或管道——
#    PowerShell 默认按文本处理，二进制会被解码/换行转换破坏）
zstd -d -f -o "$env:TEMP\db.sql" "$BK\db.sql.zst"

# 2) 清空目标库（DROP SCHEMA public CASCADE 必需：dump 只 DROP 它自己导出的对象，
#    残留的 alembic_version / 表会与导入内容冲突）
& $PSQL @PG -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3) 导入（ON_ERROR_STOP=1：任何一步失败立即中断，避免半库状态）
& $PSQL @PG -v ON_ERROR_STOP=1 -q -f "$env:TEMP\db.sql"

# 4) 校验（实测：30 表 / 261 漏洞 / 108 报告 / alembic d6e7f8a9b0c1）
& $PSQL @PG -c "SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema='public') AS tables, (SELECT version_num FROM alembic_version) AS alembic, (SELECT count(*) FROM vulns) AS vulns, (SELECT count(*) FROM reports) AS reports"

# 5) 补迁移到本地 head（VP_DEBUG=1 免 SECRET_KEY 强校验，与 dev.ps1 同口径）
cd E:\GitRepo\Talos\backend
$env:VP_DEBUG='1'; $env:VP_DATABASE_URL='postgresql+asyncpg://vulnplatform@127.0.0.1:5432/vulnplatform'
.\.venv\Scripts\python.exe -m scripts.migrate     # 实测输出 5 条 Running upgrade ... → e1f2a3b4c5d6

# 6) storage（可选：1.8 GB，只做业务开发可跳过——DB 是唯一必需项）
& "$env:SystemRoot\system32\tar.exe" -xf "$BK\storage.tar.zst" -C E:\GitRepo\Talos\backend\storage

# 7) 验证：起 dev 栈（前端 27014 / 后端 27015）后用原 admin 账号登录
pwsh -NoProfile -ExecutionPolicy Bypass -File E:\GitRepo\Talos\dev.ps1
```

要点：

- **本地 DBngin 连接是 `trust`**（`dev-database/postgre/pg_hba.conf:119` 的 `host all all 127.0.0.1/32 trust`）：连 `127.0.0.1` **不需要密码**，`.env` 的 `POSTGRES_PASSWORD` 只服务容器部署。
- **目标库编码必须是 UTF8**（本机 `vulnplatform` 实测 UTF8；集群默认库 `postgres` 是 WIN1252）。中文数据导入失败时先按 `LOCAL_DEV_SETUP.md` 用 `TEMPLATE template0 ENCODING 'UTF8'` 重建库。
- **storage 解到 `backend\storage`**（`STORAGE_DIR` 默认 `storage`，而 dev 后端从 `backend/` 启动），不要解到仓库根。
- 只想要「几张表 + 中文数据」做联调时，可以只用步骤 1~5；`storage` 常用于复现导入解析/报告导出的附件问题。

常见问题：

| 现象 | 原因与处理 |
|---|---|
| `zstd : 无法将“zstd”项识别为 cmdlet…` | 未安装或装完未重开终端；`winget install --id Facebook.ZStandard -e` 后重开 PowerShell；或用 9.3 的 WSL 解压回退 |
| `invalid byte sequence for encoding "UTF8"` | ① 目标库不是 UTF8（重建库并指定 `TEMPLATE template0 ENCODING 'UTF8'`）；② 在**中文（GBK）控制台**用 `-c` 传了含中文的 SQL：改用纯 ASCII 的 `-c`，或把 SQL 写进 UTF-8 文件用 `-f`，或先 `chcp 65001` |
| `\restrict: invalid command` | 客户端 psql 过旧（`\restrict` 需 psql ≥ 16.10 / 15.14 / 17.6，新版 `pg_dump` 会用它包裹声明）；升级 psql 客户端（本机 16.14 实测正常） |
| 导入中报 `relation … already exists` 或 `alembic_version` 冲突 | 漏了步骤 2 的 `DROP SCHEMA public CASCADE`，或目标库不是空库 |
| 页面 500 `column … does not exist` | 漏了步骤 5 的补迁移（见「七」） |
| 解压后 SQL 比备份大很多（293 KB → 3.2 MB） | 正常：纯 SQL 文本压缩比通常 10:1 以上 |
| `tar` 解包报 owner/权限告警 | 备份里的条目属主是容器内 root；Windows 侧可忽略，WSL/Git-Bash 侧加 `--no-same-owner` |

### 9.3 方案二：WSL-Kali（远程连本机 PG + restore 脚本）

本机环境实测（`.wslconfig` 为 `[wsl2] networkingMode=mirrored`）：

| 能力 | 实测结果 |
|---|---|
| 工具链 | `/usr/bin/zstd` 1.5.7、`/usr/bin/psql` 18.1、`/usr/bin/docker` 29.4.2、`/usr/bin/tar` |
| 连通本机 PG | **镜像网络下 WSL 的 `127.0.0.1:5432` 直通 Windows 宿主 DBngin**：`pg_isready` 返回 `accepting connections`，`psql postgresql://vulnplatform@127.0.0.1:5432/vulnplatform` 可查（无需查宿主 IP、无需改 `listen_addresses` / `pg_hba` / 防火墙） |
| 仓库访问 | 直接 `cd /mnt/e/GitRepo/Talos`（无需在 WSL 内再克隆） |

**脚本选择**：`scripts/restore.sh` 面向 docker compose 栈（`docker compose exec postgres` + 卷内 storage），
目标只能是容器库；本机 DBngin 不是容器，故用 **`scripts/restore-local.sh`**——它复用 `backup-common.sh` 的产物定位与
解压能力，去掉 docker 依赖，改为对**任意 DSN** 恢复，并对非回环目标加 `--yes` 破坏性护栏。

```bash
# 0) 连通性（应先输出 accepting connections；不通见下表）
pg_isready -h 127.0.0.1 -p 5432

# 1) 一键恢复（清空 public schema → 流式导入 db.sql.zst；实测 1.3 s 完成）
cd /mnt/e/GitRepo/Talos
bash scripts/restore-local.sh backups/anchors/2026/09/20260910_101126 \
     --dsn postgresql://vulnplatform@127.0.0.1:5432/vulnplatform

# 1b) 需要同时恢复上传文件时加 --storage-dir（1.8 GB，写入 /mnt/e 较慢，可留给方案一）
bash scripts/restore-local.sh backups/anchors/2026/09/20260910_101126 \
     --dsn postgresql://vulnplatform@127.0.0.1:5432/vulnplatform \
     --storage-dir /mnt/e/GitRepo/Talos/backend/storage

# 2) 校验（与方案一同一口径）
psql postgresql://vulnplatform@127.0.0.1:5432/vulnplatform \
  -c "SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema='public') AS tables, (SELECT version_num FROM alembic_version) AS alembic, (SELECT count(*) FROM vulns) AS vulns"

# 3) 补迁移：后端 venv 在 Windows 侧，按 9.2 步骤 5 执行（不要在 WSL 里用 /mnt/e 上的 Windows venv 跑 Python）
```

**解压回退**（Windows 侧没装 `zstd` 时，借 WSL 解压、产物落回 Windows 目录，全程二进制安全）：

```powershell
wsl -d kali-linux zstd -d -f -o "C:\Users\<你>\AppData\Local\Temp\db.sql" "E:\GitRepo\Talos\backups\anchors\2026\09\20260910_101126\db.sql.zst"
# 随后回到 9.2 步骤 2 继续（DROP SCHEMA → psql -f）
```

常见问题：

| 现象 | 原因与处理 |
|---|---|
| `pg_isready ... no response` | ① DBngin 里 PostgreSQL 未 Start；② `.wslconfig` 不是 `networkingMode=mirrored`（默认 NAT）：改用宿主 IP 连接 —— `ip route show default \| awk '{print $3}'`（或 `/etc/resolv.conf` 的 nameserver），并按下面两条补配置 |
| 报 `no pg_hba.conf entry for host "172.x.x.x"` | NAT 模式下 `pg_hba.conf` 只放行 `127.0.0.1/32` 与 `::1/128`：在 `dev-database/postgre/pg_hba.conf` 追加 `host all all 172.16.0.0/12 scram-sha-256`，并在 `postgresql.conf` 设 `listen_addresses = '*'`；改完 `psql -h 127.0.0.1 -U postgres -c "select pg_reload_conf()"`（或在 DBngin 里重启服务） |
| NAT 模式下仍连不上（无入站放行） | Windows 防火墙放行 TCP 5432（WSL 的 vEthernet 通常属 Public 配置文件，需 `-Profile Any`）：`New-NetFirewallRule -DisplayName "PostgreSQL (WSL)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 -Profile Any`。**不想动 DBngin 配置**可用端口转发：`netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=5433 connectaddress=127.0.0.1 connectport=5432`，WSL 连宿主 `5433`（此时服务端看到的来源是 `127.0.0.1`，天然命中 `trust` 规则） |
| `zstd: command not found` | `sudo apt install -y zstd`（本机已装 1.5.7） |
| 脚本报「目标是远程库…确认后请追加 --yes」 | 破坏性护栏：DSN 主机不是 `127.0.0.1` / `localhost` / `::1` 时必须显式 `--yes`，避免误清生产库 |
| 在 `/mnt/e` 下解包 storage 极慢 | drvfs 跨文件系统 + 1.8 GB，属正常现象；属主告警可忽略（脚本内已用 `tar xf - --no-same-owner`），或干脆把 storage 留给 Windows 侧解包（9.2 步骤 6） |

### 9.4 两方案收尾（共同）

1. 补完迁移后 `alembic current` 应为**本地 head**（当前 `e1f2a3b4c5d6`）；
2. 启动 dev 栈（`dev.ps1`）→ 用**原 admin 账号**登录验证数据完整；页面报错先看「七、恢复后页面 500 排查」；
3. 本地库被真实数据覆盖后，`vulnplatform_test` / `vulnplatform_e2e` **不受影响**（测试库独立，见 `LOCAL_DEV_SETUP.md`），跑测试仍按 `scripts/test.ps1` 的既有口径。

---

## 十、健康探针与后台任务恢复（2.20.3 / P0-3）

### 10.1 三档健康探针

| 路径 | 语义 | 判据 |
|---|---|---|
| `/api/health` | 兼容旧探针 | 恒 200，只表示进程在跑（不查依赖） |
| `/api/health/live` | 存活探针 | 恒 200；**不查依赖**（依赖故障时应重启前先排障，而非被编排杀掉） |
| `/api/health/ready` | 就绪探针 | 逐项返回依赖状态；任一**必需**依赖失败返回 **503**，可选依赖失败不影响状态码 |

依赖分级：**PostgreSQL 恒为必需**；队列启用时（`VP_DISABLE_QUEUE=0`）**Redis 与 arq worker 心跳
同为必需**；**Gotenberg 为可选**（不可用只降级「PDF 导出不可用」）。
响应形如 `{"status":"ready","checks":{"database":{"ok":true,"required":true},"redis":{...},"worker":{...},"gotenberg":{"ok":false,"required":false,"reason":"连接超时"}}}` ——
只含依赖名、`ok` 与归类后的原因文案，**不含 DSN / 凭据 / 内网地址**。

worker 心跳键为 `arq:health-check`（worker 每 30s 续期，TTL 61s）：探针读到该键才认为有存活 worker，
故「Redis 通但 worker 全挂」同样会返回 503。

```bash
curl -s -o /dev/null -w 'health=%{http_code}\n'  http://127.0.0.1/api/health
curl -s http://127.0.0.1/api/health/ready | python3 -m json.tool
```

### 10.2 后台任务租约与自动恢复

导入解析与报告导出均带**租约 / 心跳 / 尝试次数 / 退避 / 死信**字段（`attempts`、`last_heartbeat`、
`lease_until`、`next_retry_at`、`dead_letter_reason`），口径见 `app/services/task_lifecycle.py`：

- 任务启动即写租约（默认 600s），长步骤前续租；worker 崩溃后记录停在 `running` / `parsing`，
  **超租约即被判为孤儿任务**，在 API 启动时回收一次，并：
  - 未达最大次数（默认 3）→ 回到排队态 + 指数退避（`30s × 2^n`，封顶 1h）后重试；
  - 已达上限或属永久错误（文件损坏 / 数据缺失等）→ 置 `failed` 并在 `dead_letter_reason` 保留原因。
- 兜底扫描：worker 侧 cron 每 5 分钟；无队列形态（`VP_DISABLE_QUEUE=1`）由 API 进程内每 5 分钟一次。
- 可调参数：`VP_TASK_LEASE_SECONDS`（须显著大于单次最长任务耗时）、`VP_TASK_MAX_ATTEMPTS`、
  `VP_TASK_BACKOFF_SECONDS`。
- 幂等：任务重试不会重复生成章节 / 漏洞 / 复测轮次 / 报告文件（导出按状态短路，通知按幂等键抢占，
  报告导入按批次状态机与 `export_jobs.dedup_key` 去重）。

```bash
# 查看最近的导出任务与重试/死信状态
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT id,report_id,status,attempts,lease_until,next_retry_at,left(dead_letter_reason,40) AS reason FROM export_jobs ORDER BY id DESC LIMIT 10"'
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT id,filename,status,attempts,lease_until,next_retry_at,left(dead_letter_reason,40) AS reason FROM import_batches ORDER BY id DESC LIMIT 10"'
```

### 10.3 从前端报错定位后端日志（request_id）

每次响应都带 `X-Request-Id` 头（复用调用方传入值，否则服务端生成 12 位十六进制）；
后端 `app.*` 日志统一形如 `... [rid=<request_id>] app.api.v1.xxx: ...`，4xx/5xx 另有一条
`请求失败 rid=... method=... path=... status=...` 汇总行。后台任务无 HTTP 上下文，关联字段为
消息里的 `job_id=` / `batch_id=`。

```bash
# 用界面响应头里的 rid 直接过滤日志
sudo docker compose logs --tail 2000 api | grep 'rid=<粘贴的 request_id>'
sudo docker compose logs --tail 2000 api | grep 'job_id=<导出任务ID>'
```

### 10.4 可选：启用 pg_trgm 前后通配符索引（P0-4）

列表关键词走 `%keyword%`（B-tree 无法命中）。基准实测（10 万漏洞、关键词具选择性）：
`P95 43.5ms → 5.3ms`，执行计划由 `Seq Scan` 变为 `Bitmap Index Scan on ix_trgm_vulns_title`。
该脚本幂等、可先试运行；需要 `CREATE EXTENSION pg_trgm` 权限（compose 的 `postgres` 用户满足）。

```bash
sudo docker compose run --rm api python -m scripts.enable_trgm_indexes --dry-run
sudo docker compose run --rm api python -m scripts.enable_trgm_indexes
```

---

## 附：常用排查

> VPS 上 docker 命令需 `sudo`（与 `scripts/upgrade.sh` 一致）；本地开发环境去掉 `sudo`。
> 以下命令均假设当前目录为仓库根（`docker-compose.yml` 所在处）。

### 服务与版本

```bash
sudo docker compose ps                                        # 各服务状态与端口
sudo docker compose logs -f api --tail 200                    # 后端日志（跟踪）
sudo docker compose logs --tail 200 worker                    # worker 日志（导入解析 / 报告导出在其执行）
sudo docker compose exec -T api python -c "from app.core.config import settings; print(settings.APP_VERSION)"
sudo docker compose exec -T api python -m alembic current     # 当前迁移版本
```

### 接口连通性（绕开浏览器）

```bash
# 前端 nginx 已把 /api 同源反代到后端；未对外暴露 8000 端口时用该入口探测
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/api/v1/imports/template

# 取登录令牌后调用任意接口排查（首次登录的账号需先改密码）
TOKEN=$(curl -s -X POST http://127.0.0.1/api/v1/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=<口令>' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1/api/v1/auth/me
```

### 数据库直查

```bash
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT id,title,status FROM reports ORDER BY id DESC LIMIT 5"'
sudo docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT version_num FROM alembic_version"'
```

### 文件与磁盘

```bash
sudo docker compose exec -T api ls -l /app/storage/exports/     # 报告导出产物
sudo docker compose exec -T api ls -l /app/storage/backups/     # 数据维护脚本产生的备份
bash scripts/disk-usage.sh                                     # 磁盘占用概览
sudo docker system df                                           # 镜像 / 卷 / 缓存占用
sudo docker builder prune --filter "until=168h" -f              # 清理 7 天前的构建缓存
```

> **磁盘排查必须「双视角」**（2026-08-31 VPS 事故复盘固化）：`du` 只能定位到目录级；Docker 的**构建缓存**以碎片 blob 形式藏在 `/var/lib/containerd` 内容库里，`du` 无法归因 —— 必须同时看 `docker system df` 的 **Build Cache / RECLAIMABLE** 一栏。当时 `du` 统计 39G 而 `df` 为 34G（差额为 containerd 快照硬链接被重复统计），最终根因是 BuildKit 缓存累积 **12.95GB（可回收 12.47GB，ACTIVE=0）**，`docker builder prune -af` 一次回收。
> **升级流程已内置回收**：`scripts/upgrade.sh` 在重建镜像后会执行 `docker builder prune`，故正常升级不会让缓存无限累积；只有手工 `docker compose build` 时才需自行清理。
> 其他易涨项与处置：`/var/log`（建议配 journald `SystemMaxUse`）、`/app/storage/exports`（导出产物，可定期清理过期文件）、过期备份（锚点保留 3 份由 `backup.sh` 自动裁剪）、snap/apt/Homebrew 缓存（定期维护）。

### 只重建单个服务

```bash
sudo docker compose up -d --build api worker    # 仅后端（导入解析 / 报告导出在 worker，务必一并重建）
sudo docker compose up -d --build frontend      # 仅前端
```

> 导入解析（`parse_import_task`）与报告导出（`export_report_task`）由 **worker** 容器执行，
> 只重建 `api` 不会让解析 / 导出相关的代码改动生效。
