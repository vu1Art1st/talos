# AGENTS.md — Talos 项目约定与规范

本文件是仓库内唯一的项目规范入口，供所有协作者与 AI 编码工具遵循。

## 项目概述

Talos 漏洞管理平台：漏洞全生命周期管理（前身洞察 2.0 / insight2 的现代化重写）。

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic · arq + Redis |
| 前端 | Vue 3 (`<script setup>` + TS) · Vite · Pinia · Element Plus · TailwindCSS · ECharts · TipTap 2 |
| 数据库 | 开发 SQLite（免队列），生产 PostgreSQL 16 |
| 部署 | Docker Compose（api / worker / frontend / postgres / redis / gotenberg） |

## 常用命令

```bash
# 一键本地开发（Windows / Linux-macOS，SQLite + 免队列，自动建 venv 与装依赖）
powershell -ExecutionPolicy Bypass -File .\dev.ps1
bash dev.sh

# 后端（始终用 backend/.venv 解释器，禁止系统 python）
cd backend
uv venv .venv --python 3.12                 # 创建/重建 venv（uv 管理，与容器 python:3.12-slim 对齐）
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt   # 安装/同步依赖
.venv/Scripts/python -m pytest              # 运行全部测试
.venv/Scripts/python -m uvicorn app.main:app --reload --port 27015
.venv/Scripts/python -m ruff check app scripts alembic tests   # 静态检查（配置 backend/ruff.toml）
.venv/Scripts/python -m vulture app --min-confidence 80        # 死代码检查

# 前端（统一 pnpm，勿用 npm/yarn —— 仓库只保留 pnpm-lock.yaml）
cd frontend
pnpm install
pnpm run dev        # http://localhost:27014，代理 /api 与 /storage 到 27015
pnpm run build
pnpm typecheck      # 类型检查（vue-tsc --noEmit，配置 tsconfig.json）
pnpm test           # vitest 单测
```

> 前端提交前门禁：`pnpm typecheck` + `pnpm test` + `pnpm run build` 三者全绿（与后端 `ruff` + `pytest` 对应）。

开发态环境变量：`VP_DATABASE_URL=sqlite+aiosqlite:///./dev.db`、`VP_DISABLE_QUEUE=1`、`VP_DEBUG=1`（dev 脚本已内置）。

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
  - 既有列名（`vul_type` / `vul_id` / `vul_edit_snapshot` / `remote_testings.vuln_id`）**保持不变**：库表列重命名须连同 Alembic 与 `db.py` 轻量迁移双轨一起做（见「数据库迁移」约定），属独立专项；**当前决策：不做**（2026-09-18）。
- 字典/枚举与其展示色值只写在 `app/constants.py`，禁止在路由/服务内散落定义；改字典即全端生效（/meta 下发）。
- 请求/响应模型写入 `app/schemas/` 对应域文件并在 `schemas/__init__.py` 重导出，禁止回填单文件或在路由文件内定义业务模型。
- 分页/排序统一走 `app/core/query.py` 的 `paginate` / `apply_sort` / `get_or_404`，不手写 limit/offset 样板；聚合筛选（filters JSON）复用 `app/core/filters.py` 引擎。
- 时间统一 `app/core/timeutil.py` 的 `now()`（UTC+8），禁止散落 `datetime.now()`。
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
> | 幂等 DDL 顺序表 | `db.py::_migrate_lightweight` | 逐列「查 PRAGMA → ALTER」直线逻辑；拆分会反复传 `conn`/列集合，破坏「一段一表」的顺序可读性 |
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
| 前端 | 与被测模块同目录的 `__tests__/` 子目录 | `<被测模块名>.spec.ts`（如 `src/utils/__tests__/download.spec.ts`） | `cd frontend && pnpm test` |

**规则**：

- 新增功能或修 bug 时优先补测试；后端 API 变更必须同步更新 `test_api.py`。
- 测试不得依赖仓库外/外部文件（后端 docx 样例在测试内用 python-docx 现造，参考 `test_parser.py` 的 `_make_docx`）。
- 测试产物（db / 临时文件）必须由 fixture teardown 自清理（参考 `conftest.py` 的 session 收尾），禁止依赖 .gitignore 兜底。
- 前端纯逻辑（composables / utils）为单测优先覆盖对象；组件测试按需引入 `@vue/test-utils`。

**验收口径（改动涉及运行时必做）**：

- **后端**：`ruff` + `vulture` 全绿 + **全量 pytest**（基线 **189 passed / 1 skipped**）。
- **前端**：`pnpm typecheck`（**0 错误**）+ `pnpm test`（基线 **24 files / 138 passed**）+ `pnpm run build`。
- **运行时改动必须在 WSL-Kali 重建镜像**后验证：`docker compose build api worker frontend && docker compose up -d` —— 容器源码为**镜像内置**，不重建则改动不生效（导入解析与报告导出跑在 worker，务必与 api 一并重建）。
- **接口探针**（容器内执行）：`docker compose exec -T api python - < 探针脚本`（脚本用完即删；`_*.py` 已被 .gitignore 覆盖）。登录必须用 **form 表单**而非 JSON（`POST /api/v1/auth/login`，`username=admin1&password=123456`），取 token 后依次 GET 22 个关键接口：`/meta`、`/vulns`、`/vulns/stats`、`/reports`、`/testing-plans`、`/testing-plans/stats`、`/testing-plans/conclusion`、`/nonpen-plans`、`/nonpen-plans/stats`、`/remote-testings`、`/spring-actions`、`/knowledge`、`/knowledge/search?q=注入`、`/search?q=a`、`/assets`、`/users`、`/roles`、`/groups`、`/pats`、`/notify-channels`、`/audit/logs`、`/imports` —— **全部 200 视为通过**。
- **浏览器冒烟**（前端改动）：Chrome DevTools 逐页检查**控制台 0 错误/警告** + 关键 DOM（表格行、抽屉步骤条等）渲染；**默认不执行写操作**，避免污染共享数据。

## 文档治理

- `docs/` 只保留**长期有效**的文档：`DEPLOY.md`（部署/备份/回滚/排障）、`RELEASE.md`（发布史，唯一真相源）、`ROADMAP.md`（未来计划）、`SCRIPTS.md`（脚本清单）、`OPEN_API_GUIDE.md`、`USER_GUIDE.md`，以及**尚未闭环**的专项报告。
- **任务型文档**（审计报告、事故复盘、单次排查报告、批次执行记录）在满足以下三条后**删除**，删除前先归并内容：
  1. **任务闭环** —— 验收项全部打勾，或未打勾项已明确转为待办；
  2. **有价值结论已归并** —— 规范/阈值/坑 → 本文件；运维与排障操作 → `DEPLOY.md`；脚本用途 → `SCRIPTS.md`；跨会话事实 → `.codebuddy/memory/`；
  3. **引用点已修正** —— 用 `rg <文档名>` 确认无悬空引用（含代码/配置注释）。
- 删除写进当次提交信息；**git 历史即归档**（`git show <sha>:docs/<name>.md` 可取回）。
- **未闭环的专项报告不得删除**：如 `docs/SECURITY_AUDIT_*.md` 在漏洞修复 + 负责人复验完成前必须保留（它是修复行动的唯一真相源）。

## 发布约定

版本号遵循 SemVer，三处必须同步修改：`backend/app/core/config.py` 的 `APP_VERSION`、`frontend/package.json` 的 `version`、`docs/RELEASE.md`（唯一版本记录真相源，Keep a Changelog 风格）。登录页右下角版本号由 Vite 构建时从 `frontend/package.json` 注入（`vite.config.ts` 的 `__APP_VERSION__`），随前端版本号自动同步，无需单独维护。

路线与规划见 `docs/ROADMAP.md`；部署手册见 `docs/DEPLOY.md`。
