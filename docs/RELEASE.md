# Talos 版本发布记录（Release Notes）

本文档记录 Talos 漏洞管理平台的每次版本更新,格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## 版本号规则

版本号遵循 [语义化版本 Semantic Versioning](https://semver.org/lang/zh-CN/) `x.y.z` 管理:

| 位 | 名称 | 递增条件 |
| --- | --- | --- |
| `x` | 主版本号(Major) | 不兼容的重大变更:API 破坏性调整、移除已有模块 / 接口、数据库结构不兼容迁移、架构级重构 |
| `y` | 次版本号(Minor) | 向下兼容的功能新增或明显的用户可见变化(新模块 / 新功能 / 命名体系统一) |
| `z` | 修订号(Patch) | 向下兼容的问题修复、小优化、文档 / 构建脚本调整 |

> **版本号重算说明（2026-08-13）**：本文档版本号依据上述语义化版本规则,从 `0.1.0` 起对每一次发布的内容重新推算——每个发布点按其改动性质定级(新增功能→次版本、缺陷修复→修订号、破坏性变更→主版本),确保版本号变化准确反映改动的性质与影响范围。首个破坏性变更为「0.4.0 应用与资产合并重构」(移除独立的应用管理模块 `/apps` 及 `app:manage` 权限点,漏洞与资产改为多对多关联),该发布定为 `1.0.0`；自此之后的功能新增依次递增次版本号。

发布约定:

- 每次发布需同步更新三处版本号:本文档、`backend/app/core/config.py` 的 `APP_VERSION`、`frontend/package.json` 的 `version`；登录页右下角版本号由前端构建时从 `package.json` 注入（`vite.config.ts` 的 `__APP_VERSION__`），随 `version` 自动同步，无需单独修改
- 发布后在 git 上打注解标签:`git tag -a vX.Y.Z -m "release x.y.z"`
- 变更条目按类型分组:`新增(Added)` / `变更(Changed)` / `修复(Fixed)` / `移除(Removed)` / `安全(Security)`
- 未发布的改动先记入「Unreleased」,发布时移入对应版本段落

> **Tag 管理说明（2026-08-13）**：版本号体系重构时,旧的 `v0.5.0`~`v1.1.1` 共 11 个标签编号与本文档重算后的版本（`1.0.0`~`1.11.1`）已完全错位,已全部清理（本地 + 远程）。本文档为唯一版本真相源,**历史版本不再追溯打标签**；仅未来新发布时按上述约定打 `vX.Y.Z` 注解标签（从 `1.11.1` 之后继续）。

---

## [2.20.0] - 2026-09-22

### 新增

- **测试统一入口 + 并发隔离（测试流程改进 P0/P1/P2）**（2026-09-21）：
  - 新增 `scripts/test.sh` / `scripts/test.ps1` 作为测试唯一入口，固化三件「记错就得到误导性结果」的事：
    关闭受管终端删除守卫、每次运行唯一 basetemp（仓库内）、5432/6379 依赖预检；并支持 `--workers N`（pytest-xdist
    并行）与 `--prune`（回收残留 schema 与 basetemp）。
  - `conftest.py` 改为**每个 pytest 进程独占一个 PostgreSQL schema**（`VP_DB_SCHEMA` → 业务连接与 Alembic 的
    `search_path`；存储目录同步按 run 隔离），消除并发跑测试互相 `DROP SCHEMA` 造成的假失败 ——
    实测同一份代码：并发（隔离前）70 failed / 219 passed，隔离后**串行 291 passed / 1 skipped / 40.38s、
    4 worker 并行 29.97s**。
  - 新增 `backend/scripts/probe_api.py`：22 个关键接口探针固化为脚本（取代「每次手写临时脚本、用完即删」），
    本地 / 容器 / CI 共用一份口径。
  - 新增 `backend/scripts/prune_test_schemas.py`：回收被强杀进程遗留的 `test_*` / `mig_*` schema
    （默认只列出，`--yes` 才删；仅回环地址上的 `*_test` 库，fail-closed）。
  - `requirements-dev.txt` 增加 `pytest-xdist`（本地并行）与 `pytest-cov`（本地覆盖率报告，不设全量阈值）。
  - **CI：决定不采用**（2026-09-22）：曾新增 `.github/workflows/ci.yml`（后端静态检查 / 后端测试 /
    前端三门禁 三 job 并行），经评估后**已删除** —— 门禁一律在**本机**执行（`scripts/test.ps1` + 前端三门禁
    + 发布前 `scripts/probe_api.py` 探针）。理由：本机与生产同栈（PG 16 + Redis 7 单栈），CI 的增量收益
    （跨机器可复现、多 job 并行）低于其维护成本与 runner 分钟消耗。
- **本地垃圾清理脚本**（2026-09-22）：新增 `scripts/clean.sh` / `clean.ps1` —— 只清**可再生**本地产物
  （`__pycache__`、`.pytest_cache`/`.ruff_cache`、`backend/_pytest_tmp`、`frontend/dist`、测试存储残留、
  `_*.txt`/`_*.log` 临时日志），默认**预演**、`--apply`/`-Apply` 才删除，并带**硬白名单**（`.env` /
  `dev-database` / `backups` / `backend/storage` / `.venv` / `node_modules` 等命中即中止）。首次执行释放 **7.9 MB**；
  另按「只留最近 1 份」清理本地演练备份 `backups/`（4.8 GB → 1.8 GB，回收 ~3.0 GB）并清空 `backend/storage/`。
- **前后端契约检查**（2026-09-22）：新增 `backend/scripts/check_api_contract.py` —— 把 OpenAPI（`app.openapi()`）
  与 `frontend/src/types/index.ts` 做**双向字段集合比对**，**不连数据库**：**TS 有 / API 无 → 失败**（前端读永不返回的
  字段 → 运行时静默 `undefined`；`el-table` 插槽是 `any`，`vue-tsc` 抓不到这类问题）；**API 有 / TS 无 → 默认告警**
  （本项目 TS 只声明实际消费字段，属有意为之），`--strict` 才视为失败。首运行即抓到一处真实缺陷并已修复（见「修复」）。
- **端到端测试（E2E）落地**（2026-09-22）：新增仓库根工具包（`package.json` + `playwright.config.ts` + `e2e/golden-path.spec.ts`）
  与编排脚本 `scripts/e2e.ps1` / `e2e.sh` —— 自动起**独立 E2E 栈**（`vulnplatform_e2e` 库 + 迁移 + 种子 + api 27016 +
  前端 27017 + 独立 storage，与 dev 栈完全隔离），跑 3 条黄金链路：登录、新建漏洞（含影响URL 批量粘贴切分/去重/落库）、
  报告编辑器渲染；每条均断言**控制台 0 error**。用**系统 Chrome**（`channel: 'chrome'`，浏览器下载 0 MB），
  `workers: 1` + `retries: 1` + `trace on-first-retry`，**不做截图基线/canvas 断言**。实测 **3 passed / 1.4 min**
  （用例本体各 ~2.5 s，其余为起栈）。为定位稳定锚点，给登录/漏洞表单/影响URL 编辑器补了 8 处 `data-test`。
  前置：`vulnplatform_e2e` 库（DBngin 一次创建）+ 根目录 `pnpm install`。
- **pre-push 门禁钩子**（2026-09-22，替代 CI 的「机器强制」）：新增 `.githooks/pre-push`（ruff/vulture + 全量 pytest +
  契约检查 + 前端三门禁；依赖服务未启动时 fail-open，`TALOS_PREPUSH_STRICT=1` 可改为严格阻断）+ `.gitattributes`
  强制 `.githooks/*` 与 `*.sh` 使用 LF（CRLF 会让 `#!/usr/bin/env bash` 直接失效）。启用需各人执行一次
  `git config core.hooksPath .githooks`（仓库不代为修改 git 配置）。
- **拆分单体 `tests/test_api.py`（4626 行 / 89 用例）为 11 个领域模块**（2026-09-22）：新增
  `backend/tests/api/`（`test_api_{core_auth,assets_vulns,imports,reports,retest,plans,dashboard,special,knowledge,pat_open_api,misc}.py`
  + 共享 `_helpers.py`）。用 AST 拆分器做**纯搬移**（逐字比对 + 名称守恒校验，收集数量保持 292 不变），
  并整改三处「依赖其它用例先造数据」的隐式耦合：`test_dashboard` 与 `test_report_edit_and_export`
  改为自建漏洞；`test_dashboard_by_department` 因依赖 `test_retest_round_tracking` 的「轮次部门」数据，
  迁入复测模块并在 docstring 注明该**同模块内顺序依赖**。**效果**：11 个模块逐一单独运行全绿（不再有
  跨模块数据依赖）；`-Workers 4` 并行的加速比由 **1.35x → 2.05x**（串行 36.8s → 并行 17.9s）。
- **Alembic 迁移端到端守卫**（2026-09-21）：新增 `backend/tests/test_migrations.py` —— 在独立 schema 里
  真跑 `alembic upgrade head`，断言迁移建出的表/列与模型声明**完全一致**，并验证 `downgrade base` 能回到
  空 schema。单轨化后 migrations 是 schema 演进的唯一路径，此前**没有任何测试执行过迁移**（其余用例走
  `create_all`，`test_schema_consistency.py` 只对迁移源码做正则断言）。

### 修复

- **`seed_dev_data.py --reset` 在存在「联动漏扫工单」时报外键错误**（2026-09-22，E2E 首次重置 E2E 库时实测）：
  原实现按手写的「先子后父」表顺序逐表 `DELETE`，而该顺序把 `testing_plans` 排在 `nonpen_plans` **之前**，
  一旦库里有 `nonpen_plans.testing_plan_id` 非空的联动工单，就抛
  `ForeignKeyViolationError: update or delete on table "testing_plans" violates foreign key constraint
  "nonpen_plans_testing_plan_id_fkey"` —— 即**只要开发库存在联动工单，`--reset` 就不可用**。
  已改为单条 `TRUNCATE TABLE ... RESTART IDENTITY CASCADE`（依赖顺序交给 PG），顺序不再敏感、也更快。
- **漏扫基线工单「关联资产」永不显示**（2026-09-22，由新增的前后端契约检查发现）：`NonpenPlanOut` 一直缺少
  `asset_names`，而前端 `NonpenPlanWorkflowDrawer` 读取 `plan.asset_names` → 该 UI 块恒不渲染（死代码）。
  现由 `nonpen_service.asset_name_map` / `to_out` 在创建 / 列表 / 详情 / 更新 / 测试项流转五类响应中统一填充
  （按 `asset_ids` 原顺序、列表一次批量查询、资产已删则跳过）；并新增 `tests/api/test_api_nonpen.py` 固化
  （该组接口此前**没有 API 级用例**，仅被开放 API 用例间接触及）。测试基线随之 291 → **292 passed**。
- **`alembic downgrade base` 不可用**（2026-09-21，由新增的迁移守卫实测抓到）：`e5f6a7b8c9d0` 的 downgrade
  会 `ADD COLUMN appeal_success`，而该列真正被删除发生在上层迁移 `b4c5d6e7f8a9`（本迁移的 upgrade 从未删过它），
  于是回退到该步时抛 `DuplicateColumnError: column "appeal_success" already exists`。已改为「仅当该列存在时
  同步数据、不再 `add_column`」，`downgrade base` 现可正常回到空 schema。

### 说明

- `testing_plans.create_nonpen` 由迁移 `c9d0e1f2a3b4` 建列，但该标志后来改为「仅入参、不落库」，模型未映射它。
  该列 `NOT NULL + server_default=false`，对写入无影响；按项目既有口径（`assets` 的 `ports`/`services`/… 同理）
  **删列属独立专项**（需 Alembic 迁移 + 登记 `DEPRECATED_COLUMNS`），故在 `tests/test_migrations.py` 中登记为
  已知惰性列，不顺手删除。

---

## [2.19.1] - 2026-09-21

### 变更

- **本地开发环境切换 DBngin 托管 PostgreSQL + Redis**（2026-09-21）：`dev.ps1` / `dev.sh`
  由「SQLite + 免队列」改为连接 DBngin 本机原生托管的 PostgreSQL 16（`vulnplatform` 开发库）与
  Redis 7——凭据复用根目录 `.env`，新增依赖服务预检（5432/6379 未监听即给出明确指引）；
  后端测试库同步切至 `vulnplatform_test`（conftest 支持外部 `VP_DATABASE_URL` 覆盖以兼容
  CI services 容器，并以「库名必须 `_test` 结尾」护栏防止误清开发/生产库，session 开始/结束
  各执行一次 DROP SCHEMA 重建）。开发与测试自此与生产同方言同大版本，消除 SQLite 掩盖
  PostgreSQL 方言差异导致的「本地测不出」缺陷（单栈化后该类风险整体消失；搭建手册见
  `docs/LOCAL_DEV_SETUP.md`）。**阶段二收口已在同批完成**（见下方「移除」）。
  本批次测试基线：**290 项 = 289 passed + 1 skipped + 0 failed**（旧 SQLite 基线 272 passed + 1 skipped；
  阶段一切换后为 283 passed，阶段二新增守卫用例 6 项后为 289）。
- **开发种子脚本目标库守卫改为 PostgreSQL 口径**（2026-09-21）：`scripts/seed_dev_data.py` 的默认 DSN
  由「写死 `sqlite+aiosqlite:///./dev.db`」改为解析仓库根 `.env`（指向本机 `vulnplatform` 开发库）；
  `_assert_dev_database()` 判据由「仅限 SQLite dev.db」改为「库名 ∈ {`vulnplatform`,
  `vulnplatform_test`} **且** 主机为回环地址」，二者缺一即以退出码 2 拒绝执行，缺失/非法 DSN
  一律 fail-closed（较原方案增加主机维度：只校验库名会放过「同名远程库」）。
- **文档同步单数据库栈口径**（2026-09-21）：`AGENTS.md` 技术栈表与开发态环境变量改 PostgreSQL、
  新增「数据库迁移（单轨）」条目（并修正原先指向不存在章节的悬空引用）、后端测试基线由过期的
  `189 passed` 校正为 `289 passed`；`README.md` / `README_EN.md` 一键开发步骤补 DBngin 前置与
  PG DSN；`docs/DEPLOY.md` 删「是否需要清除 SQLite 数据」节、排障节改单轨口径；
  `docs/SCRIPTS.md` 更新 `seed_dev_data.py` / `migrate_utc_to_utc8.py` 的守卫与方言描述及行号。

### 移除

- **SQLite 双轨迁移与相关守卫**（2026-09-21，阶段二收口）：删 `app/db.py::_migrate_lightweight`
  共 **358 行**（`app/db.py` 由 496 行降至 138 行）及其在 `init_db` 中的调用——schema 演进自此
  **只有 Alembic 单轨**，无第二条兜底路径（`init_db` 的 `create_all` + 种子保留，PG 生产依赖）。
  同步删除 `tests/test_schema_consistency.py` 的 SQLite 轨断言（保留 `DEPRECATED_COLUMNS` 模型断言
  与 Alembic 断言），`scripts/migrate_utc_to_utc8.py` 的 SQLite 分支，以及 `requirements-dev.txt`
  的 `aiosqlite` 依赖。
- 新增两条收口守卫防回退（`tests/test_schema_consistency.py`）：`test_no_sqlite_driver_imports_in_app`
  （`app/` 下不得再引用 `aiosqlite` / `sqlite3`）与 `test_default_database_url_is_postgresql`
  （配置默认 DSN 不得回退为 SQLite）；`tests/test_seed_dev_data_guard.py` 按新守卫语义重写。
- **一次性数据回填函数与 SQLite 残留文件**（2026-09-21，阶段三收尾）：删除
  `app/db.py::_backfill_asset_tech_fields`（历史技术字段回填，37 行函数 + 其 `init_db` 调用；
  `app/db.py` 138 → 98 行）。删除**前置已在生产 PG 核实收敛**：44 个资产全部满足「新 JSON 列已归一
  且旧列无待搬运数据」（核实判定 `rows_needing_backfill = 0`，各分项计数亦为 0）；该核实 SQL 与
  函数行为的等价性已在本地 PostgreSQL 上用 5 类边界数据验证。同批删除本地 SQLite 残留
  `backend/dev.db`（618 KB / 31 张表；演示数据可由 `scripts/seed_dev_data.py` 重建）、
  `.gitignore` 中 SQLite 专属忽略项，并清理 4 个冻结迁移文件里的历史 SQLite 注释
  （`d9e0f1a2b3c4` 的方言防御**代码**分支按「历史迁移内容冻结」原则保留未动）。
  注：旧列 `ports` / `services` / `middleware` / `database_type` 已无任何读写方（唯一引用即该函数），
  但**删列不在本次范围**（属独立 schema 变更，须走 Alembic 迁移并登记 `DEPRECATED_COLUMNS`）。

### 修复

- **测试事件循环作用域与数据库连接池错配**（2026-09-21）：`backend/pytest.ini` 此前只声明了
  fixture 侧的 `asyncio_default_fixture_loop_scope = session`，测试侧仍为默认的函数级 loop，
  导致 session 级 fixture 建立的 asyncpg 连接池被跨 loop 复用，抛 `Event loop is closed` /
  `'NoneType' object has no attribute 'send'`（SQLite + aiosqlite 走独立线程、对 loop 归属不敏感，
  该缺陷长期被掩盖）。现补齐 `asyncio_default_test_loop_scope = session`，并新增回归守卫
  `backend/tests/test_asyncio_loop_scope.py`（静态校验两条配置 + 运行时断言用例与 session
  fixture 同 loop + 连接池可用性冒烟）。

---

## [2.19.0] - 2026-09-20

### 新增

- **渗透测试工单聚合筛选支持条件分组与嵌套**（2026-09-19）：筛选条件由「扁平规则 + 单条取反」升级为
  **条件树** —— 每个分组可单独设置组内逻辑（且 / 或）与整组取反（非），分组之间再按父级逻辑连接，
  优先级完全由嵌套层级（括号）表达，可表达「需求接收晚于 X 且（状态为 Y 或 Z）」这类混合逻辑。
  界面新增递归分组编辑器（条件 / 分组动态增删、最多 5 层）与「实际生效条件」可读表达式预览，
  未填写完整的条件会明确标注「暂不生效」；历史已保存的扁平条件会自动折叠为等价条件树，无需重配。
  接口层 `filters` 参数同时接受新版条件树与历史 `{"rules": [...]}` 扁平格式（左结合语义保持），
  并新增结构限制（嵌套 ≤ 5 层、条件 ≤ 50 条），非法结构返回 400；列表 / 统计 / 结论 / 导出四处口径一致。
- **渗透测试结论输出模块优化**（2026-09-19）：
  - **新结论文本**：「渗透测试方面，统计周期内（{周期文字}）共完成 x 个部门（xx部门、yy部门）的 n 个系统
    测试工作。其中初测完成 a 个系统发现 v 个漏洞。复测完成 b 个系统，其中 y 个系统已完成整改，z 个系统
    未完成整改仍存在漏洞未修复。请相关部门尽快完成漏洞修复并提交复测。具体漏洞情况详见附件。」
    周期文字跟随所选条件——快捷项显示名称（本周 / 本月…），自定义区间显示「起始 - 结束」，未筛选为「全部时间」；
    部门按工单 `department` 去重并以顿号列出（空值记「未填写」），系统数按工单去重。
  - 统计卡片同步改为「部门数 / 完成系统数 / 初测完成系统 / 初测发现漏洞 / 复测完成系统 /
    已完成整改 / 未完成整改 / 周期内发起复测 / 周期内复测报告」，**涵盖周期内发起复测与生成复测报告的统计**。
  - 结论附件（整改情况.xlsx）扩展「初测完成时间 / 复测完成时间」两列。
  - 接口：`conclusion` / `conclusion/export` 新增 `period_label` 参数（周期名称，仅影响文案）；
    `PlanReportBrief` 新增 `is_retest` / `retest_state`，报告管理列表新增 `retest_state`。
- **漏洞行内编辑与删除**（2026-09-19）：历史漏洞库列表新增「操作」列，行内直接「编辑 / 删除」，
  删除按钮按权限（漏洞管理员或提交人本人）展示，二次确认后单条删除并联动刷新统计；
  渗透测试工单流程抽屉的漏洞行在「编辑」后新增「删除」（认领者可见），
  无需再跳转历史漏洞库勾选多选删除。原「删除选中」批量删除保留。

### 变更

- **「初测完成时间」筛选升级为「统计周期」**（2026-09-19）：列表 / 统计 / 结论 / 导出的时间范围
  （参数名沿用 `first_test_from` / `first_test_to`）命中口径改为
  「初测完成 ∪ 复测发起 ∪ 复测完成 ∪ 复测报告生成 **任一落入周期**」（见 `plan_query._period_condition`）。
  界面下拉改为「统计周期」，自定义区间占位改为「周期开始 / 周期结束」。
- **报告复测状态改为三态**（2026-09-19）：原先仅按「该报告章节漏洞是否全部闭环」打「复测完成」角标，
  无法区分「已发起复测」与「从未发起复测」的报告；现统一为
  **未发起复测 / 复测中 / 复测完成**（`plan_service.retest_state_of`），展示在工单列表「关联报告」
  与「复测轮数」弹层、工单流程抽屉报告列表、报告管理列表四处。

### 修复

- **统计周期筛选在 PostgreSQL 上 500（发布前发现）**（2026-09-19）：周期的「复测发起 / 复测完成 /
  复测报告生成」三支按 `func.date(col) >= '<日期串>'` 比较，日期串被绑定为 `VARCHAR`，
  PostgreSQL 无 `date >= character varying` 算子 → `asyncpg.UndefinedFunctionError`
  （实测：选择统计周期后 `/testing-plans/conclusion` 等四个入口全部 500，SQLite 单测因两侧都是文本
  而无法发现）。改为 `[当日 00:00, 次日 00:00)` 半开日期时间区间（`plan_query._datetime_date_range`），
  同时不在列上套函数、可用索引；非法日期改为明确 400；新增 PostgreSQL 方言编译守卫用例。
- **周期内已完成的复测被漏统计**（2026-09-19）：原时间筛选只过滤 `first_test_done_time`，而
  `retest_done_time` 与轮次 `done_time` 在工单**未全部闭环时均为空**（实测工单 20260721-1：初测完成 7-30、
  9-16 发起复测且同日生成复测报告，但复测完成点为空），选中 9-11~9-17 时该工单被排除。现按上述周期口径纳入。
- **报告与复测轮次缺少结构化关联**（2026-09-19）：新增 `testing_plan_retest_rounds.src_report_id`
  （发起本轮的源报告），Alembic `e1f2a3b4c5d6` 与 `db.py` 轻量迁移双轨同步，存量由
  `scripts/backfill_retest_src_report.py`（按 `source` 文本匹配，幂等、支持 `--dry-run`）回填；
  此前只能靠 `source` 文本反查源报告，脆弱且不可靠。
- **删除漏洞未联动工单复测闭环，且单删权限、外键清理不完整**（2026-09-19）：`DELETE /vulns/{id}`
  原仅放行 `vuln:manage`，工单认领者（无该权限）无法删除自己录入的漏洞 → 现放宽到
  「工单认领者 / 提交人本人」，同时**保留漏洞管理员（含 `*`）删除任意漏洞的原能力**
  （与前端删除按钮可见性逐条对齐，避免「按钮可见却 403」）。并修两处缺失：
  ① 单删与批量删除此前只重算工单漏洞统计、未重算复测闭环状态（`sync_plan_retest_state`），
  删掉最后一条未闭环漏洞后工单不会判「复测完成」；② `_clean_vul_references` 补
  `remote_testings.vuln_id` 置空，此前生产 PostgreSQL 删除被远程检测关联的漏洞会因强制外键 500
  （开发 SQLite 不校验外键，本地无法暴露）。

## [2.18.1] - 2026-09-19

### 安全

安全审计（`docs/SECURITY_AUDIT_2026-09-18.md`，报告不入库）确认的 6 项漏洞已全部完成修复（TALOS-2026-001~006，批次 A~E）：

- **任意文件读取 / 任意文件删除（TALOS-2026-001/002，高危）**：春耕行动「原始报告附件」与
  远程检测「申诉附件」的存储路径原由客户端提交并直接落库，下载/删除时以
  `settings.storage_path / 字段` 裸拼接，可用 `../../` 或绝对路径读取/删除进程可访问的任意文件
  （生产实测已存在 `../../../../../../../etc/passwd` 记录）。新增 `app/core/storage.py`：
  写入侧 `require_attachment_path()`（限定 `uploads/<子目录>/<32 位十六进制>.<扩展名>` 白名单，
  非法即 400）、读取/删除侧 `resolve_storage_path()`（拒绝绝对路径、盘符、`..`、符号链接越界与
  不存在的目标，统一 404）；两个附件字段不再接受手工填写的路径。
- **SSRF：通知渠道 webhook（TALOS-2026-003，高危）**：webhook 地址原仅校验 http(s) 前缀，
  可指向 Docker 内网与云元数据。新增 `app/core/outbound.py::assert_public_url()`（协议白名单 +
  域名全量解析 + 回环/私网/链路本地/共享地址/保留段判定），在渠道写入（schema）与任务发送前
  （`send_notify_task`）各校验一次，发送不再跟随重定向；企业自建内网中继可用新增环境变量
  `VP_NOTIFY_HOST_ALLOWLIST` 显式放行。
- **SSRF：报告导出远程图片抓取（TALOS-2026-004，高危）**：`htmldocx` 会对 `<img>` 中的
  http(s) 地址执行 `urllib.request.urlopen`（无超时、无目标限制），最低权限 `vuln:submit`
  即可在漏洞描述中埋入远程图片，待他人导出时触发，且响应为图片时会被嵌入 docx 回带。
  `report_builder._drop_unresolvable_images` 改为**只保留 storage 内已本地化且真实存在的图片**，
  远程图片在交给 htmldocx 前一律移除。生产量化：全库仅 3 处远程图片且均指向本平台自身
  （可被本地化），实际影响为零。
- **富文本消毒缺口：复测记录标题 HTML 注入（TALOS-2026-005，中危）**：`VulRetestRecordIn.title`
  为纯文本字段（不受 `HtmlStr` 覆盖），却被原样拼进 `vul.retest_html`，可注入任意标签
  （该字段下发给前端渲染并被导出链路当 HTML 解析）。聚合入口收敛为
  `services/vul_service.py::sync_vul_retest_html`（新增）并在拼接前 `html.escape(title)`。
- **专项域审计补齐**：春耕行动与远程检测的增删改及附件下载此前无任何审计记录（生产事件无法
  溯源）。新增审计动作 `spring_action_change` / `remote_testing_change` / `attachment_download` /
  `logout`。
- **公开图片目录未授权访问（TALOS-2026-006，低危）**：`/storage/uploads/images` 原为 `StaticFiles`
  匿名直出，报告截图（常含内网地址、账号、令牌）在 URL 泄露后可被任意人读取。现改为**需登录下发**
  （`app/api/images.py` + `core/deps.get_image_viewer`）：**URL 路径保持不变**——改前缀会让报告导出的
  图片本地化（`_localize_images`）失效并丢失图片，且前端渲染的是库内 HTML（`v-html`）无法逐张改造。
  浏览器靠登录/刷新/改密时下发的 `vp_img` Cookie 自动携带凭证（HttpOnly、`Path=/storage/uploads/images`、
  SameSite=Lax、Secure 由 `VP_COOKIE_SECURE` 控制），API 客户端可继续用
  `Authorization: Bearer <access token 或 tlp_ 令牌>`；匿名请求一律 401。
  新增 `POST /auth/logout`（注销会话并清除该 Cookie：HttpOnly 前端删不掉），`GET /auth/me` 顺带续订
  Cookie，使升级前已登录的用户无需重新登录即可恢复图片显示。
- **批次 E 加固落地**：
  - **refresh token 一次性轮换**（`core/token_store.py`）：refresh 令牌带 `jti`，刷新即轮换、旧令牌
    立即失效（默认 120 秒宽限供多标签页/并发刷新，`VP_REFRESH_GRACE_SECONDS`），退出登录注销当前
    会话、改密清空全部会话；多设备会话相互独立（上限 5）。
  - **可信代理层数显式化**（`VP_TRUSTED_PROXY_HOPS`，默认 1）：客户端 IP 改为「X-Forwarded-For
    右起第 N 项」，修复旧启发式在客户端伪造**公网** XFF 时被采信的问题（实测伪造
    `X-Forwarded-For: 1.2.3.4` 会被写进审计日志）。外层还有代理时需相应调大 N。
  - **压缩包解压配额**（`core/archive.py`）：docx/xlsx 解析前按条目数（2000/500）、解压总量
    （200MB/100MB）、压缩比（100）判定并拒绝 zip 炸弹——仅校验压缩后大小挡不住「1MB 压缩包
    解压出数十 GB」的资源耗尽。
  - **首登改密服务端强制**（`core/deps.py`）：`must_change_password` 账号仅放行 `/auth/*` 与 `/meta`，
    其余接口 403 并带 `X-Must-Change-Password: 1`；前端据此静默处理（不弹错误提示），由不可关闭的
    改密弹框接管。此前仅前端弹框引导，直连 API 即可绕过。
  - **前端 Nginx 安全响应头**：`X-Frame-Options: DENY`（防点击劫持）、`X-Content-Type-Options`、
    `Referrer-Policy`、`Permissions-Policy`、`server_tokens off`；CSP 以 `Report-Only` 先观察
    （前端有运行时内联样式与 data: 图片，配置注释给出转强制与启用 HSTS 的条件）。

### 新增

- 一次性脚本 `backend/scripts/fix_attachment_paths.py`（置空存量非法附件路径）与
  `backend/scripts/fix_retest_title_html.py`（转义存量复测标题并重算 `retest_html`），
  均支持 `--dry-run` 且落库前备份到 `storage/backups/`。
- 后端测试：`test_storage_path_guard.py`（路径守卫与接口级回归）、`test_ssrf_guard.py`
  （出站目标判定与"不发起请求"断言）、`test_retest_title_sanitize.py`、`test_source_guard.py`
  （源码结构守卫：禁止附件路径裸拼接、禁止 `app/` 内直接出站、要求标题聚合转义）。

### 修复

- **升级后富文本图片全部不可见（图片鉴权引入的空窗，2026-09-19 生产实测）**：图片凭证是登录时
  下发的 `vp_img` Cookie，而**升级前就已打开的标签页**从未拿到该 Cookie，新版后端上线后这些会话的
  全部图片请求 401（表现为整页裂图，刷新页面即恢复）。处理：
  1. 前端新增 `utils/imageAuth.ts`——捕获阶段的图片加载失败监听，静默补发一次凭证
     （`GET /auth/me` 会续订 Cookie）并带时间戳重试原图一次；整页裂图只补发一次凭证（5s 节流），
     已重试过的图片不再重试；站外图片与未登录状态不触发；仅识别同源 `/storage/uploads/images/` 路径。
  2. `GET /auth/me` 已在每次进入页面时续订 Cookie（应用启动即调用），故正常整页加载不受影响。
  > 升级操作提示：图片鉴权首次上线后，请让在线用户**刷新一次页面**（或重新登录）；此后新版前端可自愈。
- `report_builder._drop_unresolvable_images` 的 img 标签匹配补全结束尖括号：整体移除不可内嵌
  图片时不再残留孤立的 `>`。
- **复测聚合标题回填脚本导入断链**：`scripts/backfill_retest.py` 仍从 `app.api.v1.vulns` 导入批次 D
  已迁走的 `_sync_vul_retest_html`，`upgrade.sh` 的 [4.5/5] 步骤只打印告警、现象被掩盖，手动执行才暴露
  `ImportError`（脚本不参与 pytest 收集，CI 无法发现）。已改为 `app.services.vul_service.sync_vul_retest_html`，
  并新增 `scripts/_check_imports.py` + `tests/test_source_guard.py::test_scripts_app_references_resolve`
  静态守卫脚本对 app 的引用。

## [2.18.0] - 2026-09-18

### 新增

- **影响URL 支持批量粘贴自动切分（录入漏洞 / 报告导入修正）**：新增共用组件
  `frontend/src/components/AffectedUrlEditor.vue`，在两个入口替换原「逐条点添加URL」的输入区。
  在任意一行粘贴含换行（LF/CRLF）或分号（`;`/`；`）的文本时，自动按分隔符切分、逐条 trim、
  丢弃空项、去重保序后插入当前行位置，并提示「已识别 N 条、已去重 M 条」；切分结果仍是逐条
  可编辑、可删除的输入行，可继续点「添加URL」补充。当前行内容被整段选中时按覆盖处理，否则
  保留原内容并在其后追加（不误删已填数据）；单值粘贴不接管默认行为，保留光标位置。
- 影响URL 解析与校验纯函数集中在 `frontend/src/utils/urls.ts`（`parseAffectedUrl` /
  `joinAffectedUrl` / `validateAffectedUrls`），与后端 `app/schemas/common.py` 的
  `normalize_affected_url` 同一口径；条数上限 100、单条上限 2048 字符，超限或条目含空白/
  非法字符时在字段下方行内提示（不弹窗、不清空表单），提交前同口径拦截。
- **漏洞录入「套用模板」支持跨模板全局搜索**：新增 `GET /knowledge/search`
  （`backend/app/api/v1/knowledge.py`），不预选漏洞类型即可按漏洞名称、编号（CVE 等，写在名称
  后缀）/ 参考链接 / 关键字（`deep=true` 时含描述、危害说明、修复建议正文）模糊检索全部模板；
  支持漏洞类型、危害等级、维护人、更新时间区间筛选与相关度（名称全等 > 前缀 > 包含 > 参考链接 >
  正文）/ 更新时间 / 危害等级 / 名称排序及分页，结果附带所属漏洞类型名称与描述摘要。
  新增 `GET /knowledge/{id}` 供套用前取完整正文；原 `GET /knowledge/by-type/{vul_type}`
  保持不变（`vul_type` 传当前类型即等价原有「模板内搜索」）。
- 前端新增跨模板搜索弹窗 `frontend/src/components/TemplatePickerDialog.vue`：默认作用域为
  「当前类型」（行为与旧版一致），可一键切「全部模板」；结果展示所属模板路径
  （漏洞模板库 / 漏洞类型 / 漏洞名称）、危害等级、维护人与更新时间，支持关键词高亮、筛选排序、
  分页、键盘上下选择与回车套用，当前类型无命中时提供「在全部模板中搜索」引导。
- 套用模板时若条目漏洞类型与当前漏洞卡片不一致，自动同步漏洞类型并提示（跨模板套用一致性）；
  新增 `frontend/src/api/knowledge.ts` 接口封装与 `frontend/src/utils/highlight.ts` 高亮工具。

### 变更

- **影响URL 存储由 `varchar(512)` 扩宽为 `TEXT`**（`vulns.affected_url`、`import_records.affected_url`，
  迁移 `d9e0f1a2b3c4`；SQLite 开发库因类型亲和无需重建，由 `db.py` 注释登记双轨）。写入时统一
  规范化：按换行与分号切分 → trim → 去空 → 去重保序 → 换行拼接。上限校验从数据库列下沉到
  schema 层（`VulIn` / `ImportRecordUpdateIn` / 春耕行动草稿共用 `AffectedUrl` 类型）。
  Word 解析器（`docx_parser.py`）移除了对影响URL 的 `[:512]` 硬截断，不再静默丢数据。
  注意：分号一律视为分隔符（含查询串内的分号），前端粘贴与后端入库行为一致。
- **漏洞命名域收口（内部一致性，无用户可见变化）**：`backend/app/services/vuln_service.py` →
  **`vul_service.py`**（8 文件 / 45 处引用同步，不留兼容壳）；`AGENTS.md` 的命名域规则修订为
  「实体域新增标识符统一 `vul_`」并附实测依据（`vul_id` 外键列 6 处 : `vuln_id` 1 处）与 6 项
  既成事实例外（字典域仍 `Vuln*`）。**不改动任何数据库列**。
- **前端列表页类型收敛**：全部列表页改为泛型 `useListPage<T>`（本次补齐 `UserList` / `TokenList` /
  `TestingPlanList` / `NotifyChannelList` / `NonpenPlanList` / `AuditLog`，累计 12 页），
  `pnpm typecheck` 保持 0 错误；纯类型改动，无运行时行为变化。
- **文档收口与治理规则成文**：删除 5 份已完成的任务型文档（代码审计报告、审计修复执行记录、
  备份优化方案、磁盘告警复盘、单次排查报告），其中有长期价值的结论归并到 `AGENTS.md`
  （函数体量口径与「合理长」保留形态、验收口径、文档治理规则）与 `DEPLOY.md`（§五 备份重写为
  「锚点 + 差异快照」、附「文件与磁盘」补磁盘排查双视角）。

### 修复

- **影响URL 录入约 20 条即触发 500**：根因是该列原为 `varchar(512)`，而前端把多条 URL 以换行
  拼成单个字段提交，约 20 条即溢出，PostgreSQL 在写入时抛 `StringDataRightTruncation`
  （SQLSTATE 22001），落入兜底 500 并由前端整页跳转错误页、丢失已填表单。除扩宽列与补齐
  长度校验外，`app/main.py` 新增 `DataError` 处理器把数据长度/数值越界类数据库拒绝归为 400
  并给出可读文案；`RequestValidationError` 处理器现会透出 schema 层自有校验（`value_error`）
  的中文提示，超限时返回 422 并说明具体原因（条数 / 条序号与长度 / 非法字符），不再是一句
  「请求参数校验失败」。
- 输出侧（`VulOut`）显式退回普通 `str`，不对历史数据跑写入校验，避免存量脏数据导致列表/
  详情接口 500。
- 移除套用模板弹窗中恒失效的 `tags` 匹配/展示分支（后端模板条目并无该字段）。
- **Redis 不可达时登录 / PAT 鉴权会无限挂起**：`app/core/ratelimit.py` 的 Redis 客户端未设连接/
  读写超时 —— 当 Redis 被防火墙 DROP（而非主动拒绝连接）时连接停在 TCP 握手，`try/except`
  的降级分支永不触发，登录失败计数与 PAT 限流整条鉴权链卡死（实测：全量测试卡在 PAT 限流用例）。
  现显式设置 2s 连接/读写超时（`VP_REDIS_TIMEOUT`），arq 连接池超时同源、重试收敛为 1 次
  （`conn_timeout` / `conn_retries`；worker 保留默认重试以容忍 Redis 短暂不可用），并新增
  `VP_DISABLE_REDIS` 供无 Redis 的单机与测试环境直接走进程内计数（不再依赖外部 Redis）。

## [2.17.1] - 2026-09-17

### 修复

- **工单「复测完成」误置（多漏洞 / 多报告场景）**：复测完成判定由「单份报告的章节漏洞」改为
  **工单全部关联漏洞**是否闭环（`backend/app/services/vuln_service.py::sync_plan_retest_state`，
  原 `sync_report_completion`）。此前工单含多份报告或多个漏洞时，单份报告全部闭环会把整单误置
  「复测完成」，出现「工单复测完成 + 仍有未修复漏洞」的矛盾状态；同时将进入「复测完成」的条件
  收紧为工单处于「提请复测(40) / 复测中(50)」。
- **补齐工单「复测完成」的回退触发点**：新增漏洞、批量提交、编辑漏洞变更关联工单、从漏洞库关联
  漏洞、生成报告（`api/v1/vulns.py`、`api/v1/testing_plan.py`、`api/v1/reports.py`）均按工单级
  口径重算——已闭环工单出现未闭环漏洞时回退「复测中」、清空复测完成时间并重开最近一轮复测。
- **报告导入「全部修复」判定口径对齐工单级**（`services/import_service.py`）：复测报告仅覆盖工单
  部分漏洞且本批全部标记修复时，不再把整单置为「复测完成」，工单状态在批次入库后按工单全部关联
  漏洞重算。
- **存量纠偏脚本** `backend/scripts/fix_plan_retest_state.py`：幂等扫描「复测完成但仍存在未闭环
  漏洞」的工单并回退「复测中」（支持 `--dry-run`，落库前备份至 `storage/backups/`）。

### 新增

- **工单流程抽屉「报告复测完成」标注**：`TestingPlanOut.reports[]` 新增派生字段
  `vul_total` / `vul_closed` / `all_closed`（`schemas/report.py::PlanReportBrief`、
  `services/plan_service.py::report_closure_map`，随工单列表 / 详情接口返回，不落库）；
  前端 `components/PlanWorkflowDrawer.vue` 报告区对「报告所含漏洞已全部完成（已修复 / 已忽略）」
  的报告追加「复测完成」标签，便于与仍有未闭环漏洞的报告区分。

---

## [2.17.0] - 2026-09-16

### 变更

- **工单状态改名（渗透测试工单 + 漏扫基线工单统一口径）**：渗透测试工单状态码 30「等待复测」调整为**「初测完成」**、
  40「复测申请」调整为**「提请复测」**（唯一字典源 `backend/app/constants.py` 的 `TESTING_PLAN_STATUS`）；
  漏扫基线工单测试项状态 `wait_retest` 同步由「等待复测」调整为**「初测完成」**（`constants.NONPEN_ITEM_STATUS`，
  状态码 / 状态键与流转规则均不变），两处字典均经 `/meta` 全端生效，前端流程抽屉文案与用户 / 开放 API 文档同步更新。
- Excel 导入兼容改名前导出的旧文案：`backend/app/services/plan_io.py` 的 `PLAN_STATUS_REVERSE`
  保留 `等待复测` / `复测申请` 两个历史别名，旧表格仍可正常入库。

---

## [2.16.0] - 2026-09-15

### 新增

- **自定义错误页（400 / 401 / 403 / 404 / 500 / 502 / 503 / 504）**：新增全屏错误页
  `frontend/src/views/ErrorPage.vue`（巨号状态码嵌入线稿图标 + 文案双栏，明暗双态、响应式、
  尊重 `prefers-reduced-motion`），状态码文案 / 图标 / 响应策略集中在 `frontend/src/utils/errorPage.ts`；
  未登记状态码按首位数字走 4xx / 5xx 通用模板，任意三位码都不会空白。
- **按状态码分档的错误路由**：未匹配路径由「静默重定向到 `/dashboard`」改为进入 `/error/404?from=<原路径>`；
  新增顶层公开路由 `/error/:code`（不继承主布局，未登录也可访问，避免 401 / 404 / 502 被守卫拦去登录页）。
- **请求级错误策略**：401 静默刷新失败 → 清理本地凭证并进入 401 页（保留 `redirect` 意图，登录后回到原页面）；
  403 页面级读取（GET/HEAD）进 403 页、行内写操作仅轻提示；5xx 进全屏错误页；400 / 404 / 422 / 429 保持轻提示；
  409 保持静默；断网等无响应场景仅提示。并发失败只跳一次，已在错误页时不重复导航。
- **前端全局兜底**：渲染 / setup 阶段异常统一落到 500 页（事件回调等阶段仅记录日志，保持原交互）；
  懒加载分包失败（新版本发布后旧 chunk 失效）先自动刷新一次，仍失败才进 500 页。
- 后台轮询请求豁免：导出记录轮询声明 `meta.skipErrorPage`，接口异常时不再清屏打断报告编辑。
- 后端统一错误响应体 `backend/app/main.py`：未捕获异常由 Starlette 默认纯文本 500 改为
  JSON `{"detail": "服务器内部错误，请稍后重试"}`（堆栈仅落服务端日志），请求校验失败（422）统一可读文案。

---

## [2.15.0] - 2026-09-15

### 新增

- **渗透测试工单搜索框支持工单ID**：列表搜索框（占位符「搜索系统 / 类型 / 部门 / 工单ID」）可按关键词匹配工单ID——
  手动指定值（如 `ZDDD-2026-001`）与其片段，以及自动编号 `YYYYMMDD-N`（完整值、日期段 `20260506`、序号段）均可命中。
  搜索口径集中在 `plan_query.plan_search_condition`，站内列表 / 统计 / 导出 / 结论输出与开放 API
  `GET /open/testing-plans` 一致（与漏扫基线工单 `nonpen_search_condition` 同口径）。

---

## [2.14.0] - 2026-09-11

远程检测表单关联资产台账与漏洞库：系统名称可关联资产并现场新增资产，漏洞改为「新增漏洞」录入并支持点击查看详情。

### 新增

- **远程检测关联资产台账**：表单新增「关联资产」选择器，支持远程搜索与空态 / 按钮现场「新增资产」
  （保存后自动选中）；选中后自动带出系统名称与部门，仍可手工修正。列表在系统名称后展示「部门」列
  （原「资产归属」列改名）与新增的**「资产归属」列**（`remote_testings.asset_belong`），区分部门归属与资产归属口径。
- **远程检测关联漏洞库**：表单「漏洞名称」调整为「新增漏洞」，可就地录入漏洞名称 / 等级 / 类型 / 来源，
  保存时随记录创建漏洞并关联（`remote_testings.vuln_id`）；列表「漏洞名称」列展示关联漏洞标题，
  点击即弹出漏洞详情（等级、类型、状态、影响 URL、描述、复现步骤、修复建议 + 查看完整详情）。
- **漏洞详情弹窗抽为公共组件** `frontend/src/components/VulnDetailDialog.vue`：渗透测试工单流程
  （`PlanWorkflowDrawer`）与远程检测共用同一交互与展示口径。
- 数据库迁移 `c7d8e9f0a1b2`：`remote_testings` 新增 `asset_id` / `vuln_id`（外键 + 索引）与 `asset_belong`，
  `app/db.py` 轻量迁移同轨补列（SQLite）。

### 变更

- 远程检测检索扩展：新增「资产归属」字段与关联漏洞标题参与模糊匹配。
- 保存时以关联漏洞为权威同步文本快照（`vuln_name` / `vuln_type`）；旧记录无关联时仍按原文本展示，不影响存量数据。

---

## [2.13.1] - 2026-09-11

### 修复

- **远程检测新建 / 编辑在 PostgreSQL 下报 500**：远程检测口径重构（`appeal_success` → `appeal_status`）时，
  迁移 `e5f6a7b8c9d0` 漏删旧列 `remote_testings.appeal_success`。该列在基线中为 `NOT NULL` 且无默认值、
  模型已不再映射，导致 PostgreSQL 下任何 `INSERT` 都触发 `NotNullViolationError`（SQLite 开发库因重建表
  逻辑不受影响，故此前未被发现）。新增迁移 `b4c5d6e7f8a9` 幂等删除该遗留列（列已不存在时自动跳过），
  并在 `app/db.py` 轻量迁移中同步兜底；新增 `tests/test_schema_consistency.py` 守卫「模型 / Alembic /
  SQLite 轻量迁移」三处对废弃列的处理口径。

---

## [2.13.0] - 2026-09-10

漏洞模板库内容全面优化：CVE 命名规范、多漏洞组件拆分、描述与修复建议增强，并提供幂等同步脚本。

### 新增

- **模板库同步脚本** `backend/scripts/sync_knowledge_templates.py`：以 `backend/knowledge-import-vulnerabilities.json`
  为唯一权威数据源，按漏洞名称 upsert；`--prune` 清理改名 / 合并后的残留条目，`--dry-run` 仅打印差异。
  幂等可重跑，入库前统一过 `sanitize_html` 消毒并校验字典码。
- **模板库数据完整性测试** `backend/tests/test_knowledge_templates.py`：固化名称唯一性、编号修复建议、
  CVE 命名格式、多漏洞组件拆分、参考链接来源等要求。

### 变更

- **模板数据集扩充为 135 条**（`backend/knowledge-import-vulnerabilities.json`，含 33 条带 CVE 编号）：
  - **CVE 编号入名**：有明确编号的漏洞名称统一为「名称（CVE-YYYY-NNNN）」，如
    `Fastjson 1.2.24反序列化命令执行（CVE-2017-18349）`、`Apache Shiro认证绕过（CVE-2020-1957）`；
    无 CVE 的组件漏洞沿用官方 / 威胁情报编号（`Nacos默认密钥权限绕过（QVD-2023-6271）`、
    `MariaDB认证远程代码执行（QVD-2026-48306）`）。
  - **多漏洞组件拆分**：`Fastjson反序列化` 拆为 1.2.24（CVE-2017-18349）与 autoType 绕过（CVE-2022-25845）；
    `Shiro反序列化` 拆为 rememberMe 反序列化（CVE-2016-4437）与认证绕过（CVE-2020-1957）；
    `Nacos权限绕过/默认密钥` 拆为 CVE-2021-29441 与默认密钥两条；`目录遍历/列目录`、`目录暴露` 修正为
    「路径遍历（目录穿越）」与「目录列表（目录浏览）」两条单一漏洞模板。
  - **描述与修复建议增强**：补全「原理 + 触发条件 + 影响版本」；修复建议多条时统一按
    `<p>1、…</p><p>2、…</p>` 编号换行；参考链接改用先知社区 / FreeBuf / 安全内参 / 绿盟 / 启明星辰 /
    阿里云·腾讯云安全 / 官方通告 / NVD 等。
  - **重点组件漏洞扩充（新增 41 条）**：覆盖天清汉马 VPN、Apache Tomcat、NGINX、Kubernetes（k8s）、
    MySQL、GreatDB、MariaDB、MongoDB、ZooKeeper、Redis、Nacos、RabbitMQ、MinIO、React/Next.js、
    Dify、FastAPI(Starlette)、JeecgBoot，并纳入截至发布时的最新漏洞，如
    `Nacos 3.x权限绕过（鉴权作用域错配）`（3.0.0–3.2.3）、`React Server Components远程代码执行（CVE-2025-55182，React2Shell）`、
    `Next.js React Server Components远程代码执行（CVE-2025-66478）`、`JeecgBoot积木报表未授权远程代码执行`、
    `NGINX rewrite模块堆缓冲区溢出远程代码执行（CVE-2026-42945）`、`Apache Tomcat Tribes集群反序列化远程代码执行（CVE-2026-34486）`、
    `Kubernetes(k8s) Ingress-NGINX未授权远程代码执行（CVE-2025-1974）`、`Redis Lua沙箱逃逸远程代码执行（CVE-2025-49844）`、
    `MongoDB未授权内存信息泄露（CVE-2025-14847）`、`MinIO服务账号与STS权限提升（CVE-2025-62506）`。
- **预置数据单源化**：`scripts/seed_knowledge.py` 改为直接读取上述 JSON（`SEED_DATA` 现携带富文本 HTML），
  `scripts/seed_dev_data.py` 同步改为 HTML 原样入库，消除两份模板数据源不一致的问题。
- **模板列表预览可读性**（`frontend/src/views/KnowledgeList.vue`）：列表「标准描述 / 修复建议」列提取纯文本时
  在块级元素间补换行，「1、2、3」编号建议不再黏连成一行。

### 移除

- 清理名称优化产生的 4 条历史残留条目（`Fastjson反序列化`、`Shiro反序列化`、`目录暴露`、`目录遍历/列目录`），
  由 `sync_knowledge_templates --prune` 幂等完成。

### 测试

- `pytest tests/test_knowledge_templates.py` 6 项通过；WSL-Kali docker 容器内对 PostgreSQL 实测同步：
  先后完成基础优化（新建 33 / 更新 60 / 清理 4，库内 93 条）与重点组件扩充（新建 41 条）及别名命名调整
  （新建 6 / 清理 5），最终库内 **135 条**（33 条含 CVE）；再次 `--dry-run` 为「新建 0 / 清理 0」，验证幂等。
- 页面实测（admin1 登录）：模板库 135 行，18 个重点关注组件均可检索到对应模板。

---

## [2.12.3] - 2026-09-10

修复 2.12.2 内置的存量数据维护脚本在 `--dry-run` 下崩溃的问题。

### 修复

- **`scripts.fix_retest_section_dup --dry-run` 抛 `MissingGreenlet`**（`backend/scripts/fix_retest_section_dup.py`）：
  试运行分支在 `await session.rollback()` **之后**才逐条打印章节信息，而 rollback 会使会话内 ORM 实例全部过期，
  此后再访问 `s.id` / `s.report_id` / `s.content_html` 等属性会触发同步 IO，在异步会话中直接抛
  `sqlalchemy.exc.MissingGreenlet`（VPS 上以 `docker compose run --rm api ...` 执行时必现；本地因当次未跑到该分支而漏检）。
  现改为在扫描阶段先把 `id` / `report_id` / `vul_id` / 原文 / 新值取出为普通 dict（同一份数据复用于备份文件），
  打印与备份均只读该纯数据快照，不再触碰 rollback 后的 ORM 实例。

  > 该失败发生在任何写库动作之前（试运行本就不提交），**不会污染数据**；
  > 省略 `--dry-run` 直接执行正式清理的路径不受影响。

### 测试

- 本地容器复现：临时注入一条「正文尾部内嵌复测详情」的旧格式章节 →
  `--dry-run` 正常打印该章节长度变化（573 → 527 字符）→ 正式清理后内容精确还原为注入前原文、内嵌标记消失。

---

## [2.12.2] - 2026-09-10

修复报告导入漏洞等级误判与复测详情重复/遗漏两类问题。

### 修复

- **报告导入漏洞等级被误判为中危**（`backend/app/services/docx_parser.py`）：
  - **标签与值同段未被识别**：解析器只认「独立标签行」，`漏洞等级：高危`、`漏洞链接：\n1. http://…` 这类写法会被整段丢弃，导致详情章节的权威等级与漏洞链接丢失；
  - **汇总表模糊匹配过宽**：旧实现按「公共字符集合大小 ≥ 4」匹配，`RSA私钥泄露` 会误配到 `前端JS泄露SM4加密密钥`（公共字符 `{S,泄,露,钥}`）而取到中危；匹配失败时又静默回落中危；
  - **等级来源优先级倒置**：改为 **风险问题详情等级 > 风险问题汇总匹配等级 > 中危兜底**，并记录 `level_source` / `level_mismatch` / 两处原始等级文字；汇总匹配改为「最长公共子串 + 相似度 + 唯一候选」双校验（歧义视为未命中）。
- **复测详情在章节正文尾部重复且导出遗漏最新结果**（`backend/app/services/report_html.py`、`report_builder.py`、`api/v1/reports.py`）：
  - 根因是同一份复测详情被双份存储——`vuln_section_html` 曾把 `vulns.retest_html` 追加为章节正文的最后一个元素，其后的复测更新只写漏洞字段、章节快照永不刷新；导出时又因「正文已含复测详情」跳过追加，导致导出始终停留在旧快照；
  - 现改为**以 `vulns.retest_html` 为唯一权威来源**：章节快照不再内嵌复测详情，导出前统一剥离历史内嵌段（保留其后的手工追加内容）并在正文末尾追加一次；发起复测复制章节时同步剥离继承段。

### 新增

- **导入等级不一致提醒**：新增 `GET /imports/level-mismatches` 返回待入库批次中汇总表与详情等级不一致的记录（含实际入库等级与两处原始等级）；导入预览页自动弹窗提醒并保留警示横幅，批量确认对话框在入库前强制确认一次（新增前端组件 `ImportLevelMismatchDialog.vue`）。
- **存量数据清理脚本** `backend/scripts/fix_retest_section_dup.py`：幂等剥离存量报告章节正文尾部内嵌的复测详情副本（支持 `--dry-run`），清理前无需备份复测内容（以 `vulns.retest_html` 为准）。
- **数据库迁移** `a4b5c6d7e8f9`：`import_records` 新增 `level_source` / `level_summary_text` / `level_detail_text` / `level_mismatch`（SQLite 开发库由 `db.py` 轻量迁移同步）。

### 测试

- `backend/tests/test_parser.py`：同行标签解析、详情等级优先、等级不一致标记、无来源兜底、占位行不误取、汇总匹配拒绝弱重合 6 个用例
- `backend/tests/test_report_builder.py`：章节快照不含复测详情、内嵌段剥离规则、导出复测详情唯一且为最新 4 个用例
- `backend/tests/test_api.py`：等级不一致记录标记与提醒接口、报告章节不内嵌复测详情

---

## [2.12.1] - 2026-09-09

修复渗透测试工单流程抽屉中历史导入漏洞排序与原报告序号不一致的问题。

### 修复

- **流程抽屉历史漏洞排序错乱**：工单流程「漏洞」列表按 `level + submit_time + id` 排序，历史导入漏洞（2.11.1 修复前生产 PostgreSQL 无序处理入库）`submit_time` 全同（报告日期 14:00）、id 已按错位顺序生成且不可回改，同等级内顺序仍乱。现新增导入解析序号纠偏，无需改动存量数据：
  - **后端**（`backend/app/api/v1/testing_plan.py`）：新增 `GET /testing-plans/{row_id}/vuln-order`，返回工单关联漏洞的导入解析序号映射 `{vul_id: seq}`（取各漏洞在导入批次中的最小 `seq` 即首次导入顺序）
  - **前端**（`frontend/src/components/PlanWorkflowDrawer.vue` + 新增 `frontend/src/utils/vulnOrder.ts`）：流程抽屉同等级内优先按导入序号（原报告序号）排序，非导入漏洞回退录入时间 / id 兜底（原行为）

### 测试

- `backend/tests/test_api.py`：导入报告后断言 `vuln-order` 映射的 seq 顺序与漏洞 id 顺序一致
- `frontend/src/utils/__tests__/vulnOrder.spec.ts`：等级分组 / seq 纠偏 / 无映射兜底 / 混合场景 5 个用例

---

## [2.12.0] - 2026-09-09

审计日志与漏洞操作日志显示用户姓名（realname），详情页与报告编辑页滚动分离及章节导航快捷定位。

### 新增

- **日志展示名（realname）**：`OperationLogOut` / `VulLogOut` 新增 `realname` 字段；`audit_service` 新增 `resolve_realnames` 批量按 `user_id`（优先）/ `username`（兜底，覆盖登录失败等 `user_id` 为空记录）解析用户姓名；`audit.list_logs` 与 `vulns.vuln_logs` 填充 `realname`，未设置时前端回退用户名（`AuditLog.vue`、`VulnDetail.vue` 操作日志）
- **详情页滚动分离**（`frontend/src/views/VulnDetail.vue`、`MainLayout.vue`）：漏洞详情改为正文与右侧（状态流转 + 操作日志）各自独立滚动（`h-full` 撑满主区），页面整体不再随内容滚动；主区容器补 `h-full`
- **报告编辑章节导航快捷定位**（`frontend/src/views/ReportEditor.vue`）：章节导航头部新增「滚动到顶部 / 底部」按钮，一键平滑滚动正文区（`contentScrollRef`）

### 测试

- `backend/tests/test_api.py`：审计 / 漏洞日志断言 `realname` 存在，且 admin（姓名「管理员」）记录正确返回 `realname`

---

## [2.11.1] - 2026-09-09

修复报告导入后漏洞与章节顺序与原报告不一致的问题（章节导航乱序）。

### 修复

- **导入章节乱序（根因）**（`backend/app/services/import_service.py`）：确认入库的解析记录查询此前无 `ORDER BY`，生产 PostgreSQL 返回顺序不定，导致章节 `order` 按乱序写入——报告编辑页「章节导航」与导出 Word 章节顺序与原报告不一致。现严格按解析序号 `ImportRecord.seq`（文档顺序）处理，SQLite 开发环境行为不变
- **漏洞列表默认顺序不稳定**（`backend/app/api/v1/vulns.py`）：默认排序仅 `submit_time` 倒序、无同值兜底；报告格式导入的漏洞提交时间全部相同（报告日期 14:00），顺序由数据库物理顺序决定。现默认排序补 `id` 升序兜底，同批次漏洞按原报告序号稳定展示
- **存量数据修复脚本**（`backend/scripts/repair_report_section_order.py`）：按 `import_records.vul_id → seq` 重排历史导入报告的章节顺序（幂等，支持 `--dry-run`），修复已升级生产环境的乱序报告

### 变更

- **全站分页页长选项**（`frontend/src/components/TlPagination.vue`）：页长选项由 `[20,50,100]` 扩展为 `[10,15,20,50,100]`
- **侧栏折叠与主区宽度**（`frontend/src/layouts/MainLayout.vue`）：折叠切换改为单按钮按状态切换图标（避免折叠态双图标）；主内容区最大宽度由 1400px 提升至 1920px 封顶居中，≥1536px 时内边距同步放大（MASTER.md 6.2）

---

## [2.11.0] - 2026-09-03

开放 API 新增工单读写（渗透测试工单 / 漏扫基线工单），与站内口径一致。

### 新增

- **开放 API 工单读写**（`backend/app/api/v1/open_plans.py`）：`/open/testing-plans`、`/open/nonpen-plans` 支持查询（过滤/分页/排序，复用 `plan_query.plan_conditions`，与站内列表同口径）、创建、全量更新；认证仅接受个人访问令牌 PAT（`get_pat_user`，JWT 拒绝），读不做数据归属过滤、写按令牌所属用户角色权限校验 `special:manage`（`require_pat_perm`，与站内 `require_perm` 同口径），避免个人令牌绕过 RBAC；写入逻辑复用 `services/plan_crud`，工单ID分配、状态流转校验、联动同步与统计重算口径不漂移
- **工单 CRUD 服务抽取**（`backend/app/services/plan_crud.py`）：从站内路由（`testing_plan.py`、`nonpen.py`）抽取建/改工单逻辑，站内与开放 API 共用同一实现
- **开放 API 指南**（`docs/OPEN_API_GUIDE.md`）：PAT 调用漏洞/态势（只读）与工单（读写）的认证、接口清单、参数、响应、错误码及 curl/Python/JS 示例（含每令牌每分钟 120 次限流 `PAT_RATE_LIMIT`）
- **Markdown 渲染工具**（`frontend/src/utils/markdown.ts` + `markdown.spec.ts`）：基于 markdown-it、原始 HTML 转义（可安全 v-html），用于访问令牌页指南抽屉渲染 `OPEN_API_GUIDE.md`；`TokenList.vue` 接入
- **构建上下文调整**：`docker-compose.yml` 前端 build context 提至仓库根、`frontend/Dockerfile` 新增 `.dockerignore`，使令牌页 `?raw` 可导入 `docs/OPEN_API_GUIDE.md`（含 `README.md`/`README_EN.md` 同步说明）

### 变更

- `backend/app/constants.py` 审计动作新增 `plan_create` / `plan_update`；`backend/app/core/deps.py` 新增 `require_pat_perm`；`__init__.py` 注册 `open_plans` 路由；`backend/tests/test_api.py` 补充开放工单接口用例

---

## [2.10.3] - 2026-09-01

审计日志来源信息修正：真实客户端 IP 解析与代理头透传。

### 修复

- **审计日志来源 IP 全为容器内网 IP**：生产链路 `浏览器 → Nginx(frontend 容器) → api 容器` 下，后端直接读 `request.client.host`（uvicorn TCP 对端）恒为 Nginx 容器内网 IP；且前端 Nginx 仅透传 `X-Real-IP`、未设 `X-Forwarded-For`，uvicorn 亦未开启 proxy-headers。新增统一解析模块 `backend/app/core/client_info.py`（`get_client_ip` / `get_user_agent`）——`X-Forwarded-For` 从右往左跳过内网/保留段取首个公网地址，兼容多层代理与 XFF 伪造防护，全内网场景退化取最近一跳；审计日志（`backend/app/services/audit_service.py`）与登录防爆破（`backend/app/api/v1/auth.py`）统一改用真实来源 IP
- **登录防爆破锁粒度失效**：失败计数 key 此前取同一容器 IP，所有用户共享一把锁；修复后按真实来源 IP 隔离计数
- **前端 Nginx 代理头补全**（`frontend/nginx.conf`）：`/api/` 与 `/storage/uploads/images/` 增加 `X-Forwarded-For $proxy_add_x_forwarded_for` 与 `X-Forwarded-Proto $scheme` 透传；外层如仍有代理（宿主 Nginx / 云 LB / CDN）需同样追加，方可还原最外侧真实 IP
- **补单元测试**（`backend/tests/test_client_info.py` 新增）：覆盖单层/多层代理、伪造 XFF、IPv4/IPv6 带端口剥离、全内网退化等 13 例；`pytest` 全量 84 passed

> **历史数据说明**：存量 `operation_logs.ip` 为容器内网 IP，请求链路未留痕，无法恢复真实来源；如需兜底可将内网网段 IP 统一标记占位，详见运维口径。UA 若无代理篡改则历史记录准确。

---

## [2.10.2] - 2026-09-01

系统类型拼写修正与漏洞统计子系统展示。

### 修复

- **系统类型「DCIT」拼写修正为「DICT」**（`backend/app/db.py` / `backend/app/models/business.py` / `backend/app/schemas/asset.py` / `backend/scripts/seed_dev_data.py`）：字典预置、模型/入参注释与开发种子数据统一为「DICT系统」

### 变更

- **漏洞统计透视表子系统列**（`backend/app/api/v1/vulns.py` / `frontend/src/views/VulnList.vue`）：按资产聚合时取 `sub_system`，系统列展示「系统-子系统」（如「营销活动平台-优惠券中心」，子系统为空则仅系统名）
- **漏洞统计概览默认闭合**（`frontend/src/views/VulnList.vue`）：顶部统计概览默认收起（与渗透/漏扫工单统计概览一致），移除 localStorage 展开态记忆

---

## [2.10.1] - 2026-09-01

登录页版本号构建期注入与登出跳转收敛。

### 变更

- **登录页版本号构建期注入**（`frontend/vite.config.ts` / `frontend/src/vite-env.d.ts` / `frontend/src/views/Login.vue`）：右下角版本号由硬编码 `v2.8.0` 改为构建期从 `package.json` 注入（`__APP_VERSION__`），随前端版本号自动同步；footer 文案去除「内置 admin 登录」
- **登出跳转收敛到 store**（`frontend/src/stores/auth.ts` / `frontend/src/layouts/MainLayout.vue`）：`logout()` 统一在 store 内 `router.replace('/login')`，移除 MainLayout 两处手动 `router.push('/login')`，避免重复跳转
- **结论面板默认收起**（`frontend/src/views/TestingPlanList.vue`）：「结论输出」折叠面板默认收起（`conclusionPanel` 默认 `[]`）
- **发布约定补充**（`AGENTS.md` / `docs/RELEASE.md` / `backend/app/core/config.py`）：登录页版本号由前端构建时注入，随 `package.json` 的 `version` 自动同步，无需单独维护

---

## [2.10.0] - 2026-09-01

备份提速与容灾优化：多线程压缩 + 差异快照 + 迁移锚点，升级备份提速 60%+、磁盘稳态 ≤8GB。

### 新增

- **差异快照备份**（`scripts/backup-incremental.sh` 新增）：基于最近迁移锚点的硬链接差异（`rsync --link-dest`），只存变化文件，秒级完成；无基线时自动降级为锚点
- **迁移锚点**（`scripts/backup.sh` 改造）：自包含全量备份，zstd 多线程压缩 + db/storage 并行，解包差异基线，保留最近 3 份
- **备份公共库与告警**（`scripts/backup-common.sh` / `scripts/notify.sh` 新增）：flock 互斥锁、zstd 优先/gzip 回退、SHA256 校验、MANIFEST 完成标记、webhook 告警
- **升级异步备份**（`scripts/upgrade.sh`）：升级前备份后台执行，与镜像重建并行；新增 `--anchor` 参数（MAJOR 发版生成全量锚点）
- **cron 一键安装**（`scripts/install-cron.sh` 新增）：幂等安装每日差异快照 + 每月锚点定时任务
- **备份优化设计文档**（`docs/BACKUP_OPTIMIZATION.md` 新增）

### 变更

- **恢复脚本兼容 zstd**（`scripts/restore.sh`）：支持 .zst/.gz 双格式，兼容历史平铺备份目录与锚点/快照两种源

### 修复

- **备份压缩瓶颈**：storage 上传文件由容器内 gzip 单线程改为宿主机 zstd 多线程，1.7GB 备份提速约 3~5 倍

---

## [2.9.0] - 2026-09-01

渗透测试工单「初测完成时间」筛选与「结论输出」：按时间范围筛工单，一键生成通报结论文字与整改情况附件。

### 新增

- **初测完成时间筛选**（`backend/app/api/v1/testing_plan.py` / `backend/app/services/plan_query.py`）：列表 / 统计 / 导出接口新增 `first_test_from` / `first_test_to` 参数，`plan_conditions` 支持按「初测完成时间」区间过滤
- **结论输出（通报汇总）**（`backend/app/services/plan_query.py` `compute_conclusion` / `plan_io.py` `build_conclusion_workbook`）：`GET /testing-plans/conclusion` 按筛选条件聚合生成结论文字（N 个部门 N 个系统、存在漏洞/未发现风险、已整改/整改中统计）与附件行数据；`GET /testing-plans/conclusion/export` 下载「整改情况附件.xlsx」（工单ID / 所属部门 / 测试系统 / 漏洞数 / 测试类型 / 整改完成情况）
- **时间范围快捷项**（`frontend/src/utils/dateRange.ts` + `__tests__/dateRange.spec.ts`）：今天 / 本周 / 上周 / 本月 / 上月 / 自定义六档，周一起始口径（`mondayOf`），`computeDateRange` 计算起止日期
- **工单列表时间范围与结论面板**（`frontend/src/views/TestingPlanList.vue`）：工具栏新增时间范围下拉 + 自定义日期选择器（初测完成起/止）；新增「结论输出」折叠面板（结论文字卡片 + 部门/系统/漏洞/整改 7 张 StatCard + 复制结论 / 下载附件）

### 修复

- **前端镜像构建 corepack 超时**（`frontend/Dockerfile`）：corepack 下载 pnpm 本体默认走 registry.npmjs.org，海外源不可达导致 `ETIMEDOUT`；构建时指定 `COREPACK_NPM_REGISTRY` 走国内镜像，与依赖源一致

---

## [2.8.2] - 2026-09-01

备份保留策略与升级缓存清理：响应 VPS 磁盘空间告警，防止 BuildKit 缓存无限累积与备份冗余。

### 变更

- **备份保留策略**（`scripts/backup.sh`）：备份后自动每日去重（每天保留最新一份）+ 保留最近 `BACKUP_KEEP_DAYS` 天（默认 30）；目录名即时间戳（YYYYmmdd_HHMMSS），字符串排序即时间排序
- **升级构建缓存清理**（`scripts/upgrade.sh`）：重建镜像后清理过期 BuildKit 缓存（`docker builder prune --filter "until=168h"`，保留最近 7 天），清理失败不阻断升级
- **事故复盘文档**（`docs/INCIDENT-20260831-disk-space.md`）：VPS 磁盘空间告警排查复盘，根因为 BuildKit 构建缓存无限累积（12.95GB，可回收 12.47GB）

---

## [2.8.1] - 2026-08-31

favicon 品牌色对齐与运维脚本补充。

### 变更

- **favicon 品牌色对齐**（`frontend/public/favicon.svg`）：图标由旧靛蓝盾牌改为薄荷绿几何图标，与 2.8.0 demo-2 品牌主色（#10b981）一致
- **运维脚本**（`scripts/`）：新增 `disk-usage.sh`（磁盘占用分析：按占用降序输出前 N 大目录/文件，另列大于阈值的大文件，结果写终端与日志）、`swap-manager.sh`（一键开启/关闭 4GB swap，含状态查询与开机自动挂载管理）

---

## [2.8.0] - 2026-08-31

前端 UI 按 demo-2（Linear Dark）全面重写：令牌层换薄荷绿/绿调近黑、全局框架与 15 个视图统一骨架、新增 ⌘K 命令面板与全局搜索接口。

### 新增

- **⌘K 命令面板**（`frontend/src/components/CmdPalette.vue`，挂载于 `MainLayout`）：Ctrl/Cmd+K 全局唤起，↑↓↵esc 键盘导航；支持页面跳转（与侧边栏同源、按权限显隐）、动作（明暗切换）与全局搜索（防抖调用后端接口，无权限分区静默为空）；顶栏新增搜索入口按钮（含 ⌘K 键位提示）
- **全局搜索接口**（`backend/app/api/v1/search.py`，`GET /api/v1/search?q=`）：跨漏洞/资产/渗透测试工单/漏扫基线工单/报告标题模糊聚合，分组各返回最近 5 条；资产/工单/报告分区跟随 `asset:manage` / `special:manage` / `report:manage` 权限（或通配符）
- **组件层**（`frontend/src/components/`）：`StatCard v2`（语义点标 + meta 行 + 出血式迷你趋势线插槽，统一原 Dashboard 内联自绘与 3 处旧版并存）；`SparkLine`（Catmull-Rom 平滑 SVG 迷你趋势线，替代 Dashboard 曾用的 9 个 ECharts spark 实例）；`TlPagination`（统一分页 layout [20,50,100]，替换全站两种流派共 18 处）；`FilterToolbar`（列表筛选工具栏容器：弹性搜索框 + 等宽字典筛选 + 右侧按钮组）
- **colors.ts 主题感知 tone 映射层**：后端 `/meta` 下发浅色版字典色（导出文档同为浅色口径），`html.dark` 时前端自动映射 demo-2 降饱和变体（五级/状态约 11 码精确映射，未收录色值走通用提亮），`MutationObserver` 保证切换主题后已渲染标签实时重渲染；新增 `dotStyle()` 点标助手

### 变更

- **设计令牌全面替换**（`frontend/src/style.css` / `tailwind.config.js`）：品牌主色靛蓝→薄荷绿（亮 #059669 / 暗 #34D399，主按钮薄荷底+深墨字）；暗色底 GitHub 系→绿调近黑（#0A0E0C 系）；圆角体系 EP 控件 7px / 卡片 10px / 浮层 12px，全站 35 处 `!rounded-lg` 覆盖清零；基准字号 13.5px + 语义阶梯（11/12/13.5/14/16/26），数字统一等宽字体；删除全局 `.el-card:hover` 上浮+靛蓝光晕；删除假 Inter 字体声明改系统栈；新增滚动条 / `::selection` / `.dot-tag` / `.ktag` / `.kbd` / `.num` 全局类；`.tl-tag` 胶囊改方角 5px
- **全局框架**（`frontend/src/layouts/MainLayout.vue`）：侧边栏 224px 平铺分组（漏洞运营/资产管理/专项管理/系统管理 10.5px 分组标签）+ 紧凑导航项 + 底部用户信息块；顶栏 50px 毛玻璃（面包屑 + 工具栏式标题 + ⌘K 入口）；主区 20/28/48 内边距 + 最大 1400px 居中；折叠持久化键迁移 `sidebarCollapsed`（兼容读旧键）
- **15 个视图统一骨架**：工具栏独立（FilterToolbar）+ 表格卡片 + TlPagination 三段式；selection 列统一 40、序号列 64、操作列收敛 120/160 两档并全局套 `.op-col` 紧凑样式；表格行内等级/状态改「色点+文字」dot-tag、漏洞类型改 ktag 中性方角签（`AGENTS.md` 新规范）；搜索框统一弹性 175-250px；5 个缺 flex-wrap 的工具栏补齐
- **换行混乱治理**：资产 URL 列「等 N 条」改 +N popover 全量展开、角色权限列/通知订阅事件列/春耕网络层级与危害程度列「前 N 个 + +N popover」、导入预览 URL 补 `min-w-0` 截断保护、报告标题列补 tooltip
- **弹窗宽度归档三档 480/640/800**：用户权限查看与令牌展示 560→640、渗透测试工单 22 项大表单 640→800、漏洞详情动态宽 720→800
- **字典展示色切换 demo-2 浅色版**（`backend/app/constants.py`）：五级风险/漏洞状态/工单状态/资产/报告/导入导出/非渗透测试项全部色值更新（导出 docx/xlsx 同源生效）
- **图表主题**（`frontend/src/utils/chartTheme.ts`）：PALETTE 薄荷绿打头、明暗轴/网格/tooltip 对齐令牌、删除无引用的 `barGradient`；Dashboard 布局改 2fr/1fr 非对称、状态分布饼图改堆叠条+图例、类型 Top10 改 CSS 横条、图表内 6 处写死色改令牌
- **登录页薄荷绿重写**（`frontend/src/views/Login.vue`）：绿调近黑底 + 薄荷光晕 + 玻璃卡，登录按钮薄荷底深墨字（≥4.5:1）

### 测试

- `backend/tests/test_api.py`：`/meta` 色值断言更新为新色板；新增 `test_global_search`（空关键字空分组、漏洞标题命中、资产名命中）
- `frontend/src/utils/__tests__/colors.spec.ts`：色板夹具与断言更新；新增 `dotStyle` 输出与暗色 tone 映射（精确映射 + 通用提亮）用例
- 全量验证：后端 `pytest` 109 passed；前端 `vitest` 69 passed；`vite build` 通过

---

## [2.7.0] - 2026-08-30

春耕行动增强与英文文档：工单表单内联录入漏洞、新增预估扣分/资产认定原因字段、原始报告附件上传解析入库，漏洞搜索支持系统名称，README 双语化。

### 新增

- **春耕行动「涉及漏洞」内联新增**（`backend/app/services/vuln_service.py` / `frontend/src/views/SpringActionList.vue`）：表单内直接快速录入新漏洞（名称/等级/类型），来源固定为「春耕行动」，保存时创建并自动关联选中（`create_vul_drafts`）
- **春耕行动「预估扣分」字段**（`est_score_deduction`，迁移 `b3c4d5e6f7a8_add_spring_action_est_score_deduction.py`）：列表与表单中位于「最终扣分」前一列，便于比对申诉/复核前后的扣分差异
- **春耕行动「资产认定原因」字段**（`asset_reason`，迁移 `c5d6e7f8a9b0_add_spring_action_asset_reason.py`）：列表与表单中位于「申诉结果」前一列，记录对应系统资产归属的认定依据
- **原始报告附件上传解析入库**（`backend/app/api/v1/spring_action.py`，迁移 `d6e7f8a9b0c1_add_spring_action_report_file.py`）：`POST /spring-actions/upload-report` 上传原始报告（.docx ≤ 50MB）解析回填系统名称/年度、勾选导入报告漏洞（保存时创建并关联，来源固定为「春耕行动」），附件留档；`GET /spring-actions/{id}/report` 下载附件
- **春耕行动列表新增「网络层级」「危害程度」两列**（`frontend/src/views/SpringActionList.vue`）：位于「涉及漏洞」前，按关联漏洞聚合去重展示（所在层/漏洞等级）
- **漏洞搜索支持系统名称**（`backend/app/services/vuln_service.py` / `backend/app/api/v1/vulns.py` / `frontend/src/views/VulnList.vue`）：关键词除标题/URL 外命中关联资产（系统）名称，搜索框占位改「搜索标题 / 系统 / URL」
- **英文 README**（`README_EN.md` 新增，`README.md` 重写）：项目双语说明，含平台命名由来、功能清单与快速开始

### 变更

- **UI 设计规范升级**（`AGENTS.md`）：风格改为 Linear 式暗色优先极简（视觉基准 `design-demos/demo-2`，本地设计稿不入库）；品牌主色由靛蓝改为薄荷绿（浅色 #059669 / 暗色 #34D399）；密度双档（正文 14px / 紧凑 13.5px）；表格行内等级/状态改用「色点 + 文字」dot-tag 变体；新增命令面板（⌘K/Ctrl+K）与 StatCard 迷你趋势线约定
- **输入框占位文字省略号**（`frontend/src/style.css`）：`.el-input__inner` 加 `text-overflow: ellipsis`，长占位文案截断为 …
- **漏洞筛选日期框溢出修复**（`frontend/src/views/VulnList.vue`）：daterange 编辑器补 `box-sizing: border-box`，修复 width:100% 下左右内边距撑出 20px 溢出面板
- `.gitignore` 忽略 `design-demos/`（本地 UI 设计稿，勿入库）

### 测试

- `backend/tests/test_api.py` 扩展 `test_special_modules_crud`：`asset_reason`/`est_score_deduction` 断言、原始报告非 docx 拒绝、无漏洞表 docx 留档解析空草稿、附件绑定+漏洞草稿保存创建（`source=20`）与下载、收尾清理导入漏洞
- `backend/tests/test_api.py` 新增 `test_vuln_search_by_system_name`：系统名称命中关联漏洞、标题命中回归

---

## [2.6.0] - 2026-08-28

角色（权限）管理：新增独立权限管理页，权限点按功能模块分组目录化下发，菜单按权限点精细分组。

### 新增

- **权限管理页**（`frontend/src/views/RoleList.vue`，`user:manage`）：独立「权限管理」页面，列出全部角色并编辑其权限点勾选；新增用户与权限端点 `GET /users/roles/permissions/catalog` 返回按模块分组的权限目录（含中文名与说明），供分组勾选与说明展示（`backend/app/api/v1/users.py`）
- **权限目录化**（`backend/app/constants.py`）：`PERMISSIONS` 由扁平列表升级为 `PERMISSION_CATALOG`（每项含 `key`/`label`/`group`/`desc`，按「态势总览 / 资产与组织 / 漏洞管理 / 报告中心 / 专项工作 / 系统管理」分组）；`PERMISSIONS` 改为由目录派生的扁平 key 列表，权限校验与 `/meta` 下发保持兼容。新增响应模型 `PermissionItemOut` / `PermissionGroupOut`（`backend/app/schemas/auth.py`）

### 变更

- **系统管理菜单按权限分组**（`frontend/src/layouts/MainLayout.vue` / `frontend/src/router/index.ts`）：「用户管理」「权限管理」归入 `user:manage` 可见，「审计日志」「通知渠道」归入 `system:manage` 可见；用户与权限页标题由「用户与权限」改为「用户管理」，新增「权限管理」路由
- **用户管理页重构**（`frontend/src/views/UserList.vue`）：角色分配与权限展示交互整理，与权限管理页职责分离
- **报告列表交互优化**（`frontend/src/views/ReportList.vue`）：去除独立展开箭头列，改为点击报告标题展开/收起该行导出记录（标题着色提示展开态）；勾选列宽收窄
- **渗透工单编辑自动带出 URL**（`frontend/src/views/TestingPlanList.vue`）：编辑进入且 `target_urls` 为空时，从关联资产自动带出 URL（与点选资产语义一致，仅空时带出，保存后以本列表为准）
- **漏洞列表筛选宽度对齐**（`frontend/src/views/VulnList.vue`）：录入时间 daterange 编辑器覆盖 `--el-date-editor-width` 撑满列宽，与其他下拉框同宽
- 远程检测列表「外部项目」「申诉状态」列宽微调（`frontend/src/views/RemoteTestingList.vue`）

### 测试

- `backend/tests/test_api.py` 适配权限目录：角色权限校验用例改用 `PERMISSION_CATALOG` 语义，补充 `GET /users/roles/permissions/catalog` 分组返回断言

---

## [2.5.0] - 2026-08-26

导入报告批量关联工单并确认导出：多批次一键入库，复用现有单批确认逻辑与报告批量导出链路。

### 新增

- **导入列表批量关联工单并确认**（`backend/app/api/v1/imports.py` / `backend/app/services/import_service.py` / `frontend/src/views/ImportList.vue` / `frontend/src/components/ImportBatchConfirmDialog.vue`）：导入列表新增多选与「批量关联工单并确认」入口，勾选多个待确认批次后统一选择渗透测试工单（资产随工单联动，可覆盖），一次确认全部入库；报告格式批次自动生成报告，并复用 `/reports/batch-export` 批量导出打包下载
- **批量确认端点**（`POST /imports/batch-confirm`，`import:manage`）：逐批次复用单批确认逻辑（抽取为 `import_service.confirm_batch_internal` 结构化返回），单批次失败仅回滚该批次不影响其余；已确认 / 无待入库记录的批次计入跳过；返回各批次明细与生成报告 id 列表供前端触发导出
- **工单 / 资产联动逻辑抽取**（`frontend/src/composables/usePlanAssetLink.ts`）：预览确认页与批量对话框共用（工单下拉文案、资产候选过滤、选定工单自动联动默认资产），消除两处复制

### 测试

- `backend/tests/test_api.py` 新增 `test_batch_import_confirm`：正常批量确认（统一工单、报告自动生成并挂载）、重复关联跳过（含 `batch_ids` 内重复去重）、部分失败隔离、空批次与非法工单校验、无 `import:manage` 权限 403

---

## [2.4.1] - 2026-08-25

缺陷修复：报告格式导入建漏洞时提交时间按报告月份归口。

### 修复

- **漏洞提交时间口径**（`backend/app/services/import_service.py`）：报告格式导入新建漏洞的 `submit_time` 改为取报告时间（标题日期 14:00），替代原先的导入当天当前时间，使「渗透测试工单按月漏洞统计」与「安全态势」按报告月份归口而非导入当月；`create_vul_from_record` 新增 `submit_time` 入参，`confirm_one_record` 传入 `report.create_time`

### 新增

- **存量回填脚本**（`backend/scripts/backfill_vul_submit_time.py`）：幂等扫描历史已确认的报告导入批次，将其关联漏洞的 `submit_time` 回填为批次 `report_date` 的 14:00（与报告 `create_time` 口径一致）；支持 `--dry-run` 仅统计

### 测试

- `backend/tests/test_api.py` 补充断言：报告导入漏洞 `submit_time` 始于 `2026-07-01T14:00`（按月归口）

---

## [2.4.0] - 2026-08-25

报告被测测试账号、测试周期与参测人员解析回填，导入自动生成报告同步导出文件。

### 新增

- **报告被测测试账号**（`backend/app/models/report.py`、`schemas/report.py`、迁移 `d0e1f2a3b4c5_add_report_test_account.py`、`frontend/src/views/ReportEditor.vue`）：`reports` 新增 `test_account` 字段，导入时从「测试目标」表第 5 行解析回填、报告编辑页可展示编辑，导出模板「测试目标」表第 5 行使用；`db.py` 轻量迁移同步加列
- **测试周期与参测人员解析**（`backend/app/services/docx_parser.py`）：新增 `_parse_schedule_table` 解析「时间与人员」表，回填 `test_start`/`test_end` 与参测人员姓名；`_parse_target_table` 补 `test_account`
- **参测人员关联工单**（`backend/app/services/import_service.py`）：`sync_plan_testers` 把导入报告参测人员姓名按 realname/username 映射系统账号并关联到工单测试人员（按 id 去重）
- **导入自动导出文件**（`backend/app/services/import_service.py` + `backend/app/api/v1/imports.py`）：导入自动生成的报告同步生成 docx 文件并记录导出任务（可下载），时间取报告标题日期固定 14:00；导入完成刷新关联工单实际人天（`plan_service.refresh_mandays`）
- **资产 URL 去重合并**（`backend/app/services/import_service.py`）：被测系统 URL 按换行/分号/逗号/空白拆分，`_is_internal_url` 判定内网后去重合并进资产 `internal_urls`
- **导出任务可下载标识**（`backend/app/schemas/report.py`）：`ExportJobOut.has_file` 派生字段（存在 `file_path` 为真），前端仅在 `has_file` 时提供预览/下载（`ReportList.vue`、`useExportJobs.ts`）

### 测试

- `backend/tests/test_api.py`、`test_parser.py`、`test_report_builder.py` 适配 `test_account`/时间与人员表解析；`ImportPreview.vue` 适配导入自动导出

---

## [2.3.0] - 2026-08-23

初测报告状态口径与测试目标URL补全：导出的初测报告漏洞状态显示「未修复」、工单新增「被测系统URL」字段作为报告测试目标数据源。

### 新增

- **URL 工具**（`frontend/src/utils/urls.ts` + `frontend/src/utils/__tests__/urls.spec.ts`）：新增 `mergeUrls` / `cleanUrls` / `assetUrls` 工具与单测

### 变更

- **初测报告漏洞状态口径（仅展示层）**（`backend/app/services/report_builder.py`）：关联报告后漏洞在系统内照旧自动流转「修复中」（内部流程、打点、状态机均不变），但对外交付的**初测报告**（标题不含「复测」）导出时，风险汇总表状态列与风险详情章节标题中的「修复中」统一显示为「未修复」；复测报告维持原状态名（含「复测未通过」派生态）。报告编辑页章节导航状态标签同步该口径
- **工单「漏洞简述」替换为「被测系统URL」**（`backend/app/models/special.py` / `schemas/special.py` / `frontend/src/views/TestingPlanList.vue` / `ReportEditor.vue`）：`testing_plans.brief` 列删除（该字段全仓无展示/导出消费，已录入文本随迁移丢弃），新增 `target_urls` JSON 字符串数组；编辑渗透测试工单时选择关联资产后自动带出资产公网/内网URL（`mergeUrls` 并入，新增与编辑模式均生效，去重保序、只增不删），支持手动回车录入新增与标签删除；保存后以该列表为准
- **报告「测试目标」URL优先取工单**（`backend/app/workers/main.py` / `backend/app/services/report_builder.py`）：导出时工单 `target_urls` 非空则作为「被测系统URL/被测系统域名」的权威来源（域名由URL推导），为空时回退既有「漏洞→资产」聚合链路，解决资产台账未录URL时报告测试目标两格空白的问题

### 迁移

- 新增 Alembic 迁移 `b8c9d0e1f2a3_plan_target_urls_replace_brief.py`：`testing_plans` 新增 `target_urls` 列、删除 `brief` 列（既有简述文本随迁移丢弃）

### 测试

- 后端 `test_report_builder.py` 新增：初测报告修复中显示「未修复」（汇总表+详情标题）、复测报告状态名保持「修复中」回归、测试目标表工单URL优先/为空回退资产聚合
- 后端 `test_api.py` 新增：`test_report_export_target_urls_from_plan` 导出集成用例（资产无URL时工单URL仍带出至测试目标表）；工单CRUD用例改用 `target_urls` 并覆盖编辑增删
- 前端新增 `src/utils/urls.ts`（mergeUrls/cleanUrls/assetUrls）及 `__tests__/urls.spec.ts` 单测
- `backend/scripts/seed_dev_data.py` 种子数据改用 `target_urls`

---

## [2.2.2] - 2026-08-23

嵌套弹窗与复测联动修复：弹窗定位失效、复测变更未实时刷新父列表。

### 修复

- **嵌套弹窗定位失效**（`frontend/src/components/AssetFormDialog.vue` / `PdfPreviewDialog.vue` / `VulnFormPanel.vue` / `VulnRetestPanel.vue`）：在计划抽屉表格展开行内打开的弹窗因固定定位失效导致页面闪烁、按钮点击失灵；补充 `append-to-body` 使弹窗挂载到 `document.body` 正常显示
- **复测变更未实时刷新**（`frontend/src/components/PlanWorkflowDrawer.vue`）：复测记录增删改后新增 `onRetestChanged` 处理器，重拉计划与漏洞列表，保证状态列、复测轮数随「已修复 / 复测未修复」结论实时联动（与「流转」行为一致）

### 测试

- **新增前端单测（vitest）**：`frontend/src/components/__tests__/VulnRetestPanel.spec.ts` 回归用例，验证新增复测记录弹窗通过 `append-to-body` 挂载到 `document.body`、脱离组件根节点，防止嵌套弹窗定位回归

---

## [2.2.1] - 2026-08-23

缺陷修复：导出历史标签渲染崩溃导致报告区域整页消失。

### 修复

- **导出/导入状态色值未随 /meta 下发（关键修复）**：`/meta` colors 命名空间遗漏 `export_job_status` / `import_batch_status` / `import_record_status` 三个 key（常量在 `constants.py` 已定义但未组装下发）。前端 `applyDictMeta` 无条件赋值将 `undefined` 注入注册表，渲染导出记录状态标签时 `undefined['done']` 抛 TypeError、Vue 渲染中断，表现为：测试流程抽屉点击「导出历史」后报告卡片整体消失、报告中心展开行后表格数据行消失、报告编辑页「导出记录」卡片不渲染。后端补齐三个色值字典下发
- **前端字典注册表空值兜底（防御加固）**：`applyDictMeta` 全部字段改为 `?? {}` / `?? []` 兜底，后端再漏发任何 key 时色值走 FALLBACK_COLOR 灰色展示，不再出现整页渲染崩溃

### 测试

- 后端 `test_api.py::test_meta` 补 colors 三 key 断言（名称与色值必须同步下发）
- 前端 `colors.spec.ts` 新增「meta 漏发任一 key 时兜底为空对象、标签查询不抛错」防回归用例

---

## [2.2.0] - 2026-08-22

功能演进（ROADMAP F3/F4/F6/F7 落地 + 会话令牌空闲滑动过期；F2/F5 取消）。

### 新增

- **F3 通知渠道（webhook + 邮件）**：新表 `notification_channels` 与 `/notify-channels` CRUD（system:manage，含「测试发送」）；`constants.py` 新增 `NOTIFY_CHANNEL_TYPES`（企业微信/钉钉/邮件）与 `NOTIFY_EVENTS`（漏洞创建/工单认领/漏洞状态流转/复测完成），经 `/meta` 下发；新 worker 任务 `send_notify_task`（wecom/dingtalk webhook 走 httpx markdown 消息，邮件复用 SMTP 任务）；`services/notify_service.py` 在触发点（漏洞创建/认领/各流转端点/复测闭环）按渠道订阅分发，失败仅告警不影响业务；前端「系统管理 → 通知渠道」配置页
- **F4 CVSS 3.1 计算器**：`vulns.score` 迁移为 Float 并新增 `cvss_vector` 列（知识库同步新增）；前端 `utils/cvss.ts` 实现 v3.1 基础评分（8 指标 + 官方 Roundup）与向量解析/构造，`CvssCalculator.vue` 组件嵌入漏洞表单（实时评分、等级色、向量串、「按评分同步等级」开关）；知识库表单支持向量录入与评分预览，套用模板/from-vul 双向带出向量；漏洞详情页展示 CVSS 评分标签
- **F6 开放 API（PAT）**：新表 `personal_access_tokens`（仅存 sha256，明文 `tlp_` 前缀仅创建时返回一次）；`/pats` 个人令牌管理（登录即可，7/30/90/365 天档位，每人至多 20 个有效令牌）；`core/deps.get_pat_user` 认证依赖（过期/吊销/禁用校验 + 每令牌每分钟限流 `VP_PAT_RATE_LIMIT=120`）；`/open/vulns` 与 `/open/stats` 只读接口复用站内查询口径（`vulns._build_vuln_conditions` / `services/stats_service.py` 自 dashboard 提炼）；前端「用户下拉 → 访问令牌」管理页
- **F7 登录与操作审计**：新表 `operation_logs`（IP/UA/操作人/动作/详情 JSON）；`services/audit_service.py` 统一写入，覆盖登录成功/失败/锁定、改密、用户与角色 CRUD、漏洞创建/删除/流转、工单认领与流转、报告导出/删除/发起复测、导入入库、知识库删除、PAT 与通知渠道变更；`GET /audit/logs` 查询端点（system:manage，类目/用户/动作/IP/日期筛选）；前端「系统管理 → 审计日志」双 tab 查询页
- **会话令牌空闲滑动过期**：refresh token 有效期 7 天 → 24 小时空闲窗口（`VP_REFRESH_TOKEN_EXPIRE_HOURS`），每次 `/auth/refresh` 轮换即重置计时；前端 `client.ts` 请求拦截器临期（<5 分钟）主动静默续期（single-flight 复用），活跃用户无感知、空闲超 24 小时强制重新登录。PAT 不受此限制

### 变更

- dashboard 聚合逻辑提炼为 `services/stats_service.py::build_stats`（`/dashboard/stats` 与 `/open/stats` 共用口径）
- `docker-compose.yml` backend_env 透传 `VP_SMTP_*`；根 `.env.example` 补 SMTP / 刷新窗口 / PAT 限流配置说明

### 数据库迁移

- `f6a7b8c9d0e1`：`vulns.score` Integer→Float（PostgreSQL USING 转换）、`vulns` / `knowledge_entries` 新增 `cvss_vector`；SQLite 开发库由 `db.py` 轻量迁移同步
- `a7b8c9d0e1f2`：新建 `operation_logs` / `notification_channels` / `personal_access_tokens` 三表（用户删除时审计置空、令牌级联删除）

### 测试

- 后端 `test_api.py` 新增 8 组用例：refresh 轮换与过期拒绝、审计登录/操作/筛选、meta 字典下发、PAT 生命周期与认证边界/过期/限流、通知渠道 CRUD 与校验/emit 分发（monkeypatch dispatch）、CVSS 字段往返与知识库向量
- 前端新增 `utils/__tests__/cvss.spec.ts`（官方向量→评分 9 组断言 + 解析/构造/等级映射）

---

## [2.1.0] - 2026-08-22

重构还债（ROADMAP R1-R6 全量落地）：后端巨石文件按域拆分、导入链路服务化、前后端字典单源化、全站表单校验体系化、前端测试覆盖扩展。

### 重构

- **R1 拆分 `api/v1/special.py`（1319 行 → 6 个文件，单文件 ≤ 600 行）**：按业务域拆为 `remote_testing.py` / `testing_plan.py` / `spring_action.py` 三个路由模块；通用聚合筛选引擎抽至 `core/filters.py`（操作符白名单/区间解析/按字段类型构造表达式），TestingPlan 专属查询（固定筛选/派生字段/统计）下沉 `services/plan_query.py`，Excel 导入导出下沉 `services/plan_io.py`；`_load_vulns` 提级为 `vuln_service.load_vulns_or_400`。路由路径与权限点零变化
- **R2 拆分 `schemas.py`（775 行 → `schemas/` 包 8 个域文件）**：common（分页/消毒类型/跨域 Brief/字典）/ auth / asset / vuln / knowledge / import_ / report / special，经 `schemas/__init__.py` 显式重导出，全部 `from app.schemas import ...` 调用方零改动
- **R3 拆解 `imports.py::confirm_batch`（260 行 → 路由约 65 行 + `services/import_service.py`）**：按「解析校验 → 报告编排（计划/资产/报告三段）→ 知识库回填 → 去重合并/建漏洞 → 收尾」拆为服务函数，路由只做参数编排；`_vuln_section_html` / `_affected_urls_html` 提级 `services/report_html.py`，消除跨路由模块引用私有函数

### 变更

- **R6 前后端字典单源化**：`constants.py` 新增各字典展示色值表（等级/状态/计划状态/漏洞类型/资产状态/URL 标签/报告状态/导入与导出任务状态），`/meta` 扩展下发 `colors` 色值命名空间、`report_status` / `import_*_status` / `export_job_status` 名称字典与 `nonpen` 命名空间（测试项/状态/操作/文案，`NONPEN_ITEM_ACTIONS` 改有序元组即按钮渲染顺序）；前端 `colors.ts` 重构为 meta 注册表（`applyDictMeta` 由 `fetchMeta` 注入，函数签名全部不变），删除 `constants/nonpen.ts` 镜像文件——改后端字典一处即全端生效；docx 打印色板（report_builder）独立保留
- **R5 全站表单校验切换 el-form rules**：资产（AssetFormDialog）、漏洞（VulnFormPanel 外层测试目标 + 每漏洞卡片动态表单）、工单（TestingPlanList / NonpenPlanList，含「联动创建需测试项」与「工单ID二选一」跨字段 validator）三类主表单，以及 Login / MainLayout 改密码 / GroupList / UserList / KnowledgeList / VulnRetestPanel（复测结论↔详情跨字段）全部迁移，错误提示内联到字段，消除提交前 `ElMessage.warning` 弹窗式校验

### 测试

- **R4 前端测试覆盖扩展（9 例 → 45 例）**：新增 `format` / `colors`（meta 注册表/回退/nonpen 助手）/ `useAssetSelect` / `useDictOptions` / `useCrudDialog` / `useExportJobs`（重复导出确认与取消/异常放行）单测与 `VulnList` / `ReportEditor` 冒烟测试（jsdom + stub 重子组件）
- `backend/tests/test_api.py::test_meta` 扩展断言 colors/nonpen 下发结构；`test_report_builder.py` 章节函数断言改从 `services/report_html` 导入

### 文档

- `docs/ROADMAP.md`：R1-R6 移入已完成归档，现状基线更新为 2.1.0
- `AGENTS.md`：目录结构（schemas/ 包、api/v1 拆分模块、services 新增）、前端规范（colors.ts 改为 meta 注册表唯一出口、删除字典镜像同步要求）、新增表单校验规范（必须 el-form rules）

---

## [2.0.2] - 2026-08-22

大规模重构:导出/下载/色彩/消毒统一封装,前端设计系统抽取,迁移 pnpm,补充前端测试。

### 变更

- **前端包管理迁移 npm → pnpm**（`frontend/package.json` / `pnpm-workspace.yaml` / `pnpm-lock.yaml`；删除 `package-lock.json`）：新增 `packageManager: pnpm@11.6.0` 与 `test`/`test:watch`(vitest) 脚本；开发/构建/安装统一改用 pnpm
- **开发脚本同步**（`dev.ps1` / `dev.sh` / `frontend/Dockerfile` / `README.md` / `.gitignore`）：安装与启动命令适配 pnpm；`.gitignore` 补充 pnpm/uv/测试产物忽略项

### 重构

- **Excel 导出统一封装**（`backend/app/core/xlsx.py` 新增）：抽出 `xlsx_response(wb, filename)`,所有 xlsx 导出接口(`assets.py` / `special.py` / `reports.py`)移除散落的 `BytesIO`+`StreamingResponse` 样板,统一走 `xlsx_response`
- **人天口径统一**（`backend/app/core/timeutil.py` 新增 `mandays_between` / `parse_date`）：`special.py`(`_no_vul_mandays`)、`reports.py`(`_calc_mandays`)、`vulns.py`(`_parse_date`)的本地副本统一改为调用 `query.parse_int_list`/`parse_str_list` 与 `timeutil`,消除重复
- **富文本消毒统一**（`backend/app/schemas.py`）：抽出 `HtmlStr` / `OptHtmlStr` 注解类型,全站富文本字段统一经 `sanitize_html` 消毒,移除各模型重复的 `_clean_html` validator
- **前端设计系统抽取**（`frontend/src/components/StatCard.vue` 新增、`utils/colors.ts` / `utils/chartTheme.ts` 单一色源）：`Dashboard` 等图表系列色改用语义化 `PALETTE`,统计卡统一走 `StatCard`；新增 `utils/download.ts`(`saveBlob`/`saveReportBlob` 统一 blob 下载,docx 目录域未更新时提示)、`composables/`(`useListPage` / `useExportJobs` / `useAssetSelect` / `useCrudDialog` / `useDictOptions`)；多个视图(`TestingPlanList` / `NonpenPlanList` / `VulnList` / `RemoteTestingList` / `ReportList` / `ReportEditor` / `SpringActionList` / `UserList` / `GroupList` / `KnowledgeList` / `AssetList` / `PlanWorkflowDrawer` / `ImportList`)适配统一组件与样式

### 测试

- **新增前端单测（vitest）**：`frontend/src/utils/__tests__/download.spec.ts`、`frontend/src/composables/__tests__/useListPage.spec.ts`；`backend/tests/conftest.py` 补充种子数据钩子
- **开发种子数据脚本**（`backend/scripts/seed_dev_data.py` 新增）：一键灌入演示用资产/系统/漏洞/工单数据,便于本地预览

### 文档

- **`AGENTS.md`**（新增）：仓库唯一项目规范入口（选型/命令/约束）,供协作者与 AI 工具遵循
- **`docs/ROADMAP.md`**（恢复）：补回路线图文档

---

## [2.0.1] - 2026-08-19

报告导入健壮性与批量上传:跨报告去重合并、解析器乱码回退、复测轮次修正。

### 修复

- **解析器系统名乱码回退**（`backend/app/services/docx_parser.py`）：封面/文件名/目标表系统名含乱码（`U+FFFD`）时视为无效,依次回退到下一数据源,保证能匹配现有工单（不再因乱码系统名匹配失败）
- **漏洞标题修复状态归一化**（`backend/app/services/docx_parser.py`）：新增 `_normalize_vul_title` 剥除「（已修复/未修复/部分已修复…）」后缀供跨报告去重合并,`fixed` 判定更严谨（仅「已修复」为真,「部分已修复/基本已修复」等视为未闭环）
- **复测轮次逻辑修正**（`backend/app/api/v1/imports.py`）：每份复测报告统一调用 `start_retest_round(force=True)` 建轮；全部修复才打完成点并置复测完成(60),否则停留复测中(50)待后续复测报告闭环
- **解析器复测轮次序号**（`backend/app/services/docx_parser.py`）：从文件名解析 `retest_round_seq`（同日重复复测 `-N` 后缀映射为第 N+1 轮）

### 变更

- **导入页批量上传**（`frontend/src/views/ImportList.vue`）：改为拖拽 + 可多选（上限 20 份）`.docx`,选好后点「开始上传」批量入库解析；明确「同一工单下相同名称漏洞自动去重合并」
- **跨报告去重合并**（`backend/app/api/v1/imports.py`）：同一渗透测试工单下相同名称漏洞贯穿多份报告自动去重合并为一条（贯穿三轮复测仅留一条,状态按最终闭环更新）

### 测试

- **解析器测试**（`backend/tests/test_parser.py`）：新增 `test_normalize_vul_title`（标题归一化与 fixed 判定覆盖「部分已修复/基本已修复/半角括号/含括号非状态」等边界）、文件名 `retest_round_seq` 解析（含 `-1` 第二轮）
- **导入跨报告去重测试**（`backend/tests/test_api.py`）：新增复测报告贯穿三轮导入后漏洞唯一、计划复测完成且两轮复测轮次记录的断言
- **测试样例**：3 份中移综合办公系统渗透测试/复测报告 `.docx` 样例仅本地手测用（不入库）；`test_parser.py` 的 docx 样例为测试内 python-docx 现造,不依赖外部文件

---

## [2.0.0] - 2026-08-15

破坏性的数据库结构重构:远程检测表按通报口径重构、漏洞来源口径重置。

### 数据库（破坏性变更，需迁移）

- **远程检测表重构**（`backend/app/models/special.py` / 迁移 `backend/alembic/versions/e5f6a7b8c9d0_refactor_vul_source_and_remote_testing.py`）：移除 `title` / `test_time` / `appeal_success` / `appeal_report_id`,新增通报口径字段 `notice_time`(通报月份) / `notified_unit`(通报单位) / `is_external`(是否外部通报) / `vuln_name` / `vuln_type` / `appeal_status` / `appeal_method` / `appeal_file_name` / `appeal_file_path` / `appeal_file_size`;申诉报告由 `appeal_report_id`(关联报告)改为**附件上传**（新增 `upload-appeal` 接口与 `/{id}/appeal` 下载接口）。迁移脚本删除旧列并重置表数据,**历史远程检测记录需重新录入**
- **漏洞来源口径重置**（`backend/app/constants.py` / `backend/app/models/business.py`）：`vulns.source` 不再承载「渗透测试工单」来源——凡 `testing_plan_id` 非空的漏洞恒为「渗透测试工单」来源（前端展示与统计统一按此口径）；`VUL_SOURCE` 枚举重置为可选来源值（关联工单时不再占用 source 枚举）。迁移一并重置 `vulns.source` 字段数据

### 新增

- **报告列表「关联工单」列**（`frontend/src/views/ReportList.vue`）：展示报告关联渗透测试工单号与系统名（`ticket_id` / `ticket_system_name`）

### 变更

- **漏洞来源展示统一**（`frontend/src/views/VulnList.vue` / `frontend/src/views/VulnDetail.vue` / `frontend/src/components/PlanWorkflowDrawer.vue`）：关联渗透测试工单的漏洞恒显「渗透测试工单」；否则取 `meta.vul_source` 可选值（未选择显 `-`）；工单流程抽屉漏洞详情新增「渗透测试工单」关联标识
- **报告导入来源处理**（`backend/app/api/v1/imports.py` / `backend/app/api/v1/reports.py`）：报告导入与创建按新来源口径填充 `testing_plan_id` / `source`；报告移除 `vuln_source` 冗余字段,改由漏洞自身来源口径展示
- **仪表盘统计按新来源口径**（`backend/app/api/v1/dashboard.py`）：漏洞来源统计适配重置后的 `VUL_SOURCE` 枚举

### 测试

- **远程检测重构测试**（`backend/tests/test_api.py`）：`test_special_modules_crud` 远程检测段按新接口重写（申诉附件上传 `upload-appeal` + 下载校验、字段名更新）；`test_dashboard_event_filters` 适配新来源枚举

---

## [1.13.2] - 2026-08-14

列表工具栏筛选与导入导出收纳优化,新增筛选徽标与一键重置。

### 修复

- **渗透测试工单列表工具栏重组**（`frontend/src/views/TestingPlanList.vue`）：「当前可测试系统 / 无人认领 / 待办流程」三项布尔筛选收纳为「快捷筛选」下拉（带启用项徽标）；「导入模板下载 / 导入 Excel / 导出 Excel」收纳为「导入导出」下拉；新增筛选弹窗（含日期范围与「只看我提交的」）与「重置筛选」按钮、已启用条件数徽标
- **历史漏洞库工具栏重组**（`frontend/src/views/VulnList.vue`）：多维筛选条件收纳为单个「筛选」下拉弹窗（带已启用条件数徽标与「重置筛选」），筛选与统计概览实时联动

---

## [1.13.1] - 2026-08-14

前端交互与开发脚本打磨,清理冗余演示页与文档。

### 变更

- **开发脚本健壮性**（`dev.sh` / `dev.ps1`）：新增启动前端口占用检测与启动后 HTTP 健康检查（轮询等待服务真正响应）；端口冲突或「假启动」时给出明确提示与处理建议；新增 `HEALTH_TIMEOUT` 可调参数
- **后端镜像构建**（`backend/Dockerfile`）：pip 安装改用阿里云镜像源,加速国内构建

### 修复

- **漏洞列表资产下拉远程搜索**（`frontend/src/views/VulnList.vue`）：资产选择改为远程搜索并展示「系统名（子系统）（系统类型）」标签,解决同名系统环境混淆与多选回显为纯数字问题
- **工单流程抽屉新增「编辑」入口**（`frontend/src/components/PlanWorkflowDrawer.vue`）：漏洞行新增「编辑」按钮直达 `/vulns/:id/edit`
- **统计概览标题样式**（`TestingPlanList.vue` / `VulnList.vue`）：统计概览标题居中 + 两侧渐变装饰线视觉增强
- **按钮与卡片视觉统一**（`style.css` + 多个视图）：工具栏主操作按钮统一最小宽度 `btn-min`；统计卡片留白与内边距优化；卡片 hover 阴影统一

### 移除

- **演示页**（`demo/dashboard.html` / `demo/testing-plan.html` / `demo/vuln-list.html`）：移除初版原型演示页（功能已由正式应用覆盖）
- **文档**（`docs/ROADMAP.md` / `docs/版本发布流程与开源准备.md`）：移除过期/冗余文档

---

## [1.13.0] - 2026-08-13

漏洞列表多维筛选与透视聚合统计,并新增前端演示页。

### 新增

- **漏洞列表多维筛选**（`backend/app/api/v1/vulns.py`）：`list_vulns` 新增多选过滤维度 `levels` / `statuses` / `vul_types` / `asset_ids` / `departments` / `system_types` / `test_types`(逗号分隔字符串)与录入时间区间 `submit_time_from` / `submit_time_to`;条件构建抽离为 `_build_vuln_conditions`(单选与多选互斥,多选服务于统计表多选控件)
- **漏洞统计聚合接口**（`backend/app/api/v1/vulns.py`）：`/vulns/stats` 新增按资产分组 `by_asset` 与透视表 `pivot`(按 资产 → 部门 聚合,含每行修复率与合计行),并补齐 `by_fix_status` / `by_department` / `by_system_type` / `by_test_type`
- **漏洞列表透视表前端**（`frontend/src/views/VulnList.vue`）：新增按资产/部门的透视统计表(部门列合并单元格 + 合计行),筛选区支持多选维度联动
- **演示页**（`demo/dashboard.html` / `demo/testing-plan.html` / `demo/vuln-list.html`）：新增前后端原型演示页

### 测试

- **按资产分组统计**（`backend/tests/test_api.py`）：新增 `test_vuln_stats_by_asset`,覆盖 `/vulns/stats` 按资产分组计数正确、部门筛选联动

### 变更

- **`.gitignore`** 补充 smoke 脚本(`_smoke_*.py`)与开发日志(`_uvicorn_dev.*` / `_vite_dev.*` / `test_vp_stats*.db`)忽略项

---

## [1.12.2] - 2026-08-13

复测结论校验增强:二轮复测不得误用首轮历史复测记录放行。

### 修复

- **复测结论校验按轮次判定**（`backend/app/services/vuln_service.py` / `backend/app/api/v1/vulns.py`）：`ensure_retest_conclusion` 改为按「本轮是否新增复测记录」或「随流转直接提交的复测内容」判定,不再误用首轮历史 `retest_html` 放行二轮复测流转(已修复/复测未通过)；`set_status`/`transition` 改为 `async`,系统自动流转(报告联动)以 `skip_conclusion=True` 跳过校验,避免「复测中自动回修复中」被误拦
- **新增二轮复测守卫测试**（`backend/tests/test_api.py`）：`test_second_round_retest_requires_new_record` 覆盖「二轮未新增记录时禁止切换为已修复/复测未通过,新增本轮记录后放行」

---

## [1.12.1] - 2026-08-13

报告编辑页复测处理复用 VulnRetestPanel 组件(与渗透测试工单流程抽屉一致),并修复若干前端交互细节。

### 变更

- **报告编辑页复测处理复用组件**（`frontend/src/views/ReportEditor.vue`）：移除内联复测面板与 `submitRetest`,改为复用 `VulnRetestPanel` 组件(`@changed="onRetestChanged"` 刷新漏洞状态),复测记录结构化、与渗透测试工单流程抽屉体验一致

### 修复

- **漏洞编辑页「取消」路由修正**（`frontend/src/views/VulnEdit.vue`）：「取消」按钮由 `router.back()` 改为 `router.push('/vulns')`,避免返回非预期页
- **表单按钮对齐修复**（`VulnFormPanel.vue` / `VulnEdit.vue`）：保存/提交与复测按钮补充 `!ml-0`,消除 Element Plus 默认左边距错位

---

## [1.12.0] - 2026-08-13

复测记录标题支持手动编辑,可准确对应实际复测时间。

### 新增

- **复测记录标题手动编辑**（`backend/app/api/v1/vulns.py` / `backend/app/schemas.py` / `backend/app/models/business.py` / `frontend/src/components/VulnRetestPanel.vue`）：`vul_retest_records` 新增 `title` 字段,复测记录卡片标题支持点击行内编辑（回车保存）；新增复测记录对话框可选填复测标题。自定义标题优先于自动生成,可准确对应实际复测时间；清空后回退为按创建日期自动生成的「复测记录yymmdd」（同日多条追加 -1/-2 后缀）。SQLite 走 `_migrate_lightweight` 幂等加列,PostgreSQL 走 Alembic 迁移 `e2f3a4b5c6d7`

---

## [1.11.1] - 2026-08-13

复测记录面板展示修复与复测聚合标题日期化。修复测试流程抽屉多漏洞展开行复用组件实例导致的复测记录不显示 / 串数据,以及仅有报告「复测处理」历史复测内容时面板空白；复测聚合标题由「复测记录 N」改为「复测记录yymmdd（同日 -N 后缀）」,并新增存量回填脚本接入升级流程。

### 修复

- **复测记录展开 / 编辑页显示异常**（`frontend/src/components/VulnRetestPanel.vue`）：面板改为监听 `vulId` 变化自动重新加载（替换原 `onMounted(load)`）,避免测试流程抽屉中多个漏洞的展开行复用组件实例导致复测记录不显示或串数据；漏洞仅有 `retest_html`（报告「复测处理」直接写入）而无 `vul_retest_records` 记录时,面板只读回退展示历史复测内容
- **复测聚合标题改为日期格式**（`backend/app/api/v1/vulns.py`）：`_sync_vul_retest_html` 聚合标题由「复测记录 N」改为「复测记录yymmdd」,同一天新增的多条依次追加 `-1`、`-2` 后缀（如复测记录250813、复测记录250813-1）；新增回填脚本 `backend/scripts/backfill_retest.py` 并接入 `scripts/upgrade.sh`,升级时自动重建存量旧编号标题

---

## [1.11.0] - 2026-08-13

工单体系命名统一与复测轮次一致性修复。菜单与业务文案统一为「工单」风格；复测报告与复测轮次建立关联,删除复测报告时自动回退对应轮次；漏扫基线工单列表排序口径优化；全站时间格式化统一；文档截图清理。

### 变更

- **模块命名统一**：菜单标题与业务文案统一为「工单」风格——渗透测试计划→渗透测试工单、非渗透计划→漏扫基线工单、漏洞管理→历史漏洞库、漏洞知识库→漏洞模板库；同步更新侧边栏菜单 / 路由页面标题 / 表单 / 按钮 / 提示语 / Excel 导出与导入模板（sheet 名、文件名、表头）及后端错误提示与 API 文档 tags。路由路径 `/testing-plans`、`/nonpen-plans`、`/vulns`、`/knowledge` 与 API、表名保持不变
- **漏扫基线工单列表排序口径**（`backend/app/api/v1/nonpen.py`）：列表默认排序由 `id desc` 改为「接收时间 desc → 工单序号 desc → id desc」,与渗透测试工单列表排序口径保持一致
- **全站统一时间格式化**（`frontend/src/utils/format.ts` 新增 + 多视图改用 `fmtDateTime`/`fmtDate`）：抽离统一时间展示工具,禁止各视图内散落的 `slice`/`replace` 自定义格式,消除时间格式不一致

### 修复

- **删除复测报告后复测轮数不回退**（`backend/app/api/v1/reports.py` / `backend/app/services/plan_service.py`）：发起复测生成复测报告时,本轮次 `start_retest_round` 记录关联 `report_id`；删除该复测报告时调用新增 `rollback_retest_round_by_report` 移除对应轮次（无进行中轮次时对称撤销最近一轮完成点）,保证复测轮数与报告数据一致。报告导出同步新增 `version_dates`,按计划下各报告创建顺序对齐各版本导出日期

### 数据库

- `testing_plan_retest_rounds` 新增 `report_id`（INTEGER,可空）：SQLite 走 `_migrate_lightweight` 幂等加列,PostgreSQL 走 Alembic 迁移 `d1e2f3a4b5c6`

### 移除

- 清理 `docs/images/` 下 15 张过期 UI 截图（登录 / 仪表盘 / 漏洞列表 / 报告编辑 / 导入 / 资产 / 测试计划 / 用户角色 / 复测等）,文档引用同步移除

---

## [1.10.0] - 2026-08-10

正式发布版本。新增与「渗透测试计划」平级的「非渗透计划」模块（主机 / Web / 基线扫描独立管理、测试项状态流转与次数统计、与测试计划联动双向同步 / 级联删除）,工单ID分配抽取为两表共享当日序号序列的 `ticket_service`；测试计划更名为「渗透测试计划」；实际人天支持手动修正；文档整理（移除 USER_GUIDE.md 与 ID-RENUMBERING-EVALUATION.md,新增《非渗透计划模块需求与设计》）。

### 新增

- **实际人天手动修正**（`frontend/src/views/TestingPlanList.vue` / `backend/app/services/plan_service.py` / `special.py`）：测试计划对话框的实际人天字段新增「修正」入口,点击后进入手动输入状态（不再被初测报告时间自动覆盖）,按钮切换为「取消修正」；取消修正后由系统按初测报告重新计算覆盖该字段,恢复自动计算值
- **非渗透计划模块**（`frontend/src/views/NonpenPlanList.vue` / `frontend/src/components/NonpenPlanWorkflowDrawer.vue` / `frontend/src/constants/nonpen.ts` / `backend/app/api/v1/nonpen.py` / `backend/app/services/nonpen_service.py` / `backend/app/services/ticket_service.py`）：与「测试计划」平级的新模块,独立管理主机 / Web / 基线三类扫描测试项的状态流转（未开始→初测中→等待复测→复测中→复测完成,任意阶段可忽略,取消忽略恢复未开始且次数清零）、初测 / 复测次数统计与五张统计卡片、工单ID与测试计划**共享当日序号序列**
- **测试计划「创建非渗透」联动**（`TestingPlanList.vue` / `special.py`）：测试计划新增表单勾选「创建非渗透」（新功能角标）,勾选后展开测试项选择；保存时同工单自动生成联动非渗透计划（共享工单ID与接收日期,列表展示「联动」角标）；编辑任一方公共字段**双向同步**,删除任一方**互相级联**；非渗透计划不关联漏洞 / 报告 / 人天（业务独立,复用 `special:manage` 权限）

### 变更

- **「测试计划」更名为「渗透测试计划」**：侧边栏菜单 / 页面标题 / 弹窗 / 按钮 / 空态 / 提示语全部更新为「渗透测试计划」；Excel 导出与导入模板的 sheet 名称、文件名、表头同步更新为「渗透测试计划」；后端错误提示同步更新。路由与 API 路径保持 `/testing-plans` 不变,避免破坏既有链接与权限

### 修复

- **非渗透计划扫描次数统计口径**（`backend/app/services/nonpen_service.py`）：统计卡片「基线 / 主机 / Web 扫描次数」原按「初测次数 + 复测次数」累加,导致同一测试项初测复测被计算两次；改为按「初测次数」统计,初测与复测针对同一测试项合计按一次计（复测多次也不重复计数）
- **非渗透计划流程抽屉空白**（`frontend/src/components/NonpenPlanWorkflowDrawer.vue`）：组件常驻但仅在首次挂载时 `load()`,打开时 `planId` 已设置却未重新加载导致内容空白；改为 `watch(visible + planId)` 打开时刷新
- **非渗透计划工单ID未生成**（`backend/app/schemas.py` / `backend/app/api/v1/special.py` / `frontend/src/views/NonpenPlanList.vue` / `frontend/src/views/TestingPlanList.vue`）：工单ID依赖「需求接收日期」或手动指定工单ID,两者皆空时系统静默保存导致工单ID缺失；新增前后端双重校验,未提供工单ID来源时拒绝保存并提示

### 数据库

- `testing_plans` 新增 `actual_mandays_override`（BOOLEAN）：SQLite 走 `_migrate_lightweight` 幂等加列,PostgreSQL 走 Alembic 迁移 `b5c6d7e8f9a0`
- 新增 `nonpen_plans` 表（`ticket_seq` / `ticket_id_manual` / `asset_ids` / `items` JSON / `testing_plan_id` 联动外键）；`testing_plans` 新增 `create_nonpen`（BOOLEAN）：SQLite 走 `_migrate_lightweight` 幂等建表加列,PostgreSQL 走 Alembic 迁移 `c9d0e1f2a3b4`

---

## [1.9.0] - 2026-08-07

报告列表显示生成时间、测试计划聚合筛选、报告导出历史管理与重复导出 / 重复生成检测、复测记录状态联动,以及对应数据库结构迁移。

### 新增

- **报告列表「生成时间」列**（`frontend/src/views/ReportList.vue` / `backend/app/api/v1/reports.py`）：报告列表新增可排序的「生成时间」列（`create_time`）,流程抽屉报告项同步展示「生成于 …」,报告概要 schema 补充 `create_time` 字段
- **报告导出历史管理 + 重复导出检测**（`ReportList.vue` / `PlanWorkflowDrawer.vue` / `reports.py` / `report.py` / `worker/main.py`）：报告列表与流程抽屉改为一键展开查看导出历史版本,支持单条下载 / 预览 / 删除；导出任务记录报告内容指纹（`report_snapshot`：编辑版本 + 更新时间 + 关联漏洞编辑快照）,导出前 `POST /reports/{id}/export-check` 检测同格式重复导出,前端弹窗确认「继续导出 / 取消」
- **报告生成高度相似性检查**（`reports.py` / `ReportList.vue`）：生成 / 保存报告时采集关联漏洞最后编辑时间快照（`reports.vul_edit_snapshot`）,再次生成前 `POST /reports/similarity-check` 对比历史报告,高度相似时前端弹窗确认；存量报告首次对比时自动回填快照（幂等）
- **测试计划聚合筛选**（`frontend/src/components/FilterBuilder.vue` 新组件 / `TestingPlanList.vue` / `special.py`）：列表筛选升级为弹窗式聚合筛选构建器（多条件「且 / 或」连接、单条件「非」取反、文本 / 枚举 / 数值 / 日期区间操作符）,后端 `filters` JSON 按字段白名单动态过滤；新增「显示待办流程」快捷筛选（未测试 / 初测中 / 复测中）
- **复测记录状态联动**（`vulns.py` / `VulnRetestPanel.vue` / `vuln_service.py`）：创建复测记录时可一并调整漏洞状态（复测未修复回修复中 / 已修复）,状态流转统一校验复测结论完整性
- **工单序号复用**（`special.py`）：需求接收日期内分配最小未占用序号,删除 / 释放的工单 ID 可被后续记录重新使用

### 变更

- 测试计划列表筛选栏重排:原状态 / 类型 / 部门 / 日期范围下拉收敛进「筛选」弹窗,保留「当前可测试系统」「无人认领」并新增「待办流程」快捷勾选

### 数据库

- `reports` 新增 `vul_edit_snapshot`（JSON）、`export_jobs` 新增 `report_snapshot`（JSON）：SQLite 走 `_migrate_lightweight` 幂等加列,PostgreSQL 走 Alembic 迁移 `c3d4e5f6a7b8` / `d4e5f6a7b8c9`

---

## [1.8.0] - 2026-08-07

报告编辑页章节导航支持鼠标拖拽排序,并修正拖拽 / 删除 / 移动后的导航高亮索引同步问题。

### 新增

- **报告编辑页章节导航拖拽排序**（`frontend/src/views/ReportEditor.vue`）：章节导航支持鼠标拖拽重排,含拖拽指示线、拖拽态样式（半透明 / 抓取光标）与落点高亮；同步修正 `removeSection` / `move` / 拖拽插入后的导航高亮索引,避免排序后高亮错位

---

## [1.7.0] - 2026-08-06

报告导出管线改造（回退 LibreOffice 目录自动更新、改用 Pillow 图片压缩）、全系统业务时间统一为 UTC+8 北京时区、测试计划认领与关联资产增强,以及多项部署 / 运维与文档优化。

### 变更

- 报告导出管线：报告生成与导出整体优化——`reports.py` 接口与 `report_builder` 增强、worker 导出流程改进、`ReportList` 批量导出交互优化；曾尝试由 worker 调用 LibreOffice 宏自动刷新 TOC 目录域（新增 `libreoffice_toc.py` 与 `ENABLE_LIBREOFFICE` 构建项）,因环境依赖与稳定性问题随后回退,改为前端提示用户手动更新域；新增报告图片压缩（Pillow）以解决高分辨率截图导致 docx 体积过大；前端目录提示提取为 `tocNotice.ts`（支持「不再显示」勾选,记 localStorage）
- 全系统业务时间统一为 UTC+8 北京时区：`timeutil.now()` 基于 `settings.TIMEZONE` / Asia/Shanghai（依赖 zoneinfo + tzdata）,`utcnow()` 仅用于 JWT 签发；全后端时间获取统一替换；新增 `migrate_utc_to_utc8.py` 历史数据迁移脚本
- 测试计划认领与关联资产增强：流程抽屉支持计划认领 / 退出与漏洞库选择；报告编辑页正文与目录导航滚动分离、列表页主键由 ID 改为序号展示；多个列表 / 详情页（资产、用户组、导入、远程检测、春耕行动、测试计划、漏洞等）交互优化
- 测试计划关联资产支持自动填充（按漏洞归属资产回写）,列表筛选改为多条件并集

### 新增

- 测试计划新增「工单ID」字段并支持手动编辑与唯一校验；关联资产新增录入入口及自动填充；扩展 assets / imports / knowledge / misc / users / special 等接口与 schema
- Docker 腾讯云镜像加速脚本 `scripts/setup-docker-mirror.sh`；升级脚本 `scripts/upgrade.sh` 优化备份触发条件

### 修复

- 修复报告导出失败时事务未回滚,导致导出任务永久卡在 `running` 的问题（worker 增加异常回滚）
- nginx 改为动态解析 api 上游（避免容器 IP 变化导致 502）；`backup.sh` / `restore.sh` 增加幂等处理

---

## [1.6.0] - 2026-07-31

补充生产部署与运维工具链：一键升级 / 备份 / 恢复脚本、Alembic 结构迁移基线与部署手册。

### 新增

- 部署与运维手册 `docs/DEPLOY.md`：首次部署、SQLite 数据说明、版本升级、备份、更换 VPS 平滑迁移全流程
- 一键运维脚本 `scripts/backup.sh` / `scripts/restore.sh`（PostgreSQL 逻辑备份 + `storage` 卷打包,可跨机恢复）与 `scripts/migrate.sh`（在 api 容器内执行数据库结构迁移）
- 一键升级脚本 `scripts/upgrade.sh`：拉取代码 → 升级前备份 → 重建镜像 → 数据库结构迁移（先于 api 启动）→ 重启服务,支持 `--no-backup` / `--no-pull`
- 建立 Alembic 基线迁移（`backend/alembic/versions/`）与幂等迁移决策脚本 `backend/scripts/migrate.py`：自动纳管历史 `create_all` 库,支撑生产 PostgreSQL 已有表的字段级结构演进

---

## [1.5.0] - 2026-07-31

测试计划页集成测试全流程「统一流程抽屉」,从认领到复测完成可在单页一站式完成。

### 新增

- 测试计划列表操作列新增「流程」按钮,打开统一流程抽屉 `PlanWorkflowDrawer.vue`：顶部步骤条（认领 → 录入漏洞 → 生成报告 → 发起复测 → 复测处理 → 复测完成）按计划状态高亮；抽屉内完成认领 / 退出、录入漏洞、生成报告、发起复测、复测记录处理与漏洞状态流转、报告 Word/PDF 导出（提交后轮询任务并支持下载 / 预览）,除报告章节深度编辑外全流程一站直达
- 抽取可复用组件 `VulnFormPanel.vue`（漏洞录入 / 编辑表单主体）与 `VulnRetestPanel.vue`（复测记录增删改面板）,供独立页与流程抽屉共用
- 计划详情端点 `GET /testing-plans/{id}`（含测试人员 / 关联漏洞 / 关联报告 / 复测轮次）,供抽屉打开与每次操作后局部刷新单条数据

### 变更

- `TestingPlanList.vue` 操作列精简为「流程 / 编辑 / 删除」,原「认领 / 退出、录入漏洞、生成报告」入口统一收敛进流程抽屉,消除重复入口
- `VulnEdit.vue` / `VulnRetest.vue` 改为薄壳,主体逻辑迁移至可复用组件,独立专项管理页功能与行为保持不变

---

## [1.4.0] - 2026-07-31

列表页排序能力全覆盖、测试计划与报告导出体验改进,并补充团队内部用户手册。

### 新增

- 列表页按列排序：资产 / 漏洞 / 用户 / 测试计划 / 春耕行动 / 远程检测列表新增 `sort`、`order` 查询参数,后端 `core/query.py` 提供 `apply_sort` 白名单排序助手（合法字段追加 `id` 降序保证分页稳定）,对应前端列表启用可排序表头（服务端 `sortable="custom"` + `@sort-change`,知识库为本地排序）
- 漏洞录入 / 详情支持「影响 URL」多值：`VulnEdit.vue` 多行录入（增删行）,`VulnDetail.vue` 逐行展示,后端沿用单字段以换行分隔存储
- 团队内部用户手册 `docs/USER_GUIDE.md`（含系统概述、功能模块、使用步骤及界面截图 `docs/images/`）

### 变更

- 测试计划页漏洞统计徽章双模式：数量 > 0 深底白字（醒目）,= 0 浅底深字（弱化）；「导入模板」按钮文案改为「导入模板下载」
- 报告导出（`report_builder`）：封面第二行改填系统名称（`project_name`）；风险问题汇总统计段仅计入未修复漏洞,汇总表已修复状态显示绿色；风险问题详情「测试状态」按漏洞最新 `is_retest` 重写,复测未通过正确显示「复测」
- 报告版本号语义拆分：编辑保存改用 `revision` 乐观锁自增,导出版本 `version` 仅在导出成功时 +1（Word 导入关联报告的追加章节亦计入 `revision`）
- 报告导出时若测试周期为空自动预填：开始日期取关联漏洞最早提交日期,结束日期取当天
- 漏洞知识库列表默认排序改为按危害等级优先（危害等级 → 漏洞类型 → ID）

### 修复

- 报告导出 Word 打开后目录不自动刷新：`w:updateFields` 此前插入到 `settings` 首位违反 OOXML `CT_Settings` 元素顺序被 Word 忽略,改为插入到 `w:hdrShapeDefaults` / `w:compat` 等锚点之前
- 测试计划页「关联报告数量」统计偏少：手动新建报告或从漏洞生成未选计划时报告缺少 `testing_plan_id`,现按章节漏洞唯一归属计划自动回写

---

## [1.3.0] - 2026-07-31

漏洞知识库升级：新增漏洞名称与危害等级两列,预置 50 个常见漏洞标准信息,支持批量导入 / 批量删除 / 编辑的完整 CRUD。

### 新增

- 漏洞知识库新增「漏洞名称」（`vulnerability_name`,全库唯一）与「危害等级」（`severity_level`,沿用 `VUL_LEVEL` 字典）两个字段；条目粒度由「每漏洞类型一条」升级为「每漏洞名称一条」,同一漏洞类型可沉淀多条具体漏洞
- 预置 50 个最常见漏洞标准数据（SSRF、SQL 注入、未授权访问、水平 / 垂直越权、XXE、命令注入、文件上传、弱口令等）,提供幂等录入脚本 `backend/scripts/seed_knowledge.py`
- 知识库批量导入接口 `POST /knowledge/batch-import`（按漏洞名称 upsert,单次至多 500 条,批内查重与字典码校验,整批事务性）
- 知识库批量删除接口 `POST /knowledge/batch-delete`（按 ID 列表删除）
- 知识库按 ID 编辑接口 `PUT /knowledge/{id}`（支持改名并校验名称唯一）
- 知识库页面 `KnowledgeList.vue` 新增漏洞名称 / 危害等级列、多选批量删除、JSON 批量导入弹窗（支持文件选择与示例模板下载）

### 变更

- `GET /knowledge/by-type/{vul_type}` 与 Word 导入回填在同类型多条时,返回危害等级最高、最早创建的一条模板
- `POST /knowledge/from-vul/{id}` 改为按漏洞标题作为知识库条目名称 upsert,并携带漏洞等级
- 知识库数据验证增强：漏洞名称非空校验、危害等级 / 漏洞类型字典码校验、参考链接仅允许 http(s) 协议

---

## [1.2.0] - 2026-07-31

前端视觉改版：全站明 / 暗双主题与 UI 现代化。

### 新增

- 全站明 / 暗双主题：顶栏一键切换,`stores/theme.ts` 持久化到 localStorage,Element Plus dark css-vars 与 ECharts 明 / 暗双主题（`utils/chartTheme.ts`）联动
- 侧边栏可折叠（图标模式,状态持久化）
- 首次登录 / 密码重置强制改密弹窗：不可关闭,修改密码（至少 8 位）后方可使用系统

### 变更

- UI 现代化改版：引入设计令牌 CSS 变量层（`--tl-*`）,品牌主色改为靛蓝 `#4F46E5`,卡片圆角细边框、表头浅底、柔和胶囊标签、页面路由过渡动画
- 登录页 / 主布局 / 仪表盘等页面视觉重构,菜单图标与圆角胶囊选中态,品牌 Logo 渐变色块

> 注：本版本内容随提交 `87af5a4` 与 0.5.0 一并入库,发布记录补录于此。

---

## [1.1.0] - 2026-07-30

报告编辑与复测闭环增强、测试计划人天与 Excel 导入导出、全面安全加固。

### 新增

- 漏洞复测记录：`VulRetestRecord` 模型与 `/vulns/{id}/retests` CRUD 接口,新增独立复测处理页 `VulnRetest.vue` 及路由
- 报告编辑页章节导航栏：点击平滑滚动定位并高亮当前章节
- 报告编辑页漏洞字段改为固定下拉框（等级 / 类型 / 所在层 / 状态）,`PATCH /vulns/{id}/fields` 即时保存
- 测试计划增强：预估 / 实际人天字段,Excel 导出（明细 + 统计汇总双 sheet）、导入模板下载与批量导入（按 ID upsert,测试人员按姓名 / 用户名匹配）,统计汇总（初测 / 复测次数、人天合计、按状态与月度漏洞分布）,计划详情展示关联报告
- 仪表盘（安全态势）多维筛选：时间范围 / 部门 / 来源 / 等级,统计口径联动
- 组织（用户组）管理页 `GroupList.vue`；PDF 预览组件 `PdfPreviewDialog.vue`
- 环境变量样例文件 `.env.example`

### 变更

- Word 导出改用渗透测试报告模板（`backend/app/templates/report_template.docx`,可由 `VP_REPORT_TEMPLATE` 覆盖）：封面 / 版本变更记录 / 适用性声明 / 目录 / 测试目标 / 时间与人员 / 风险汇总统计 / 风险详情自动填充,目录页码在 Word 打开时自动刷新
- 报告新增「被测系统IP」字段（编辑器可填,导出填入测试目标表）；被测 URL / 域名由关联资产自动聚合
- 漏洞章节初始内容对齐模板标签结构（测试状态 / 漏洞等级 / 漏洞链接 / 描述 / 证明 / 修复建议 / 复测详情）；导出文案层面等级「严重」映射为「超危」
- 前端包管理迁移至 pnpm（`pnpm-lock.yaml` / `pnpm-workspace.yaml`）
- 后端公共查询助手 `paginate` / `get_or_404` 重构各列表与详情接口；新增 `timeutil.utcnow` 统一时间获取

### 修复

- 报告与测试计划状态由单向改为双向同步：漏洞回退未修复时报告回退 `draft`、测试计划回退「复测中」并重开复测轮次

### 安全

- 登录防爆破：同一用户名 + IP 失败达阈值锁定（`VP_LOGIN_MAX_FAILURES` / `VP_LOGIN_LOCK_SECONDS`）,Redis 计数、不可用时降级进程内存
- JWT 引入令牌版本号 `token_version`：修改密码 / 禁用账号即失效全部存量令牌,改密接口下发新令牌
- 生产环境（`DEBUG=False`）拒绝默认占位或不足 32 字符的 `VP_SECRET_KEY`,启动即校验
- CORS 收窄为白名单 `VP_CORS_ORIGINS` 且关闭凭证共享；生产环境关闭 `/api/docs` 与 OpenAPI 端点
- 富文本双端 XSS 清洗：后端所有入库 `*_html` 字段经 nh3 白名单过滤,前端渲染统一走 DOMPurify（`utils/html.ts`）
- `storage` 静态托管收窄至公开图片目录 `uploads/images`,导出 / 导入原始文档改走鉴权接口,nginx 代理同步收窄
- 内置 admin 初始口令不再固定：`VP_INITIAL_ADMIN_PASSWORD` 指定或随机生成（日志仅显示一次）,首次登录强制改密
- docker-compose 敏感配置改由 `.env` 注入（`POSTGRES_PASSWORD` / `VP_SECRET_KEY` 必填）；后端容器改非 root 用户运行,前端改用 nginx-unprivileged（8080 端口）
- 新增 `defusedxml` 依赖加固 docx 解析,防 XXE

---

## [1.0.0] - 2026-07-28

应用与资产合并重构：统一资产模型 + 漏洞多对多关联。首个破坏性（Major）变更——移除独立的应用管理模块。

### 新增

- 统一 `Asset` 资产模型:系统命名 / 子系统 / 部门 / 公网URL(互联网、办公网标签)/ 内网URL / 端口 / 服务 / 中间件 / 数据库 / 多负责人(姓名、电话、邮箱)
- 资产 Excel 批量导入 / 导出与导入模板下载(`/assets/import`、`/assets/export`、`/assets/import/template`)
- 漏洞批量提交接口 `POST /vulns/batch`,前端支持单次提交多个漏洞块
- 漏洞提交页资产选择下拉(远程搜索),无匹配时可弹窗新建资产并自动选中回填,选中后自动填充影响URL
- 可复用资产表单弹窗组件 `AssetFormDialog.vue`

### 变更

- 漏洞与资产改为多对多关联(`vuln_assets` 关联表),替代原 `Vul.app_id` 一对多
- 漏洞列表 / 详情 / 导入确认页面的应用字段统一改为资产
- 字典重命名:`APP_STATUS`→`ASSET_STATUS`、`APP_SEC_LEVEL`→`ASSET_SEC_LEVEL`,新增 `URL_TAG`

### 移除

- 删除独立的应用管理模块(`App` 模型、`/apps` 接口、应用管理页面与 `app:manage` 权限点),功能并入资产管理

---

## [0.3.0] - 2026-07-27

平台品牌更名为 **Talos**。

### 变更

- 平台整体更名 Talos:前端品牌标识、后端 `APP_NAME`、README 同步调整(`8d931df`)
- 浏览器页签标题补充 Talos 品牌(`9e9625e`)

### 修复

- `dev.ps1` 改用 UTF-8 BOM 编码,兼容 Windows PowerShell 5 下的中文输出(`5b879fa`)

---

## [0.2.0] - 2026-07-27

体验优化与开发效率提升。

### 新增

- 一键本地开发脚本 `dev.ps1` / `dev.sh`,单命令拉起前后端开发环境(`4530d4b`)
- 功能规划文档 `docs/ROADMAP.md`,包含 SLA 管理、知识库、审计等 8 项功能设计(`702f8ec`)

### 变更

- 统一漏洞等级与状态配色规范:严重深红 / 高危红 / 中危橙 / 低危蓝 / 安全绿(`33a9d5c`)

---

## [0.1.0] - 2026-07-27

首次发布:FastAPI + Vue3 全量重构版漏洞管理平台(`2f60373`)。

### 新增

- **后端**:FastAPI + SQLAlchemy(异步)+ Alembic 迁移,JWT 认证(Access / Refresh 双令牌)
- **漏洞管理**:漏洞全生命周期管理(提交、确认、修复、复测、关闭),等级评定与状态流转
- **应用 / 资产管理**:应用列表与资产台账维护
- **Word 导入**:上传渗透测试报告 docx,解析为漏洞草稿,批次预览、修正后确认入库
- **报告中心**:报告构建与 Word 导出(可选 Gotenberg 转 PDF)
- **Dashboard**:漏洞统计概览、等级分布、趋势图表(ECharts)
- **用户与权限**:用户管理、角色权限控制
- **异步任务**:arq + Redis 后台任务队列,Redis 不可用时自动降级为进程内执行
- **前端**:Vue3 + TypeScript + Vite + Element Plus + Tailwind CSS,TipTap 富文本编辑器
- **部署**:前后端 Dockerfile 与 docker-compose 编排

### 变更

- 忽略并移除测试运行产物 `test_storage/` 与 `test_vp.db`(`fdcdb24`)
