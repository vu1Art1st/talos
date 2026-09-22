# AGENTS.md — Talos 项目约定与规范

本文件是仓库内唯一的项目规范入口，供所有协作者与 AI 编码工具遵循。

## 项目概述

Talos 漏洞管理平台：漏洞全生命周期管理（前身洞察 2.0 / insight2 的现代化重写）。

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic · arq + Redis |
| 前端 | Vue 3 (`<script setup>` + TS) · Vite · Pinia · Element Plus · TailwindCSS · ECharts · TipTap 2 |
| 数据库 | PostgreSQL 16（开发 / 测试 / 生产统一；本地由 DBngin 原生托管，见 `docs/LOCAL_DEV_SETUP.md`） |
| 部署 | Docker Compose（api / worker / frontend / postgres / redis / gotenberg） |

## 常用命令

```bash
# 一键本地开发（Windows / Linux-macOS，连本机 DBngin 的 PostgreSQL 16 + Redis 7，自动建 venv 与装依赖）
pwsh -NoProfile -ExecutionPolicy Bypass -File .\dev.ps1
bash dev.sh

# 后端（始终用 backend/.venv 解释器，禁止系统 python）
cd backend
uv venv .venv --python 3.12                 # 创建/重建 venv（uv 管理，与容器 python:3.12-slim 对齐）
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt   # 安装/同步依赖
# 后端测试统一入口（推荐）：脚本已固化「关闭受管终端删除守卫 + 每次运行唯一 basetemp + 进程独占测试 schema」
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1   # Windows（加 -Workers 4 并行）
bash scripts/test.sh                                            # WSL / Linux / macOS（加 --workers 4 并行）
# 直接 .venv/Scripts/python -m pytest 仅限「非受管终端且确认无并发测试」时使用，见 docs/LOCAL_DEV_SETUP.md §四
.venv/Scripts/python -m uvicorn app.main:app --reload --port 27015
.venv/Scripts/python -m ruff check app scripts alembic tests   # 静态检查（配置 backend/ruff.toml）
.venv/Scripts/python -m vulture app --min-confidence 80        # 死代码检查
.venv/Scripts/python -m scripts.check_api_contract             # 前后端契约检查（OpenAPI ↔ 前端 TS 类型；不连库）

# 端到端测试（仓库根工具包：Playwright + 系统 Chrome；自动起独立 E2E 栈，见 docs/SCRIPTS.md §2.14）
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\e2e.ps1     # Windows（-Headed 带界面 / -Keep 保留栈）
bash scripts/e2e.sh                                                 # WSL / Linux / macOS

# 本地垃圾清理（只清可再生：__pycache__ / 工具缓存 / frontend/dist / 测试残留；硬白名单守卫数据目录）
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean.ps1            # 预演（加 -Apply 执行）
bash scripts/clean.sh                                                        # 预演（加 --apply 执行）

# 前端（统一 pnpm，勿用 npm/yarn —— 仓库只保留 pnpm-lock.yaml）
cd frontend
pnpm install
pnpm run dev        # http://localhost:27014，代理 /api 与 /storage 到 27015
pnpm run build
pnpm typecheck      # 类型检查（vue-tsc --noEmit，配置 tsconfig.json）
pnpm test           # vitest 单测
```

> 前端提交前门禁：`pnpm typecheck` + `pnpm test` + `pnpm run build` 三者全绿（与后端 `ruff` + `pytest` 对应）。
> **本项目不采用 CI（2026-09-22 决策）**：上述门禁一律在**本机**执行（`scripts/test.ps1` + 前端三门禁），发布前按「验收口径」逐项走；不要在仓库内新增 `.github/workflows` 等流水线配置。替代「机器强制」的手段是 **pre-push 钩子**（`.githooks/pre-push`，需各人自行执行一次 `git config core.hooksPath .githooks` 启用；临时跳过 `git push --no-verify`）。**成立前提、代价对照与重估触发条件**见 `docs/LOCAL_DEV_SETUP.md` §五。

开发态环境变量：`VP_DATABASE_URL=postgresql+asyncpg://<user>:<pass>@127.0.0.1:5432/vulnplatform`、`VP_REDIS_URL=redis://127.0.0.1:6379/0`、`VP_DISABLE_REDIS=0`、`VP_DISABLE_QUEUE=1`（后台任务进程内执行，免开 arq worker）、`VP_DEBUG=1`（dev 脚本已内置，凭据取自仓库根 `.env`）。

## 目录结构

```
backend/
  app/api/v1/      # 路由（auth, users, vulns, assets, reports, imports, dashboard, knowledge,
                   #   remote_testing / testing_plan / spring_action（专项三域）, nonpen, misc,
                   #   pats / open_api（个人访问令牌与开放只读 API）, audit（审计日志）, notify（通知渠道））
  app/core/        # config / deps / security / query（分页排序）/ filters（聚合筛选引擎）/ ratelimit / sanitize / timeutil / xlsx
  app/models/      # SQLAlchemy 模型
  app/schemas/     # Pydantic 模型包（common / auth / asset / vuln / knowledge / import_ / report / special / system，
                   #   对外经 schemas/__init__.py 统一重导出，调用方一律 from app.schemas import ...）
  app/services/    # 业务逻辑（状态机、docx 解析、导入入库 import_service、报告章节 report_html、
                   #   计划查询 plan_query / Excel plan_io、报告构建、导出、态势聚合 stats_service、
                   #   审计 audit_service、渠道通知 notify_service）
  app/constants.py # 全部枚举/字典与展示色值唯一来源（经 /meta 下发前端）
  app/workers/     # arq 后台任务
  alembic/         # 迁移（改模型后必须生成迁移）
  scripts/         # 运维/数据脚本（调试脚本放这里或删除，勿散落在 backend 根目录）
  tests/           # pytest 测试
frontend/
  src/api/         # axios 封装（唯一 HTTP 入口 client.ts）
  src/composables/ # 组合式函数（useListPage / useCrudDialog / useAssetSelect / useExportJobs / useDictOptions）
  src/components/  # 可复用组件（StatCard / FilterBuilder / VulnFormPanel ...）
  src/views/       # 页面视图
  src/utils/       # colors（字典展示唯一出口：meta 注册表）/ format（时间口径）/ download（blob 下载）/ chartTheme / html / tocNotice / cvss（CVSS 3.1 评分）
docs/              # DEPLOY / RELEASE / ROADMAP
```

## 后端编码规范

- **提交前静态检查必须全绿**（2026-09-17 审计引入）：`ruff check app scripts alembic tests` 与 `vulture app --min-confidence 80`。配置见 `backend/ruff.toml`：长行按**显示宽度** 120 计（CJK 记 2 列）；已按文件豁免 `app/schemas/__init__.py` 的 F401（按设计重导出）、`alembic/versions/*` 与 `scripts/seed_dev_data.py` 的 E501（迁移内容冻结 / 中文演示数据），豁免原因写在配置文件注释中。
- **Python 版本已对齐 3.12（2026-09-17）**：后端 venv 统一由 **uv** 管理，本地 `backend/.venv` 为 **3.12.11**，与容器/生产 `python:3.12-slim` 一致；ruff `target-version = "py312"`。venv 规格变更（重建 / 换版本）一律用 uv：`uv venv backend/.venv --python 3.12` + `uv pip install --python <venv 解释器> -r backend/requirements-dev.txt`。注意 Windows 解释器路径是 `.venv/Scripts/python.exe`（Linux 为 `.venv/bin/python`）；切换 venv 时旧目录保留为 `.venv.oldXXX`（已在 .gitignore 覆盖 `*.venv.*/` 模式）。
- **漏洞相关命名域（2026-09-18 修订，取代 2026-09-17 版；新代码强制）**：仓库现状并存两套写法，缺少成文规则会让新代码只能模仿。经**模型层实测校订**（旧版称"与 `import_records.vuln_id` 一致"，实测该列是 **`vul_id`**；全仓 `vul_id` 外键列 6 处、`vuln_id` 列仅 1 处）：
  - **实体域**（漏洞实体及其字段、模块、变量）新增标识符统一 **`vul_`** 前缀，新增外键列统一 **`vul_id`** —— 与现役 6 处 `vul_id` 外键列（`vuln_assets` / `vul_logs` / `vul_retest_records` / `import_records` / `report_sections` / `spring_action_vulns`）、模型 `Vul`、常量 `VUL_*` 一致；禁止新增 `vuln_id` 形式的列/字段，禁止新增 `Vuln*` 形式的实体类或 `vuln_*` 形式的实体域模块。
  - **字典域**（漏洞类型等字典）继续用 `Vuln*`：类 `VulnType`、表 `vuln_types`。字典域与实体域是两条轴，不得互相套用。
  - 常量一律 `VUL_*`（`VUL_TYPE`/`VUL_LEVEL`/`VUL_SOURCE`）。
  - **既成事实例外（保持现状，禁止在新增代码中扩散）**：表名 `vulns`（实体表）与 `vuln_assets`（关联表，其列名为 `vul_id`）；列 `remote_testings.vuln_id`；路由前缀 `/vulns` 与路由模块 `app/api/v1/vulns.py`（对外契约名，模块名与资源名一致）；Pydantic 模块 `app/schemas/vuln.py`（内部模型已是 `VulIn`/`VulOut`）；前端 `Vuln*` 族（前端命名约定 = **API 资源名**，与 `Report`/`Asset`/`Group` 同族、镜像路由 `/vulns`）。
  - 既有列名（`vul_type` / `vul_id` / `vul_edit_snapshot` / `remote_testings.vuln_id`）**保持不变**：库表列重命名须连同 Alembic 迁移一起做（见「数据库迁移（单轨）」条目），属独立专项；**当前决策：不做**（2026-09-18）。
- 字典/枚举与其展示色值只写在 `app/constants.py`，禁止在路由/服务内散落定义；改字典即全端生效（/meta 下发）。
- **聚合筛选条件树（2026-09-19，新代码强制）**：筛选条件统一为**条件树**（分组 `logic`/`not`/`children` + 规则 `field`/`op`/`value`/`not`），优先级只由嵌套层级表达。后端唯一解析/构造入口是 `app/core/filters.py` 的 `parse_filter_tree`（同时兼容历史 `{"rules": [...]}` 按 connector 左结合折叠）与 `build_tree_condition(node, leaf_builder)`——**接入方只需提供 leaf 构造器与字段白名单**（参考 `plan_query._plan_leaf_condition`），禁止各接口自写规则遍历；结构上限 `MAX_FILTER_DEPTH=5` / `MAX_FILTER_RULES=50`，非法结构 400。前端唯一实现是 `src/utils/filterTree.ts`（归一化 / 剪枝 / 序列化 / 表达式预览），编辑器为 `FilterBuilder.vue` + 递归的 `FilterGroupEditor.vue` + `FilterRuleRow.vue`，条件树类型（`FilterRule`/`FilterGroup`/`FilterNode`/`FilterFieldDef`）声明在 `src/types/index.ts`；**未填写完整的条件不参与请求但仍保留在界面**，界面须给出「实际生效条件」预览以保证所见即所查。
- 请求/响应模型写入 `app/schemas/` 对应域文件并在 `schemas/__init__.py` 重导出，禁止回填单文件或在路由文件内定义业务模型。
- 分页/排序统一走 `app/core/query.py` 的 `paginate` / `apply_sort` / `get_or_404`，不手写 limit/offset 样板；聚合筛选（filters JSON）复用 `app/core/filters.py` 引擎。
- 时间统一 `app/core/timeutil.py` 的 `now()`（UTC+8），禁止散落 `datetime.now()`。
- **数据库迁移（单轨，2026-09-21 起，改动必读）**：schema 演进的**唯一入口是 Alembic**（`backend/alembic/versions/`）。SQLite 开发库专用的 `app/db.py::_migrate_lightweight` 已随「统一 PostgreSQL 单栈」删除，**不存在第二条轨道，也没有兜底路径**——改模型后必须生成迁移，禁止只改模型不写迁移。新增 / 重命名 / 删除列须把废弃列登记到 `tests/test_schema_consistency.py::DEPRECATED_COLUMNS`（否则 PG 侧残留「NOT NULL 且无默认值」的僵尸列，任何 INSERT 直接 500，历史事故见 `remote_testings.appeal_success`）。`init_db()` 保留（全新库由 `create_all` 建表 + 内置角色/字典种子，`scripts/migrate.py` 依赖该决策做 stamp 纳管）。**禁止在 `app/` 内新增 SQLite 分支、驱动或 SQLite 默认 DSN**（守卫：`test_no_sqlite_driver_imports_in_app`、`test_default_database_url_is_postgresql`）。本地开发/测试库的搭建见 `docs/LOCAL_DEV_SETUP.md`。**单栈化的动因（结论）**：SQLite 与 PostgreSQL 的方言差异曾在**五个轴**上造成缺陷——类型/绑定严格性、外键强制、长度约束、结果集顺序确定性、DDL 能力（`ALTER COLUMN`/`USING` 转换），且这五个轴的差异在实际使用中都会给出「本地测不出」的假绿信号（发布史至少 7 例：如 `func.date(col) >= '<日期串>'` 的线上 500、删除漏洞漏置空 `remote_testings.vuln_id`、`affected_url` 定长溢出）。统一为单数据库栈后该类风险整体消失，双栈时期的跨方言守卫维护税（方言编译断言 + 双轨迁移守卫 + schema 一致性测试）随之消除——**这是「不得新增 SQLite 分支/驱动/默认 DSN」这条禁令的理由**。
- **渗透测试的时间口径（2026-09-19，改动必读）**：列表 / 统计 / 结论 / 导出共用的「时间范围」是**统计周期**，命中口径 = 初测完成 ∪ 复测发起 ∪ 复测完成 ∪ 复测报告生成 任一落入区间，唯一实现位置是 `plan_query._period_condition`（参数名沿用历史的 `first_test_from` / `first_test_to`）。**根因**：`testing_plans.retest_done_time` 与轮次 `done_time` 只在工单**全部漏洞闭环**时才写入（`vul_service.sync_plan_retest_state`，回退时还会清空），只看完成点必然漏掉「周期内发起但尚未闭环」的复测。新增任何含时间的筛选/统计前先复用该口径，**不得退化回单列过滤**。
- **DateTime 列禁止与日期字符串比较（2026-09-19 线上 500 事故，硬性）**：`func.date(col) >= '2026-09-14'` 会把日期串绑成 `VARCHAR`，PostgreSQL 无 `date >= character varying` 算子，asyncpg 抛 `UndefinedFunctionError` → 500。凡按「天」过滤 DateTime 列，一律用 `plan_query._datetime_date_range`（或同构的 `[当日 00:00, 次日 00:00)` 半开区间），既类型正确又不在列上套函数（可用索引）。守卫：`tests/test_plan_query.py::test_period_condition_uses_datetime_binds`（PostgreSQL 方言编译 + 绑定类型断言）。**推论**：即便测试库已是 PostgreSQL（2026-09-21），接口级用例也只在「恰好走到该分支且数据非空」时才暴露此类类型/绑定差异，方言级静态断言仍需保留。
- **复测标题 / 复测状态判定（唯一口径）**：标题是否含「复测」用 `plan_service.RETEST_TITLE_MARK`（Python 判定 `is_retest_report_title` 与 SQL `ilike` 共用同一常量）；报告维度三态 `none/ongoing/done` 由 `plan_service.retest_state_of` 单一函数产出（`PlanReportBrief` 与报告管理列表同口径），**禁止在前端或路由里另行推演**。报告 ←→ 复测轮次的结构化关联用 `TestingPlanRetestRound.src_report_id`（发起本轮的源报告），历史数据由 `scripts/backfill_retest_src_report.py` 回填，升级流程自动执行。
- 用户输入的富文本入库前必须过 `app/core/sanitize.py` 消毒（schemas 中用 `HtmlStr` 类型别名）。
- **附件/文件路径必须经 `app/core/storage.py`（2026-09-19 安全整改，新代码强制）**：写入侧 `require_attachment_path(rel, subdir=...)`（白名单 `uploads/<子目录>/<32 位十六进制>.<扩展名>`，非法即 400），读取/删除侧 `resolve_storage_path(rel)`（拒绝绝对路径/盘符/`..`/符号链接越界/不存在，统一 404）。**禁止 `settings.storage_path / <请求体或数据库字段>` 裸拼接**——该形态曾导致任意文件读取与删除（审计 TALOS-2026-001/002）。守卫：`tests/test_source_guard.py`。注意：写入校验放在路由层而非 pydantic 字段类型上，避免 Out 模型继承后对存量脏数据在序列化时判非法（列表/详情 500）。
- **服务端出站请求必须经 `app/core/outbound.py::assert_public_url()`（2026-09-19，新代码强制）**：目标来自用户输入时（现为通知渠道 webhook）在写入与发送前各校验一次，拒绝回环/私网/链路本地/共享地址/保留段，且不跟随重定向；内网中继用 `VP_NOTIFY_HOST_ALLOWLIST` 显式放行。`app/` 内**禁止直接 `urlopen` / `requests.*`**（守卫同上）。报告导出只内嵌 storage 内已本地化图片，**不再抓取远程图片**（TALOS-2026-004）。
- **非富文本字段拼进 HTML 前必须 `html.escape()`（2026-09-19）**：`HtmlStr` 仅覆盖富文本字段；纯文本字段（如 `VulRetestRecord.title`）拼接到 HTML 字符串时须显式转义（TALOS-2026-005）。
- **图片必须经鉴权端点下发（2026-09-19 批次 E，新代码强制）**：`/storage/uploads/images/<name>` 由 `app/api/images.py` 处理，依赖 `core.deps.get_image_viewer`（Cookie `vp_img` 或 Bearer）；**禁止回退为 `StaticFiles` 挂载**（守卫：`tests/test_source_guard.py`）。路径保持不变是刻意为之：报告导出的图片本地化依赖 `/storage/` 前缀，富文本内的 src 也无法逐张改造。浏览器侧凭证在登录/刷新/改密/`GET /auth/me` 时下发（`core/security.set_image_cookie`），退出登录走 `POST /auth/logout`。
- **用户可控出站目标 / 压缩包解析 / 未改密拦截的口径**：出站见 `core/outbound.py`；上传的 docx/xlsx 解析前必须过 `core/archive.py::assert_archive_quota`（zip 炸弹）；`must_change_password` 账号由 `core/deps._enforce_password_change` 在依赖层拦截（仅放行 `/auth/*` 与 `/meta`，403 带 `X-Must-Change-Password: 1`）。refresh 令牌轮换状态统一走 `core/token_store.py`（`jti` 一次性 + 宽限期，勿在路由里另存状态）。
- **图片凭证自愈不要删（2026-09-19 生产踩坑）**：`vp_img` Cookie 只在登录/刷新/改密/`GET /auth/me` 时下发，凭 `utils/imageAuth.ts` 在图片加载失败时补发凭证并重试一次——这是「升级后旧标签页整页裂图」以及 Cookie 过期场景的唯一自愈手段，移除会让用户必须手动刷新（该文件有单测 `utils/__tests__/imageAuth.spec.ts`）。
- Excel 响应统一 `app/core/xlsx.py` 的 `xlsx_response()`。
- 不留 print 调试语句；本地排查脚本命名 `_*.py` / `tmp_*.py`（已被 .gitignore 通配覆盖，不入库）。

> **函数体量口径**：单函数 **≤ 60 行**（AST 口径 `end_lineno - lineno + 1`）为常态；超出时优先拆分。**已成文的「合理长」保留形态**（已逐项复评，**不要重复提议拆分**）：
>
> | 保留形态 | 现存例子 | 保留理由 |
> |---|---|---|
> | 建表 → 迁移 → 种子三段直线 | `db.py::init_db` | 无嵌套分支 |
> | 解析状态机主循环 | `services/docx_parser.py::parse_report_docx` / `parse_docx` | 各段共享 meta / records / 样式上下文，拆分会引入大量跨函数状态传递 |
> | 语义敏感的状态同步 | `services/vul_service.py::sync_plan_retest_state` | 工单级复测口径的唯一实现且有回归护栏，可读性收益 < 误改风险 |
> | 单批事务主流程 | `services/import_service.py::confirm_batch_internal` | 拆分点会跨越 `commit` 边界（批量需按批次独立提交/回滚） |
> | 薄编排 / 响应组装 | `workers/main.py::export_report_task`、`api/v1/reports.py::retest_report` | 编排已下沉服务层，剩余为参数校验与组装 |
> | 以参数面/文档为主 | `api/v1/vulns.py::_build_vuln_conditions` | 逻辑体已拆净；若要再压应引入 `VulFilterQuery` 数据类，而非继续切函数 |

## 前端编码规范

- HTTP 请求只用 `src/api/client.ts` 的 `client`（含 token 刷新与统一错误提示），禁止散落 axios/fetch。
- 字典名称/色值唯一来源是后端 `/meta`，前端唯一出口为 `src/utils/colors.ts` 的 meta 注册表（`applyDictMeta` 由 `fetchMeta` 注入）；禁止建立字典镜像文件、禁止视图内硬编码字典色值。纯 UI 色板（`STAT_CARD_COLORS`）与 `style.css` 的 `--tl-*` 令牌 / `brand` 色板照旧；图表配色只用 `chartTheme.ts` 的 PALETTE。
- 表单校验统一 Element Plus `rules`（`:model` + `prop` + `formRef.validate()`），错误内联展示在字段下方；跨字段规则用自定义 validator；禁止提交前 `ElMessage.warning` 弹窗式校验。
- 时间格式化只用 `src/utils/format.ts`，禁止视图内 slice/replace。
- 文件下载只用 `src/utils/download.ts` 的 `saveBlob()`。
- 列表页（分页/排序/加载）、CRUD 弹窗、资产选择器、导出任务必须复用 `src/composables/` 对应组合式函数，禁止再复制样板。
- 领域类型统一声明在 `src/types/index.ts`（工单/漏洞/报告/导出记录等），页面与 composable 不得就地复制 `any` 或另起同名接口；新增字段先在该文件补声明（字段名与后端 API 一致，snake_case）。**新增代码不得引入 `any`**：确属边界（第三方写入的结构、用户输入 JSON）用 `unknown`，或在原处写明理由保留；类型收敛**不得改变运行时数据流**（`{...base, ...detail}` 必须保留 spread，只在边界做 `?? base.x` 归一）。`pnpm typecheck` 必须保持 **0 错误**。
- **弹窗/抽屉打开函数命名统一为 `open<Target>`**（2026-09-17 审计 F-2）：`useCrudDialog` 的打开函数为 `openFormDialog`，业务侧为 `openCreateAsset` / `openWorkflow` 等；组件对外 API 可直接导出 `open`（与 `@closed` 对称）。禁止再引入 `openDialog`、`onOpen` 这类无目标或事件式命名（`onXxx` 仅用于「事件回调」语义，不作为「打开」动作名）。
- 视图/组件冒烟测试统一复用 `src/__tests__/helpers/clientMock.ts`（`clientMockFactory()` + `getMock`），禁止在各 spec 内重复书写 axios client 的 `vi.mock` 样板。
- 状态标签统一 `tl-tag` 类 + `softStyle()` 柔和样式；表格行内允许「色点 + 文字」dot-tag 变体（等级/状态语义），色值仍走 colors.ts 字典注册表，禁止视图内硬编码。
- Tailwind 灰阶类（`text-gray-*` / `bg-gray-*` / `border-gray-*` / `bg-white`）已映射到 `--tl-gray-*` 令牌自动适配暗黑模式，可直接使用；新增样式优先用令牌，保证明暗两态可用。
- 日期区间选择器（`el-date-picker[type=daterange]`）的根节点即 `.el-input__wrapper`，Element Plus 给该类设了 `flex-grow: 1`；放进 flex 行（`.tl-filterbar` 或自写 `flex` 容器）会被拉伸撑满、`!w-*` 失效。固定宽度必须同时写 `!grow-0`（`flex-grow: 0 !important`）。

## UI 设计规范精要

风格：Linear 式暗色优先极简（视觉基准 `design-demos/demo-2`，本地设计稿不入库），信息优先、明暗双模式全覆盖。

- 品牌主色薄荷绿：浅色态交互/描边 #059669，主按钮用「薄荷底 + 深墨字」（或加深至 #047857），保证 ≥4.5:1；暗色态强调 #34D399、信息色淡蓝 #7DD3FC。风险五级色（浅色/暗色两套）：严重 #DC2626/#F87171 · 高危 #EA580C/#FB923C · 中危 #D97706/#FBBF24 · 低危 #0284C7/#7DD3FC · 安全 #059669/#34D399——字典色值以后端 `constants.py`（/meta 下发、前端 colors.ts 注册表消费）为准，本表仅供理解语义。
- 密度双档：默认正文 14px，紧凑档 13.5px（表格/工具栏/侧栏）；模块标题 13.5-15px/600，页面标题 14px/600 工具栏式（面包屑 + 标题）；间距以 4px 为最小刻度；圆角 4/6/8/10px 四档，浮层（弹窗/命令面板）允许 12px，禁止更大。
- 文本对比度分级：主要/次要文字 ≥ 4.5:1，弱化辅助文字（时间戳、占位符、分组标签）≥ 3:1，明暗两态都要达标；交互过渡 100-200ms，禁止闪烁/弹跳；图表入场动画豁免（≤ 1s、缓动收尾）。
- 表格行内等级/状态用「色点 + 文字」dot-tag 变体（不单靠颜色传义，无障碍）；筛选器/详情/表单仍用 `tl-tag` + `softStyle()`；kbd 风格灰签仅用于弱分类（如漏洞类型）。
- 弹窗：宽度三档 S=480 / M=640 / L=800；命令面板 560px 单列、不占弹窗层级（⌘K/Ctrl+K 全局唤起，支持页面跳转、动作与全局搜索，搜索结果需后端接口支持）；表单弹窗必须 `:close-on-click-modal="false"`；单场景仅一层弹窗，禁止多层嵌套。
- 删除确认：行内操作用 `el-popconfirm`，批量/危险操作用 `ElMessageBox.confirm` 且确认按钮 `el-button--danger`。
- 提交按钮必须绑定 `:loading` 防重复提交；列表/详情首屏必须有 `v-loading`，禁止空白闪现。
- 统计卡统一用 `StatCard` 组件（支持迷你趋势线变体）；空状态统一 `el-empty` + 引导文案；数字与时间用 tabular-nums（关键指标可用等宽字体），格式化仍走 `format.ts`。

## 测试规范（强制）

**位置与命名**：

| 端 | 位置 | 命名 | 运行 |
|---|---|---|---|
| 后端 | `backend/tests/` | `test_<模块>.py`（如 `test_parser.py` 对应 `services/docx_parser.py`） | `cd backend && .venv/Scripts/python -m pytest` |
| 后端（API 集成） | `backend/tests/api/` | `test_api_<领域>.py`（按领域拆分；共享 helper `_helpers.py`，模块须可单独运行） | 同上，或 `-Workers 4` 并行 |
| 前端 | 与被测模块同目录的 `__tests__/` 子目录 | `<被测模块名>.spec.ts`（如 `src/utils/__tests__/download.spec.ts`） | `cd frontend && pnpm test` |

**规则**：

- 新增功能或修 bug 时优先补测试；后端 API 变更必须同步更新**对应领域模块**（`backend/tests/api/test_api_<领域>.py`，共享 helper 在 `tests/api/_helpers.py`；原先的 4626 行单体 `test_api.py` 已于 2026-09-22 按领域拆分）。
- 测试不得依赖仓库外/外部文件（后端 docx 样例在测试内用 python-docx 现造，参考 `test_parser.py` 的 `_make_docx`）。
- 测试产物（db / 临时文件）必须由 fixture teardown 自清理（参考 `conftest.py` 的 session 收尾），禁止依赖 .gitignore 兜底。
- **改模型或迁移必须保持 `tests/test_migrations.py` 绿**：它在独立 schema 里真跑 `alembic upgrade head`，断言迁移建出的表/列与模型声明一致，并验证 `downgrade base` 能回到空 schema —— 单轨化后 Alembic 是 schema 演进的唯一路径，这是**唯一真正执行迁移**的测试（其余用例走 `create_all`）。
- 前端纯逻辑（composables / utils）为单测优先覆盖对象；组件测试按需引入 `@vue/test-utils`。

**验收口径（改动涉及运行时必做）**：

- **后端**：`ruff` + `vulture` 全绿 + **全量 pytest**（基线 **293 passed / 1 skipped**，测试库为 PostgreSQL；统一入口 `scripts/test.ps1` / `scripts/test.sh`，提速加 `-Workers 4` / `--workers 4`）+ **前后端契约检查**（`python -m scripts.check_api_contract`，不连库；「前端声明但 API 不返回」即失败）。
- **前端**：`pnpm typecheck`（**0 错误**）+ `pnpm test`（基线 **24 files / 138 passed**）+ `pnpm run build`。
- **端到端（E2E）**（涉及前端交互或前后端联调时）：`pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\e2e.ps1`（或 `bash scripts/e2e.sh`）—— 自动起**独立 E2E 栈**（`vulnplatform_e2e` 库 + api 27016 + 前端 27017 + 独立 storage），跑 3 条黄金链路（登录 / 新建漏洞含影响URL 批量粘贴 / 报告编辑器渲染），每条都断言**控制台 0 error**。只有 3 条是**刻意**的：广度仍由分级浏览器冒烟负责，E2E 的维护成本与抖动风险不允许铺页面（取舍见 `playwright.config.ts`）。
- **运行时改动必须在 WSL-Kali 重建镜像**后验证：`docker compose build api worker frontend && docker compose up -d` —— 容器源码为**镜像内置**，不重建则改动不生效（导入解析与报告导出跑在 worker，务必与 api 一并重建）。
- **接口探针**：`cd backend && .venv/Scripts/python -m scripts.probe_api --base-url <地址>`（**已固化为脚本，不再手写临时脚本**；22 个关键接口清单见脚本 `ENDPOINTS`，**全部 200 视为通过**，任一失败退出码 1 并打印明细）。地址：本地开发 `http://127.0.0.1:27015`、容器经前端反代 `http://127.0.0.1:27012`、容器内直连 `http://127.0.0.1:8000`。登录必须用 **form 表单**而非 JSON（`POST /api/v1/auth/login`）；本地 dev 库账号 `admin/admin123`，容器数据为 `admin1/123456`，用 `--username/--password` 覆盖。
- **浏览器冒烟**（前端改动）：Chrome DevTools 逐页检查**控制台 0 错误/警告** + 关键 DOM（表格行、抽屉步骤条等）渲染；**默认不执行写操作**，避免污染共享数据。**按影响面分级执行**（2026-09-22 起，避免每次改动都跑满 12 页）：
  - **发布前（广度）**：12 组页面 —— `/dashboard`、`/testing-plans`（含流程抽屉 6 步）、`/nonpen-plans`、`/vulns`、`/reports`、`/knowledge`、`/assets` + `/assets/groups`、`/users`、`/roles`、`/tokens`、`/notify-channels`、`/audit`（建议同时覆盖专项三域的 `/remote-testings`、`/spring-actions`）。判据：控制台 0 错误/警告 + 表格/抽屉有真实数据渲染 + 该页 XHR 全 200；
  - **日常改动（深度）**：只跑**受影响页面**（改报告编辑器 → `/reports` + `/reports/:id`；改工单 → `/testing-plans` + `/nonpen-plans`；改导入 → `/reports/imports`），其余留待发布前；
  - **纯逻辑 / 类型改动**（无 UI 行为变化）：可省略浏览器冒烟，以三门禁 + `vitest` 为准。

## 文档治理

- `docs/` 只保留**长期有效**的文档：`DEPLOY.md`（部署/备份/回滚/排障）、`LOCAL_DEV_SETUP.md`（本地开发环境搭建与排障，含 DBngin 操作与测试口径）、`RELEASE.md`（发布史，唯一真相源）、`ROADMAP.md`（未来计划）、`SCRIPTS.md`（脚本清单）、`OPEN_API_GUIDE.md`、`USER_GUIDE.md`，以及**尚未闭环**的专项报告。
- **任务型文档**（审计报告、事故复盘、单次排查报告、批次执行记录）在满足以下三条后**删除**，删除前先归并内容：
  1. **任务闭环** —— 验收项全部打勾，或未打勾项已明确转为待办；
  2. **有价值结论已归并** —— 规范/阈值/坑 → 本文件；运维与排障操作 → `DEPLOY.md`；脚本用途 → `SCRIPTS.md`；跨会话事实 → `.codebuddy/memory/`；
  3. **引用点已修正** —— 用 `rg <文档名>` 确认无悬空引用（含代码/配置注释）。
- 删除写进当次提交信息；**git 历史即归档**（`git show <sha>:docs/<name>.md` 可取回）。
- **未闭环的专项报告不得删除**：如 `docs/SECURITY_AUDIT_*.md` 在漏洞修复 + 负责人复验完成前必须保留（它是修复行动的唯一真相源）。

## 发布约定

版本号遵循 SemVer，三处必须同步修改：`backend/app/core/config.py` 的 `APP_VERSION`、`frontend/package.json` 的 `version`、`docs/RELEASE.md`（唯一版本记录真相源，Keep a Changelog 风格）。登录页右下角版本号由 Vite 构建时从 `frontend/package.json` 注入（`vite.config.ts` 的 `__APP_VERSION__`），随前端版本号自动同步，无需单独维护。

路线与规划见 `docs/ROADMAP.md`；部署手册见 `docs/DEPLOY.md`。
