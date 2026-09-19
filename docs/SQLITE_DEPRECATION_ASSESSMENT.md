# SQLite 废弃与 PostgreSQL + Redis 全面迁移评估

> 评估日期：2026-09-19（同日修订：本地 PG/Redis 改用 DBngin 原生托管，不走 Docker）
> 背景：本地开发已基本不再通过 `dev.ps1` 使用 SQLite，主要在 WSL-Kali 的 Docker 环境做本地部署验证（PostgreSQL 16 + Redis 7）。
> 修订说明：原方案本地开发用 `docker-compose.dev.yml` 起 PG/Redis；现按用户决策改为 **DBngin（TablePlus 团队，Windows/macOS，原生免 Docker）直接托管本地 PostgreSQL 与 Redis 服务**，宿主机后端/前端直连。Docker 仅保留给 WSL-Kali 的部署验证与生产编排。
> 结论先行：**可行性高，建议分三阶段渐进执行**（详见第五节）。

---

## 一、两次 PostgreSQL Bug 情境归纳

两次 bug 均发生于 2026-09-19 同一批次（记录于 `docs/RELEASE.md` [Unreleased] 与 `.codebuddy/memory/`），共性根因：**开发与测试库是 SQLite，掩盖了 PostgreSQL 的方言行为差异，缺陷直到生产/容器环境才暴露**。两次均波及导出链路（筛选导出四入口 / 报告章节导出顺序）。

### Bug A：统计周期筛选在 PostgreSQL 上全入口 500（类型绑定差异）

- **情境**：渗透测试工单「统计周期」筛选（列表 / 统计 / 结论 / **导出** 四入口共用同一条件构造）中，「复测发起 / 复测完成 / 复测报告生成」三支按 `func.date(col) >= '<日期串>'` 比较。
- **机制**：日期字符串被绑定为 `VARCHAR`，PostgreSQL 无 `date >= character varying` 算子 → `asyncpg.UndefinedFunctionError` → 500。实测选择统计周期后 `/testing-plans/conclusion`（含 `conclusion/export` 整改情况 Excel 导出）等四个入口**全部 500**。
- **为何本地未发现**：单测共享库是 SQLite，两侧都是文本，比较「看似通过」——接口级用例完全无法暴露。
- **修复**：`plan_query._datetime_date_range` 改用 `[当日 00:00, 次日 00:00)` 半开区间（类型正确、不套列函数、可用索引）；非法日期明确 400；新增 PostgreSQL 方言编译守卫用例（`test_plan_query.py::test_period_condition_uses_datetime_binds`）。
- **已固化教训**：AGENTS.md「DateTime 列禁止与日期字符串比较」条目；推论「SQLite 单测覆盖不到的类型差异，需补方言级静态断言」。

### Bug B：删除漏洞时 `remote_testings.vuln_id` 外键 500（外键强制差异）

- **情境**：`DELETE /vulns/{id}` 删除被远程检测关联的漏洞时，`_clean_vul_references` 漏置空 `remote_testings.vuln_id`；该列在 PostgreSQL 带强制外键约束 → 删除直接 500。
- **为何本地未发现**：SQLite 默认 `PRAGMA foreign_keys=OFF`，**根本不校验外键**，本地删除既不级联也不报错。
- **修复**：`_clean_vul_references` 补置空 `remote_testings.vuln_id`（同批补删 `spring_action_vulns` 关联，并修复删除后未重算工单复测闭环状态）。
- **已固化教训**：项目长期记忆「漏 `remote_testings` 会让生产 PG 删除 500，而 SQLite 开发库不校验外键因此本地测不出」。

### 历史同族 bug（佐证证据链）

此类「SQLite 掩盖 PG 行为差异」的缺陷在发布史上至少还有 5 例：

| 时间 | 缺陷 | 差异类型 | 波及导出 |
|---|---|---|---|
| 早期 | 导入章节乱序：确认入库查询无 `ORDER BY`，生产 PG 返回顺序不定 → 章节 `order` 乱序写入 | 结果集顺序（SQLite 靠 rowid 天然有序） | **是**（报告编辑页章节导航与导出 Word 章节顺序错乱，后以解析序号纠偏） |
| 早期 | `remote_testings.appeal_success` 僵尸列：模型改用 `appeal_status` 后 PG 残留 NOT NULL 无默认值列 → INSERT `NotNullViolationError` 500 | 列约束强制（SQLite 开发库因重建表逃过） | 否 |
| 2026-09 前 | `affected_url` 定长 512 溢出：约 20 条 URL 即溢出，PG 写入抛 `StringDataRightTruncation` 500 | 长度校验（SQLite 不校验长度） | 否（写入侧） |
| 2026-09 前 | `vulns.score` Integer→Float：PG 需显式 `USING` 转换，SQLite 动态类型无感 | 类型系统 | 否 |
| 2.11.1 前 | 历史漏洞导入 `submit_time` 全同 + PG 无序入库 → 流程抽屉漏洞排序错乱 | 插入顺序依赖 | 间接 |

**归纳**：差异集中在五个轴——类型/绑定严格性、外键强制、长度约束、结果集顺序确定性、DDL 能力（`ALTER COLUMN`/`USING` 转换）。SQLite 开发环境在其中每个轴上都给出「假绿」信号，且项目已被迫为每类差异补建守卫（方言编译断言、双轨迁移守卫、schema 一致性测试）——**这是双数据库栈的持续性维护税**。

---

## 二、受影响范围（SQLite 现存触点盘点）

| # | 位置 | 性质 | 规模/说明 | 处置 |
|---|---|---|---|---|
| 1 | `backend/app/db.py::_migrate_lightweight` | **SQLite 专属**幂等轻量迁移 | 22–376 行，约 355 行；入口处 `dialect.name != "sqlite"` 即返回，对 PG 是死代码 | 删除 |
| 2 | `backend/app/db.py::init_db` | 建表 + 内置角色/admin/字典种子 | **PG 生产同样依赖**（全新库由 create_all 建最新 schema，`scripts/migrate.py` 依赖此决策做 stamp 纳管） | **保留** |
| 3 | `backend/app/db.py::_backfill_asset_tech_fields` | 存量技术字段回填（ORM 逻辑，方言无关） | 为旧库数据服务，幂等 | 生产已回填完毕后删除（先核实） |
| 4 | `dev.ps1` / `dev.sh` | 一键本地开发：`VP_DATABASE_URL=sqlite+aiosqlite:///./dev.db` + `VP_DISABLE_QUEUE=1` + `VP_DEBUG=1` | 两个脚本 + README 引用 | 改造（连 DBngin 本地 PG/Redis） |
| 5 | `backend/tests/conftest.py` | **测试库 = SQLite 文件** + `VP_DISABLE_QUEUE=1` + `VP_DISABLE_REDIS=1` | **全部 272 passed + 1 skipped 用例跑在 SQLite 上——最大影响面** | 切换 PG |
| 6 | `backend/scripts/seed_dev_data.py` | SQLite dev.db 演示数据种子（含 `_assert_dev_database` 守卫） | 守卫逻辑 SQLite 专属 | 守卫改为 PG dev/test 库名白名单 |
| 7 | `backend/app/core/config.py` | `DISABLE_QUEUE` / `DISABLE_REDIS` 开关 | 与 SQLite 无必然耦合，是「无 Redis 单机」容错 | **建议保留**（见风险 R8） |
| 8 | `app/main.py` / `workers/dispatch.py` / `core/ratelimit.py` / `core/token_store.py` | Redis 不可用时进程内降级（arq 进程内执行 / 限流内存计数 / token 轮换降级） | 2026-09-18 G7 修复成果，生产韧性设计 | **保留** |
| 9 | `backend/tests/test_schema_consistency.py` | **双轨迁移守卫**（Alembic 轨 + db.py 轻量迁移轨必须同步） | 3 个双轨断言 + `DEPRECATED_COLUMNS` 机制 | 双轨改单轨，Alembic 断言保留 |
| 10 | `backend/alembic/versions/`（4 个迁移文件） | SQLite 双轨注释 / SQLite 跳过分支（如 `d9e0f1a2b3c4` 的改列跳过） | 历史迁移内容冻结，仅注释与防御分支 | 注释清理即可，不强制 |
| 11 | 测试内方言兼容点 | `test_api.py:4510`（长度校验缺失说明）、`test_retest_title_sanitize.py:8`（外键不启用说明）、`test_plan_query.py:257`（方言断言理由） | 迁 PG 后语义更真实 | 逐例适配 |
| 12 | 文档 | AGENTS.md（技术栈表、开发环境变量、数据库迁移双轨铁律）、README、DEPLOY.md（「是否需要清除 SQLite 数据」节）、RELEASE.md、`.codebuddy/memory/MEMORY.md` | 多处 | 同步修订 |
| 13 | `backend/dev.db` 及 `tests/test_vp.db` 产物 | 本地数据文件 | gitignore 覆盖 | 数据价值评估后废弃 |

**不在受影响范围**：`docker-compose.yml` 生产编排（纯 PG+Redis）、`scripts/migrate.py`（Alembic 决策，反而受益简化）、`scripts/upgrade.sh`/`backup.sh`/`restore.sh`（PG 逻辑备份链路）、前端全部代码、`app/` 业务代码（`_migrate_lightweight` 是唯一 dialect 分支，`knowledge.py` 的 JSON CAST 已双方言兼容）。

---

## 三、潜在风险

| # | 风险 | 等级 | 说明与对策 |
|---|---|---|---|
| R1 | **测试体系重建成本**：272 个用例全量迁移，PG 测试库生命周期管理（建库/清库/隔离）取代 SQLite 文件库的「随起随删」 | 高（工作量） / 低（技术难度） | 测试本就是 session 级共享库，切 PG 后沿用「session 前重建 schema + session 后清理」即可；用例代码绝大多数无需改动（SQLAlchemy 屏蔽方言） |
| R2 | **用例行为语义变化**：PG 上外键真实级联、长度约束真实生效、JSON 列原生类型、事务隔离真实——预期暴露少量「SQLite 下假绿」的用例 | 中 | 这正是迁移的目的（消灭假绿）；逐例适配，适配结果反过来是回归护栏。已知敏感点：外键级联（`test_retest_title_sanitize` 注释）、字段长度（`test_api.py:4510`） |
| R3 | **外部服务前置依赖**：DBngin 的 PG/Redis 服务需已创建并处于运行状态，pytest / dev 脚本才能连上 | 中 | dev 脚本与 conftest 增加轻量预检（TCP 探测 `127.0.0.1:5432/6379`），未就绪时给出「请先在 DBngin 启动服务」的明确报错，替代无休止连接超时。另注意两点：① 生产 `docker-compose.yml` 的 postgres/redis **未映射宿主端口**，与 DBngin 默认端口（5432/6379）无冲突；② 与 WSL-Kali 部署验证同时进行时需确认 DBngin 服务已停止或端口不撞（DBngin 支持多端口实例） |
| R4 | **离线/零依赖开发能力丧失**：无 DBngin 服务时无法起后端 | 低（对现状用户） / 需如实知悉 | DBngin 为本机原生进程（非 Docker/VM），启动轻量、可开机常驻；用户已确认不走 SQLite 路径 |
| R4a | **版本对齐**：DBngin 实例版本若与生产镜像不一致，仍存在小幅方言窗口 | 低 | DBngin 支持 PostgreSQL 12–17，**建实例时明确选 16**、Redis 选 7.x，与生产 `postgres:16-alpine` / `redis:7-alpine` 对齐；版本号写入 dev 脚本注释与本文档，升级生产大版本时同步升 DBngin 实例 |
| R4b | **认证差异**：DBngin 的 PG 默认 `postgres` 超级用户且无密码（本地信任连接），与生产密码认证不同 | 低 | 仅环境形态差异，不影响应用行为（连接串由 `VP_DATABASE_URL` 注入）；建议在 DBngin 实例内为 dev/test 建独立库（`talos_dev` / `talos_test`）+ 简单口令，避免「无密码超级用户直连」成为习惯 |
| R5 | **过渡期规范真空**：删双轨守卫后，若 AGENTS.md「数据库迁移」章节未同步重写，新代码可能再踩 Alembic 单轨遗漏 | 中 | 阶段二一次性收口：AGENTS.md 迁移铁律改单轨、`DEPRECATED_COLUMNS` 断言保留 Alembic 侧 |
| R6 | **一次性大爆炸风险**：测试切换 + 删除轻量迁移同批落地，失败时难以定位 | 中 | 分阶段（见第五节）：先并行切换跑通基线，再删代码 |
| R7 | **存量 dev.db 数据**：若需保留需一次性 SQLite→PG 数据迁移脚本 | 低 | 建议直接废弃（用户已不使用该路径，数据价值低）；确需保留可写一次性导入脚本（SQLAlchemy 双引擎读旧写新，模型已对齐） |
| R8 | **误伤 Redis 降级机制**：把「废弃 SQLite 开发」扩大为「删除 DISABLE_QUEUE/DISABLE_REDIS」 | 低 | 两者无必然耦合。降级是生产韧性设计（Redis 抖动时 API 仍可用、有界超时），保留成本为零，**建议永久保留**，仅改默认值取向 |
| R9 | **删除后回退成本**：恢复 SQLite 支持需从 git 历史回溯 | 低 | git 历史即归档（项目文档治理既定原则） |

---

## 四、替代实现思路

### 4.1 开发环境（替代 dev.ps1 / dev.sh 的 SQLite 模式，PG/Redis 由 DBngin 原生托管）

**前置（一次性，DBngin 内手工配置）**：

- DBngin（TablePlus 团队，免费，Windows/macOS 原生应用，无 Docker/VM 依赖）新建两个服务：
  - PostgreSQL **16**（对齐生产 `postgres:16-alpine`），默认端口 5432；
  - Redis **7.x**（对齐生产 `redis:7-alpine`），默认端口 6379；
- 在 PG 实例内建两个库：`talos_dev`（开发数据）、`talos_test`（测试库，session 级重建）；
- 版本与端口写入 dev 脚本注释，生产大版本升级时同步升 DBngin 实例。

**dev.ps1 / dev.sh 改造为三步**：

1. **预检**：TCP 探测 `127.0.0.1:5432` / `6379`，不通则报「请先在 DBngin 启动 PostgreSQL/Redis 服务」并退出（替代无休止的连接超时）；
2. 起 venv 后端：`VP_DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:5432/talos_dev`、`VP_REDIS_URL=redis://127.0.0.1:6379/0`、`VP_DISABLE_REDIS=0`、`uvicorn --reload --port 27015`；
3. 起前端 `pnpm dev`（27014，代理配置不变）。

**队列口径（开发态建议）**：保留 `VP_DISABLE_QUEUE=1` —— 后台任务（报告导出等）在 API 进程内执行，无需另开 arq worker 进程，热重载友好；Redis 此时仍真实承担限流 / 登录锁定 / token 轮换（`VP_DISABLE_REDIS=0`）。若需调试真实队列，可显式置 0 并另起 `arq app.workers.main.WorkerSettings`。

- **收益**：开发环境与生产同方言同版本（PG16 / Redis7，仅部署形态不同：DBngin 原生 vs 容器）；「本地测不出」类缺陷在开发期即暴露；无 Docker 资源开销，启动即用。
- **无端口冲突**：生产 `docker-compose.yml` 的 postgres/redis 未映射宿主端口（仅容器网络内互通），DBngin 独占 5432/6379；WSL-Kali 部署验证与本地开发可并存。

### 4.2 测试体系（替代 conftest 的 SQLite 文件库）

- **方案 A（推荐）**：`conftest.py` 直连 DBngin PG 的 `talos_test` 库（`VP_DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:5432/talos_test`）；session fixture 改为「drop schema cascade → `init_db()`（create_all + 种子）→ session 后 drop schema」。不依赖 Docker / WSL，跑测试就是纯本机进程 + 本机 PG；沿用「session 级共享库」既有形态，272 个用例代码绝大多数无需改动。
- **方案 B（CI / 无 DBngin 环境兜底）**：CI 用 `services: postgres / redis` 容器（GitHub Actions 等），conftest 只认 `VP_DATABASE_URL` 环境变量，两形态零改动兼容；本机若偶需容器跑测试亦可临时 `docker run postgres:16-alpine -p 5432:5432`。
- **方案 C**：`testcontainers-python` 动态起容器。依赖 docker socket、Windows+WSL 组合需验证、首次拉镜像慢，**不再需要**（DBngin 已覆盖本机场景），不采用。
- 方言编译断言类守卫（`test_period_condition_uses_datetime_binds`）保留——静态断言比集成行为更早失败、定位更准；测试库即为 PG 后，此类守卫从「唯一防线」降级为「快速反馈」，价值仍在。
- `VP_DISABLE_REDIS=1` 在测试中可继续使用（省去逐用例付 Redis 往返），与「开发全面采用 Redis」不冲突——降级路径本身有 `test_ratelimit_timeout.py` 守卫；如需覆盖真实 Redis 交互（限流、token 轮换），可加一个连 DBngin Redis 的 opt-in 标记用例（`-m redis`）。
- Windows 特有收益：消除 SQLite 文件句柄锁 `test_vp.db` 的残留进程问题（conftest 已记录的坑）；PG 库无文件锁，清理更可靠。

### 4.3 后端代码瘦身

- 删 `_migrate_lightweight`（~355 行）与 `init_db` 中对它的调用；`init_db` 其余保留（PG 生产依赖）。
- `_backfill_asset_tech_fields`：先在容器内核实生产 PG 已全部回填（该脚本每轮启动幂等执行，理论上早已收敛），确认后删除。
- `test_schema_consistency.py`：删 SQLite 轨断言（`test_lightweight_migration_drops_legacy_appeal_success`、`test_retest_round_src_report_column_in_both_tracks` 的 db.py 分句），`DEPRECATED_COLUMNS` 的模型断言与 Alembic 断言保留并升格为唯一轨道。
- `seed_dev_data.py`：守卫从「仅 `sqlite+aiosqlite:///./dev.db`」改为「仅允许库名 `talos_dev` / `talos_test`」。
- Alembic 历史（链头已至 `e1f2a3b4c5d6` 及之后）：历史迁移内容冻结不动，仅注释清理；**新迁移自此只写 Alembic 单轨**。

### 4.4 文档修订清单

AGENTS.md（技术栈表「开发 SQLite」→「开发/生产统一 PostgreSQL，本地由 DBngin 托管」；开发态环境变量；「数据库迁移」双轨铁律改单轨）· README.md / README_EN.md（一键开发说明，注明 DBngin 前置）· docs/DEPLOY.md（删「是否需要清除 SQLite 数据」节）· docs/RELEASE.md（[Unreleased] 记 Removed 条目）· `.codebuddy/memory/MEMORY.md`（数据库迁移节重写）。

---

## 五、评估结论与建议

### 结论

**废弃 SQLite、统一 PostgreSQL + Redis：可行且值得做。**

1. **风险面收敛**：SQLite/PG 方言差异已造成至少 7 次线上或发布前缺陷（第一节），且类型、外键、长度、顺序、DDL 五个轴的差异**无法靠单测穷尽防守**——项目已被迫建立三类守卫（方言编译断言、双轨迁移守卫、schema 一致性测试）来对冲，属于持续性维护税。统一方言后该类风险**整体消失**，守卫负担减半。
2. **成本结构**：SQLite 仅剩两个角色——本地一键开发（用户已弃用）与测试库（需一次性重建）。生产编排、迁移脚本、备份链路、验收流程（WSL-Kali 重建镜像 + 22 接口探针）**早已是 PG+Redis**，不受影响。
3. **同构收益**：开发（DBngin 原生 PG16 + Redis7）、测试（同实例 `talos_test` 库）、生产（`postgres:16-alpine` / `redis:7-alpine` 容器）三者同方言同大版本，仅部署形态不同，「测过即所见」；DBngin 原生进程无 Docker 开销，本机开发更轻。顺带消除 Windows SQLite 句柄锁文件（conftest 已记录的坑）等文件库特有问题。
4. **Redis 判断**：全面采用 Redis 开发没有障碍，但 `DISABLE_QUEUE` / `DISABLE_REDIS` 与进程内降级**不建议删除**——那是生产韧性设计（G7 成果），与 SQLite 无耦合；只把「默认依赖降级」的开发模式废弃掉。

### 分阶段执行建议

| 阶段 | 内容 | 验收 | 风险 |
|---|---|---|---|
| **一：切换期**（1 个 PR，不删代码） | DBngin 建 PG16/Redis7 实例与 `talos_dev`/`talos_test` 库；`dev.ps1`/`dev.sh`、`conftest.py` 切 DBngin PG+Redis（含预检）；跑全量测试确立新基线；适配语义变化的用例 | 后端全量 pytest 新基线全绿（预期 ≥ 272 通过）；`ruff`/`vulture` 全绿；22 接口探针照常 | 低；SQLite 代码仍在，可随时回退 |
| **二：收口期**（切换稳定后） | 删 `_migrate_lightweight`、SQLite 双轨守卫、seed SQLite 守卫；AGENTS.md/README/DEPLOY/RELEASE 文档同步；`.codebuddy/memory` 更新 | 全量测试与探针复跑；`rg -i sqlite` 仅剩历史迁移冻结注释与 RELEASE 记录 | 低（阶段一已验证运行路径） |
| **三：可选收尾** | 评估 `_backfill_asset_tech_fields` 去留；清理 dev.db / test_vp.db 残留文件与 .gitignore 条目；（可选）CI 补 services 容器形态；（可选）`-m redis` 真实 Redis 用例 | 死代码检查 `vulture` 通过 | 低 |

**总工作量预估**：阶段一约 1–2 个工作日（主要是测试库 fixture 与用例适配）；阶段二约 0.5 天；属低风险重构，无生产数据迁移需求（`pg_data` 卷与本次变更无关）。

---

*本报告为未闭环专项评估文档，迁移决策与执行完成后按文档治理规则归并删除（结论并入 AGENTS.md / DEPLOY.md，历史记入 RELEASE.md）。*
