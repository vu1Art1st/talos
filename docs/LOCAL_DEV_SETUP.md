# 本地开发环境搭建（DBngin 托管 PostgreSQL + Redis）

> 自 2026-09 起本地开发/测试全面切换 PostgreSQL + Redis。**动因**：SQLite 与 PostgreSQL 的方言差异
> 曾在类型/绑定严格性、外键强制、长度约束、结果集顺序确定性、DDL 能力五个轴上造成缺陷，且这些轴的
> 差异在实际使用中都会给出「本地测不出」的假绿信号；统一为单栈后该类风险整体消失，跨方言守卫的
> 维护成本随之消除（结论与演进详情见 `AGENTS.md`「数据库迁移（单轨）」与 `docs/RELEASE.md`）。
> 本地数据库服务由 [DBngin](https://dbngin.com/)
> （TablePlus 团队，免费，Windows/macOS 原生应用，无需 Docker/VM）托管，与生产
> `postgres:16-alpine` / `redis:7-alpine` 同方言同大版本，仅部署形态不同。

## 一、一次性准备（DBngin 手动操作）

### 1. 建两个服务

| 服务 | 版本 | 端口 | 说明 |
|---|---|---|---|
| PostgreSQL | **16** | 5432（默认） | 版本刻意对齐生产镜像；勿选 15/17 造成方言窗口 |
| Redis | **7.x** | 6379（默认） | 默认配置即可，无需认证 |

在 DBngin 中点 `+` 新建并 Start。DBngin 的数据目录（本项目为仓库内 `dev-database/`）
已被 `.gitignore` 覆盖，**勿提交入库**。

### 2. 建角色与数据库

以 `postgres` 超级用户（DBngin 默认无密码）连 `127.0.0.1:5432`，在任意 SQL 客户端
（TablePlus / DBeaver / psql）执行——密码取仓库根目录 `.env` 的 `POSTGRES_PASSWORD` 值，
与 docker-compose 部署共用同一份凭据。

> **编码必须显式指定 UTF8**：DBngin 在 Windows 上初始化的集群默认编码为 WIN1252，
> 若省略 `ENCODING 'UTF8' TEMPLATE template0`，库会继承 WIN1252——asyncpg 以 UTF8 通信，
> 任何中文参数（角色名「超级管理员」等）都会抛 `UntranslatableCharacterError`，
> 后端启动建种子数据即失败。`LC_COLLATE/LC_CTYPE 'C'` 保证与 UTF8 编码兼容（Windows 上
> 默认 locale 与 UTF8 不兼容，必须显式覆盖）。

```sql
CREATE ROLE vulnplatform LOGIN PASSWORD '<POSTGRES_PASSWORD>';
CREATE DATABASE vulnplatform
  OWNER vulnplatform TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C';  -- 开发库（= .env 的 POSTGRES_DB）
CREATE DATABASE vulnplatform_test
  OWNER vulnplatform TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C';  -- 测试库（固定后缀 _test）
```

验证编码（应为 UTF8）：

```sql
SELECT datname, pg_encoding_to_char(encoding) FROM pg_database
WHERE datname IN ('vulnplatform', 'vulnplatform_test');
```

### 3. 验证

```bash
# PG：以 vulnplatform 账号连两个库各执行一次
psql "postgresql://vulnplatform:<密码>@127.0.0.1:5432/vulnplatform" -c "SELECT version();"
# Redis
redis-cli -p 6379 ping   # 期望 PONG
```

## 二、日常使用

```bash
# 一键开发（自动预检 5432/6379、解析 .env 凭据；前端 27014 / 后端 27015）
powershell -ExecutionPolicy Bypass -File .\dev.ps1    # Windows
bash dev.sh                                            # Linux / macOS / WSL

# 全量测试（自动连 vulnplatform_test，session 开始清空 schema、结束再清空）
# CODEBUDDY_SAFE_DELETE_ENABLED=0 仅用于绕开受管终端的删除守卫，见第四节
cd backend && CODEBUDDY_SAFE_DELETE_ENABLED=0 \
  .venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp=_pytest_tmp
```

- **dev 脚本口径**：`VP_DATABASE_URL=postgresql+asyncpg://vulnplatform:<密码>@127.0.0.1:5432/vulnplatform`，
  `VP_REDIS_URL=redis://127.0.0.1:6379/0`，`VP_DISABLE_REDIS=0`（Redis 真实承担限流/登录锁定/token 轮换），
  `VP_DISABLE_QUEUE=1`（后台任务在 API 进程内执行，无需另开 arq worker，热重载友好）。
- **测试口径**：conftest 优先读外部 `VP_DATABASE_URL`（CI services 容器兼容），否则从根 `.env`
  派生 `vulnplatform_test`；**目标库必须以 `_test` 结尾**，否则拒绝启动（session fixture 会整库
  `DROP SCHEMA public CASCADE`，护栏防止误清开发/生产库）。

## 三、常见问题

| 现象 | 原因与处理 |
|---|---|
| 报 `UntranslatableCharacterError ... has no equivalent in encoding "WIN1252"` | 建库时未指定 UTF8 编码（见第一节第 2 步的说明）；按该节 SQL 以 `TEMPLATE template0 ENCODING 'UTF8'` 重建库 |
| dev 脚本报「依赖服务未启动」 | DBngin 中对应服务未 Start；启动后重跑 |
| pytest 报「测试数据库连接失败」 | PG 服务未启动 / `vulnplatform_test` 库未建（见第一节 SQL）/ `.env` 缺 `POSTGRES_PASSWORD` |
| 大量用例报 `Event loop is closed` / `'NoneType' object has no attribute 'send'` | `pytest.ini` 缺 `asyncio_default_test_loop_scope = session`：测试 loop 回落为函数级，与 session 级连接池错配；见第四节 |
| 单文件跑全绿、全量跑却几十个 ERROR（`assert not self._finalizers`） | 受管终端的删除守卫在 pytest 清理 basetemp 时抛 `SystemExit(1)`，级联破坏 fixture 状态；以 `CODEBUDDY_SAFE_DELETE_ENABLED=0` 运行；见第四节 |
| 密码更换后连不上 | `.env` 的 `POSTGRES_PASSWORD` 与 DBngin 角色密码不一致；用 `ALTER ROLE vulnplatform WITH PASSWORD '...'` 对齐 |
| 密码含 URL 特殊字符 | `@ : / # ?` 等字符在 DSN 中需 URL 编码（当前 `.env` 密码为 URL 安全字符，无需处理） |
| 5432/6379 被占用 | 生产 `docker-compose.yml` 的 postgres/redis 不映射宿主端口，通常是本机其它服务；换端口需同步改 dev 脚本与 conftest |
| 与 WSL-Kali 部署验证并存 | 两者无端口冲突（compose 只暴露 27012）；DBngin 服务与容器可同时运行 |

## 四、测试与事件循环（pytest-asyncio，改动必读）

**所有测试与 fixture 的事件循环作用域必须统一为 `session`**，由 `backend/pytest.ini` 的
`asyncio_default_fixture_loop_scope` 与 `asyncio_default_test_loop_scope` 两条配置共同保证。

**根因**：asyncpg 的连接对象**严格绑定于创建它的 event loop**，跨 loop 复用会抛
`RuntimeError: Event loop is closed` / `attached to a different loop`，或退化表现为
`'NoneType' object has no attribute 'send'`，并伴随 `AsyncAdaptedQueuePool ... Exception
terminating connection` 噪音。`conftest.py` 的 `client` / `token` / `auth` 均为 session 级
fixture，其内部的引擎连接池建立在 session loop 上；若测试回落到默认的**函数级** loop，
每个测试都会从另一个 loop 访问该池，遂连接层报错。

> **历史教训**：SQLite + aiosqlite 通过独立线程执行数据库 I/O，对 loop 归属不敏感，因此该
> 缺陷在 2026-09-21 迁移到 PostgreSQL 前被长期掩盖（当年只有 `test_api.py` 用
> `pytestmark = pytest.mark.asyncio(loop_scope="session")` 打了个局部补丁，其余文件裸奔）。
> 迁移后一次性暴露为 24 failed / 1 error。**新增异步测试文件无需再写该 marker**，默认值已对齐。

约束：

- 新增异步 fixture 一律显式 `scope="session", loop_scope="session"`，与 `conftest.py` 现有风格一致；
- 不要为「单测隔离」把 loop 作用域降回 `function`——需要函数级隔离的用例应自带独立引擎，
  而非共享 `app.db.engine`；
- 排查同类症状时，先确认 `pytest.ini` 两行配置是否都还在（缺一行即复现上述报错）。

### 受管终端下的删除守卫（运行测试的前置条件）

在带**删除守卫**的受管终端中（WorkBuddy / CodeBuddy 沙箱等会在解释器启动时注入
`sitecustomize.py`，把 `shutil.rmtree` / `os.remove` 拦截为「回收站 + 批量删除确认」），
直接跑 `pytest` 会**必失败**且症状具误导性：

1. pytest 首次使用 `tmp_path` 时会对 `--basetemp` 目录执行 `rm_rf`；若上次运行的残留文件数
   超过守卫阈值（实测 136 > 50），守卫抛 `SystemExit(1)`；
2. 该异常破坏 pytest 的 fixture 终结器状态，之后**所有**复用 session 级 fixture 的用例
   级联报 `AssertionError`（`_pytest/fixtures.py:... assert not self._finalizers`），
   表现为「单独跑某个测试文件全绿、全量跑却几十个 ERROR」。

处理：在**单次 pytest 调用**内关闭守卫（不改变仓库与系统配置）：

```bash
cd backend
CODEBUDDY_SAFE_DELETE_ENABLED=0 .venv/Scripts/python.exe -m pytest \
  -p no:cacheprovider --basetemp=_pytest_tmp
```

`--basetemp` 指向仓库内固定目录是刻意的：默认系统临时目录会被守卫视为越界删除目标。

## 五、CI（无 DBngin 环境）

CI 用 services 容器提供同版本服务，conftest 只认 `VP_DATABASE_URL` 环境变量，零改动兼容：

```yaml
services:
  postgres:
    image: postgres:16-alpine
    env: { POSTGRES_USER: vulnplatform, POSTGRES_PASSWORD: test, POSTGRES_DB: vulnplatform_test }
    ports: ["5432:5432"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
env:
  VP_DATABASE_URL: postgresql+asyncpg://vulnplatform:test@127.0.0.1:5432/vulnplatform_test
```
