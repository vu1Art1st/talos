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

---

## 四、备份

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

## 五、更换 VPS：平滑迁移不丢数据

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

---

## 附：常用排查

```bash
docker compose ps                 # 各服务状态
docker compose logs -f api        # 后端日志
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'   # 查看表
docker compose exec api python -m alembic current   # 当前迁移版本
```
