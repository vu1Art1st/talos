# Talos 版本发布记录（Release Notes）

本文档记录 Talos 漏洞管理平台的每次版本更新,格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## 版本号规则

版本号遵循 [语义化版本 Semantic Versioning](https://semver.org/lang/zh-CN/) `x.y.z` 管理:

| 位 | 名称 | 递增条件 |
| --- | --- | --- |
| `x` | 主版本号(Major) | 不兼容的重大变更:API 破坏性调整、数据库结构不兼容迁移、架构级重构 |
| `y` | 次版本号(Minor) | 向下兼容的功能新增或明显的用户可见变化 |
| `z` | 修订号(Patch) | 向下兼容的问题修复、小优化、文档 / 构建脚本调整 |

当前处于 `0.y.z` 快速迭代阶段:从 `0.1.0` 起步,功能新增递增 `y`、修复递增 `z`;待确认可发布正式版后再进入 `1.0.0`。

发布约定:

- 每次发布需同步更新三处版本号:本文档、`backend/app/core/config.py` 的 `APP_VERSION`、`frontend/package.json` 的 `version`
- 发布后在 git 上打注解标签:`git tag -a v x.y.z -m "release x.y.z"`
- 变更条目按类型分组:`新增(Added)` / `变更(Changed)` / `修复(Fixed)` / `移除(Removed)` / `安全(Security)`
- 未发布的改动先记入「Unreleased」,发布时移入对应版本段落

---

## [Unreleased]

（暂无）

---

## [0.8.0] - 2026-07-31

列表页排序能力全覆盖、测试计划与报告导出体验改进，并补充团队内部用户手册。

### 新增

- 列表页按列排序：资产 / 漏洞 / 用户 / 测试计划 / 春耕行动 / 远程检测列表新增 `sort`、`order` 查询参数，后端 `core/query.py` 提供 `apply_sort` 白名单排序助手（合法字段追加 `id` 降序保证分页稳定），对应前端列表启用可排序表头（服务端 `sortable="custom"` + `@sort-change`，知识库为本地排序）
- 漏洞录入 / 详情支持「影响 URL」多值：`VulnEdit.vue` 多行录入（增删行），`VulnDetail.vue` 逐行展示，后端沿用单字段以换行分隔存储
- 团队内部用户手册 `docs/USER_GUIDE.md`（含系统概述、功能模块、使用步骤及界面截图 `docs/images/`）

### 变更

- 测试计划页漏洞统计徽章双模式：数量 > 0 深底白字（醒目），= 0 浅底深字（弱化）；「导入模板」按钮文案改为「导入模板下载」
- 报告导出（`report_builder`）：封面第二行改填系统名称（`project_name`）；风险问题汇总统计段仅计入未修复漏洞，汇总表已修复状态显示绿色；风险问题详情「测试状态」按漏洞最新 `is_retest` 重写，复测未通过正确显示「复测」
- 报告版本号语义拆分：编辑保存改用 `revision` 乐观锁自增，导出版本 `version` 仅在导出成功时 +1（Word 导入关联报告的追加章节亦计入 `revision`）
- 报告导出时若测试周期为空自动预填：开始日期取关联漏洞最早提交日期，结束日期取当天
- 漏洞知识库列表默认排序改为按危害等级优先（危害等级 → 漏洞类型 → ID）

### 修复

- 报告导出 Word 打开后目录不自动刷新：`w:updateFields` 此前插入到 `settings` 首位违反 OOXML `CT_Settings` 元素顺序被 Word 忽略，改为插入到 `w:hdrShapeDefaults` / `w:compat` 等锚点之前
- 测试计划页「关联报告数量」统计偏少：手动新建报告或从漏洞生成未选计划时报告缺少 `testing_plan_id`，现按章节漏洞唯一归属计划自动回写

---

## [0.7.0] - 2026-07-31

漏洞知识库升级：新增漏洞名称与危害等级两列，预置 50 个常见漏洞标准信息，支持批量导入 / 批量删除 / 编辑的完整 CRUD。

### 新增

- 漏洞知识库新增「漏洞名称」（`vulnerability_name`，全库唯一）与「危害等级」（`severity_level`，沿用 `VUL_LEVEL` 字典）两个字段；条目粒度由「每漏洞类型一条」升级为「每漏洞名称一条」，同一漏洞类型可沉淀多条具体漏洞
- 预置 50 个最常见漏洞标准数据（SSRF、SQL 注入、未授权访问、水平 / 垂直越权、XXE、命令注入、文件上传、弱口令等），提供幂等录入脚本 `backend/scripts/seed_knowledge.py`
- 知识库批量导入接口 `POST /knowledge/batch-import`（按漏洞名称 upsert，单次至多 500 条，批内查重与字典码校验，整批事务性）
- 知识库批量删除接口 `POST /knowledge/batch-delete`（按 ID 列表删除）
- 知识库按 ID 编辑接口 `PUT /knowledge/{id}`（支持改名并校验名称唯一）
- 知识库页面 `KnowledgeList.vue` 新增漏洞名称 / 危害等级列、多选批量删除、JSON 批量导入弹窗（支持文件选择与示例模板下载）

### 变更

- `GET /knowledge/by-type/{vul_type}` 与 Word 导入回填在同类型多条时，返回危害等级最高、最早创建的一条模板
- `POST /knowledge/from-vul/{id}` 改为按漏洞标题作为知识库条目名称 upsert，并携带漏洞等级
- 知识库数据验证增强：漏洞名称非空校验、危害等级 / 漏洞类型字典码校验、参考链接仅允许 http(s) 协议

---

## [0.6.0] - 2026-07-31

前端视觉改版：全站明 / 暗双主题与 UI 现代化。

### 新增

- 全站明 / 暗双主题：顶栏一键切换，`stores/theme.ts` 持久化到 localStorage，Element Plus dark css-vars 与 ECharts 明 / 暗双主题（`utils/chartTheme.ts`）联动
- 侧边栏可折叠（图标模式，状态持久化）
- 首次登录 / 密码重置强制改密弹窗：不可关闭，修改密码（至少 8 位）后方可使用系统

### 变更

- UI 现代化改版：引入设计令牌 CSS 变量层（`--tl-*`），品牌主色改为靛蓝 `#4F46E5`，卡片圆角细边框、表头浅底、柔和胶囊标签、页面路由过渡动画
- 登录页 / 主布局 / 仪表盘等页面视觉重构，菜单图标与圆角胶囊选中态，品牌 Logo 渐变色块

> 注：本版本内容随提交 `87af5a4` 与 0.5.0 一并入库，发布记录补录于此。

## [0.5.0] - 2026-07-30

报告编辑与复测闭环增强、测试计划人天与 Excel 导入导出、全面安全加固。

### 新增

- 漏洞复测记录：`VulRetestRecord` 模型与 `/vulns/{id}/retests` CRUD 接口，新增独立复测处理页 `VulnRetest.vue` 及路由
- 报告编辑页章节导航栏：点击平滑滚动定位并高亮当前章节
- 报告编辑页漏洞字段改为固定下拉框（等级 / 类型 / 所在层 / 状态），`PATCH /vulns/{id}/fields` 即时保存
- 测试计划增强：预估 / 实际人天字段，Excel 导出（明细 + 统计汇总双 sheet）、导入模板下载与批量导入（按 ID upsert，测试人员按姓名 / 用户名匹配），统计汇总（初测 / 复测次数、人天合计、按状态与月度漏洞分布），计划详情展示关联报告
- 仪表盘（安全态势）多维筛选：时间范围 / 部门 / 来源 / 等级，统计口径联动
- 组织（用户组）管理页 `GroupList.vue`；PDF 预览组件 `PdfPreviewDialog.vue`
- 环境变量样例文件 `.env.example`

### 变更

- Word 导出改用渗透测试报告模板（`backend/app/templates/report_template.docx`，可由 `VP_REPORT_TEMPLATE` 覆盖）：封面 / 版本变更记录 / 适用性声明 / 目录 / 测试目标 / 时间与人员 / 风险汇总统计 / 风险详情自动填充，目录页码在 Word 打开时自动刷新
- 报告新增「被测系统IP」字段（编辑器可填，导出填入测试目标表）；被测 URL / 域名由关联资产自动聚合
- 漏洞章节初始内容对齐模板标签结构（测试状态 / 漏洞等级 / 漏洞链接 / 描述 / 证明 / 修复建议 / 复测详情）；导出文案层面等级「严重」映射为「超危」
- 前端包管理迁移至 pnpm（`pnpm-lock.yaml` / `pnpm-workspace.yaml`）
- 后端公共查询助手 `paginate` / `get_or_404` 重构各列表与详情接口；新增 `timeutil.utcnow` 统一时间获取

### 修复

- 报告与测试计划状态由单向改为双向同步：漏洞回退未修复时报告回退 `draft`、测试计划回退「复测中」并重开复测轮次

### 安全

- 登录防爆破：同一用户名 + IP 失败达阈值锁定（`VP_LOGIN_MAX_FAILURES` / `VP_LOGIN_LOCK_SECONDS`），Redis 计数、不可用时降级进程内存
- JWT 引入令牌版本号 `token_version`：修改密码 / 禁用账号即失效全部存量令牌，改密接口下发新令牌
- 生产环境（`DEBUG=False`）拒绝默认占位或不足 32 字符的 `VP_SECRET_KEY`，启动即校验
- CORS 收窄为白名单 `VP_CORS_ORIGINS` 且关闭凭证共享；生产环境关闭 `/api/docs` 与 OpenAPI 端点
- 富文本双端 XSS 清洗：后端所有入库 `*_html` 字段经 nh3 白名单过滤，前端渲染统一走 DOMPurify（`utils/html.ts`）
- `storage` 静态托管收窄至公开图片目录 `uploads/images`，导出 / 导入原始文档改走鉴权接口，nginx 代理同步收窄
- 内置 admin 初始口令不再固定：`VP_INITIAL_ADMIN_PASSWORD` 指定或随机生成（日志仅显示一次），首次登录强制改密
- docker-compose 敏感配置改由 `.env` 注入（`POSTGRES_PASSWORD` / `VP_SECRET_KEY` 必填）；后端容器改非 root 用户运行，前端改用 nginx-unprivileged（8080 端口）
- 新增 `defusedxml` 依赖加固 docx 解析，防 XXE

## [0.4.0] - 2026-07-28

应用与资产合并重构:统一资产模型 + 漏洞多对多关联。

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

## [0.3.0] - 2026-07-27

平台品牌更名为 **Talos**。

### 变更

- 平台整体更名 Talos:前端品牌标识、后端 `APP_NAME`、README 同步调整(`8d931df`)
- 浏览器页签标题补充 Talos 品牌(`9e9625e`)

### 修复

- `dev.ps1` 改用 UTF-8 BOM 编码,兼容 Windows PowerShell 5 下的中文输出(`5b879fa`)

## [0.2.0] - 2026-07-27

体验优化与开发效率提升。

### 新增

- 一键本地开发脚本 `dev.ps1` / `dev.sh`,单命令拉起前后端开发环境(`4530d4b`)
- 功能规划文档 `docs/ROADMAP.md`,包含 SLA 管理、知识库、审计等 8 项功能设计(`702f8ec`)

### 变更

- 统一漏洞等级与状态配色规范:严重深红 / 高危红 / 中危橙 / 低危蓝 / 安全绿(`33a9d5c`)

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
