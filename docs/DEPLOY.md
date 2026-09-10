# Talos 部署与运维手册

面向在 VPS 上用 Docker 部署、升级、备份与迁移 Talos 的操作指引。生产采用
`docker-compose.yml` 编排的 **PostgreSQL**（不是本地开发用的 SQLite `dev.db`）。

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
   ```

   > `docker-compose.yml` 对 `VP_SECRET_KEY` / `POSTGRES_PASSWORD` 使用了 `:?` 强校验，
   > 未设置会直接拒绝启动。仓库内 `.env` 若已配置好可直接复用。

2. 一键启动：

   ```bash
   docker compose up -d --build
   ```

   表结构、内置角色 / 字典、admin 账号都会自动创建，**无需手工初始化数据库，也无需清除任何 SQLite 数据**
   （`dev.db` 仅本地开发使用，生产不加载）。

3. 取初始 admin 口令（若 `.env` 未设 `VP_INITIAL_ADMIN_PASSWORD`，随机生成且仅打印一次）：

   ```bash
   docker compose logs api | grep -i "初始密码"
   ```

4. 访问：前端 `http://<VPS_IP>`（80 端口）。前端 nginx 已把 `/api` 同源反代到后端，
   通常无需对外暴露 8000 端口，也无需额外配置 CORS。

---

## 二、是否需要清除 SQLite 数据？

不需要。

- 生产用 PostgreSQL，`backend/dev.db`（SQLite）只在本地 `dev.sh` / `dev.ps1` 开发时使用，生产完全不读它。
- 首次部署时 postgres 是全新空卷，天然干净。
- 仅当你想丢弃某个**旧 `pg_data` 卷**里的历史数据、重新开局时才需清库：

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

### 3.4 版本相关的一次性数据维护（按需执行）

部分版本除代码与结构迁移外，还需对**存量数据**做一次性规整。已内置脚本的版本见下表；
命令须在 `upgrade.sh` 完成之后执行（新镜像已生效，容器内才有对应脚本）。

| 版本 | 脚本 | 用途 |
| --- | --- | --- |
| 2.12.2 | `scripts.fix_retest_section_dup` | 剥离存量报告章节正文尾部内嵌的「复测详情」副本（见下） |
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

## 五、备份

在运行中的服务器、仓库根目录执行：

```bash
bash scripts/backup.sh
```

产物在 `backups/<时间戳>/`：

- `db.sql.gz`：PostgreSQL 逻辑备份（`pg_dump`，与镜像 / DB 版本无关，可跨机恢复）
- `storage.tar.gz`：`storage_data` 卷中的上传文件

建议用 cron 定期执行并把 `backups/` 同步到异地存储。`backups/` 已加入 `.gitignore`，不会误入库。

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

   脚本会：起 postgres → 导入 `db.sql.gz` 到空库 → 起 api 并解包 `storage.tar.gz` 到 `/app/storage` → 拉起全部服务。

4. 用原 admin 账号登录验证数据完整。

要点：

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

后端的 `create_all` 只会补**缺失的表**，不会给已有表加列；`_migrate_lightweight`
仅对 SQLite（本地开发库）生效，对 PostgreSQL 无效。因此缺列必须靠 Alembic 补齐。

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

### 只重建单个服务

```bash
sudo docker compose up -d --build api worker    # 仅后端（导入解析 / 报告导出在 worker，务必一并重建）
sudo docker compose up -d --build frontend      # 仅前端
```

> 导入解析（`parse_import_task`）与报告导出（`export_report_task`）由 **worker** 容器执行，
> 只重建 `api` 不会让解析 / 导出相关的代码改动生效。
