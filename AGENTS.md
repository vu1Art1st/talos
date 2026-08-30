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
.venv/Scripts/python -m pytest              # 运行全部测试
.venv/Scripts/python -m uvicorn app.main:app --reload --port 27015

# 前端（统一 pnpm，勿用 npm/yarn —— 仓库只保留 pnpm-lock.yaml）
cd frontend
pnpm install
pnpm run dev        # http://localhost:27014，代理 /api 与 /storage 到 27015
pnpm run build
pnpm test           # vitest 单测
```

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

- 字典/枚举与其展示色值只写在 `app/constants.py`，禁止在路由/服务内散落定义；改字典即全端生效（/meta 下发）。
- 请求/响应模型写入 `app/schemas/` 对应域文件并在 `schemas/__init__.py` 重导出，禁止回填单文件或在路由文件内定义业务模型。
- 分页/排序统一走 `app/core/query.py` 的 `paginate` / `apply_sort` / `get_or_404`，不手写 limit/offset 样板；聚合筛选（filters JSON）复用 `app/core/filters.py` 引擎。
- 时间统一 `app/core/timeutil.py` 的 `now()`（UTC+8），禁止散落 `datetime.now()`。
- 用户输入的富文本入库前必须过 `app/core/sanitize.py` 消毒（schemas 中用 `HtmlStr` 类型别名）。
- Excel 响应统一 `app/core/xlsx.py` 的 `xlsx_response()`。
- 不留 print 调试语句；本地排查脚本命名 `_*.py` / `tmp_*.py`（已被 .gitignore 通配覆盖，不入库）。

## 前端编码规范

- HTTP 请求只用 `src/api/client.ts` 的 `client`（含 token 刷新与统一错误提示），禁止散落 axios/fetch。
- 字典名称/色值唯一来源是后端 `/meta`，前端唯一出口为 `src/utils/colors.ts` 的 meta 注册表（`applyDictMeta` 由 `fetchMeta` 注入）；禁止建立字典镜像文件、禁止视图内硬编码字典色值。纯 UI 色板（`STAT_CARD_COLORS`）与 `style.css` 的 `--tl-*` 令牌 / `brand` 色板照旧；图表配色只用 `chartTheme.ts` 的 PALETTE。
- 表单校验统一 Element Plus `rules`（`:model` + `prop` + `formRef.validate()`），错误内联展示在字段下方；跨字段规则用自定义 validator；禁止提交前 `ElMessage.warning` 弹窗式校验。
- 时间格式化只用 `src/utils/format.ts`，禁止视图内 slice/replace。
- 文件下载只用 `src/utils/download.ts` 的 `saveBlob()`。
- 列表页（分页/排序/加载）、CRUD 弹窗、资产选择器、导出任务必须复用 `src/composables/` 对应组合式函数，禁止再复制样板。
- 状态标签统一 `tl-tag` 类 + `softStyle()` 柔和样式；表格行内允许「色点 + 文字」dot-tag 变体（等级/状态语义），色值仍走 colors.ts 字典注册表，禁止视图内硬编码。
- Tailwind 灰阶类（`text-gray-*` / `bg-gray-*` / `border-gray-*` / `bg-white`）已映射到 `--tl-gray-*` 令牌自动适配暗黑模式，可直接使用；新增样式优先用令牌，保证明暗两态可用。

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

## 发布约定

版本号遵循 SemVer，三处必须同步修改：`backend/app/core/config.py` 的 `APP_VERSION`、`frontend/package.json` 的 `version`、`docs/RELEASE.md`（唯一版本记录真相源，Keep a Changelog 风格）。

路线与规划见 `docs/ROADMAP.md`；部署手册见 `docs/DEPLOY.md`。
