# Talos 版本发布记录（Release Notes）

本文档记录 Talos 漏洞管理平台的每次版本更新,格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## 版本号规则

版本号遵循 [语义化版本 Semantic Versioning](https://semver.org/lang/zh-CN/) `x.y.z` 管理:

| 位 | 名称 | 递增条件 |
| --- | --- | --- |
| `x` | 主版本号(Major) | 不兼容的重大变更:API 破坏性调整、数据库结构不兼容迁移、架构级重构 |
| `y` | 次版本号(Minor) | 向下兼容的功能新增或明显的用户可见变化 |
| `z` | 修订号(Patch) | 向下兼容的问题修复、小优化、文档 / 构建脚本调整 |

当前已进入正式版 `1.0.0`：进入语义化版本正式阶段，功能新增递增 `y`、修复递增 `z`、重大不兼容变更才递增 `x`。

发布约定:

- 每次发布需同步更新三处版本号:本文档、`backend/app/core/config.py` 的 `APP_VERSION`、`frontend/package.json` 的 `version`
- 发布后在 git 上打注解标签:`git tag -a v x.y.z -m "release x.y.z"`
- 变更条目按类型分组:`新增(Added)` / `变更(Changed)` / `修复(Fixed)` / `移除(Removed)` / `安全(Security)`
- 未发布的改动先记入「Unreleased」,发布时移入对应版本段落

---

## [1.0.0] - 2026-08-10

正式发布版本。新增与「渗透测试计划」平级的「非渗透计划」模块（主机 / Web / 基线扫描独立管理、测试项状态流转与次数统计、与测试计划联动双向同步 / 级联删除），工单ID分配抽取为两表共享当日序号序列的 `ticket_service`；测试计划更名为「渗透测试计划」；实际人天支持手动修正；文档整理（移除 USER_GUIDE.md 与 ID-RENUMBERING-EVALUATION.md，新增《非渗透计划模块需求与设计》）。

### 新增

- **实际人天手动修正**（`frontend/src/views/TestingPlanList.vue` / `backend/app/services/plan_service.py` / `special.py`）：测试计划对话框的实际人天字段新增「修正」入口，点击后进入手动输入状态（不再被初测报告时间自动覆盖），按钮切换为「取消修正」；取消修正后由系统按初测报告重新计算覆盖该字段，恢复自动计算值
- **非渗透计划模块**（`frontend/src/views/NonpenPlanList.vue` / `frontend/src/components/NonpenPlanWorkflowDrawer.vue` / `frontend/src/constants/nonpen.ts` / `backend/app/api/v1/nonpen.py` / `backend/app/services/nonpen_service.py` / `backend/app/services/ticket_service.py`）：与「测试计划」平级的新模块，独立管理主机 / Web / 基线三类扫描测试项的状态流转（未开始→初测中→等待复测→复测中→复测完成，任意阶段可忽略，取消忽略恢复未开始且次数清零）、初测 / 复测次数统计与五张统计卡片、工单ID与测试计划**共享当日序号序列**
- **测试计划「创建非渗透」联动**（`TestingPlanList.vue` / `special.py`）：测试计划新增表单勾选「创建非渗透」（新功能角标），勾选后展开测试项选择；保存时同工单自动生成联动非渗透计划（共享工单ID与接收日期，列表展示「联动」角标）；编辑任一方公共字段**双向同步**，删除任一方**互相级联**；非渗透计划不关联漏洞 / 报告 / 人天（业务独立，复用 `special:manage` 权限）

### 变更

- **「测试计划」更名为「渗透测试计划」**：侧边栏菜单 / 页面标题 / 弹窗 / 按钮 / 空态 / 提示语全部更新为「渗透测试计划」；Excel 导出与导入模板的 sheet 名称、文件名、表头同步更新为「渗透测试计划」；后端错误提示同步更新。路由与 API 路径保持 `/testing-plans` 不变，避免破坏既有链接与权限

### 修复

- **非渗透计划扫描次数统计口径**（`backend/app/services/nonpen_service.py`）：统计卡片「基线 / 主机 / Web 扫描次数」原按「初测次数 + 复测次数」累加，导致同一测试项初测复测被计算两次；改为按「初测次数」统计，初测与复测针对同一测试项合计按一次计（复测多次也不重复计数）
- **非渗透计划流程抽屉空白**（`frontend/src/components/NonpenPlanWorkflowDrawer.vue`）：组件常驻但仅在首次挂载时 `load()`，打开时 `planId` 已设置却未重新加载导致内容空白；改为 `watch(visible + planId)` 打开时刷新
- **非渗透计划工单ID未生成**（`backend/app/schemas.py` / `backend/app/api/v1/special.py` / `frontend/src/views/NonpenPlanList.vue` / `frontend/src/views/TestingPlanList.vue`）：工单ID依赖「需求接收日期」或手动指定工单ID，两者皆空时系统静默保存导致工单ID缺失；新增前后端双重校验，未提供工单ID来源时拒绝保存并提示

### 数据库

- `testing_plans` 新增 `actual_mandays_override`（BOOLEAN）：SQLite 走 `_migrate_lightweight` 幂等加列，PostgreSQL 走 Alembic 迁移 `b5c6d7e8f9a0`
- 新增 `nonpen_plans` 表（`ticket_seq` / `ticket_id_manual` / `asset_ids` / `items` JSON / `testing_plan_id` 联动外键）；`testing_plans` 新增 `create_nonpen`（BOOLEAN）：SQLite 走 `_migrate_lightweight` 幂等建表加列，PostgreSQL 走 Alembic 迁移 `c9d0e1f2a3b4`

---

## [1.1.0] - 2026-08-13

工单体系命名统一与复测轮次一致性修复。菜单与业务文案统一为「工单」风格；复测报告与复测轮次建立关联，删除复测报告时自动回退对应轮次；漏扫基线工单列表排序口径优化；全站时间格式化统一；文档截图清理。

### 变更

- **模块命名统一**：菜单标题与业务文案统一为「工单」风格——渗透测试计划→渗透测试工单、非渗透计划→漏扫基线工单、漏洞管理→历史漏洞库、漏洞知识库→漏洞模板库；同步更新侧边栏菜单 / 路由页面标题 / 表单 / 按钮 / 提示语 / Excel 导出与导入模板（sheet 名、文件名、表头）及后端错误提示与 API 文档 tags。路由路径 `/testing-plans`、`/nonpen-plans`、`/vulns`、`/knowledge` 与 API、表名保持不变
- **漏扫基线工单列表排序口径**（`backend/app/api/v1/nonpen.py`）：列表默认排序由 `id desc` 改为「接收时间 desc → 工单序号 desc → id desc」，与渗透测试工单列表排序口径保持一致
- **全站统一时间格式化**（`frontend/src/utils/format.ts` 新增 + 多视图改用 `fmtDateTime`/`fmtDate`）：抽离统一时间展示工具，禁止各视图内散落的 `slice`/`replace` 自定义格式，消除时间格式不一致

### 修复

- **删除复测报告后复测轮数不回退**（`backend/app/api/v1/reports.py` / `backend/app/services/plan_service.py`）：发起复测生成复测报告时，本轮次 `start_retest_round` 记录关联 `report_id`；删除该复测报告时调用新增 `rollback_retest_round_by_report` 移除对应轮次（无进行中轮次时对称撤销最近一轮完成点），保证复测轮数与报告数据一致。报告导出同步新增 `version_dates`，按计划下各报告创建顺序对齐各版本导出日期

### 数据库

- `testing_plan_retest_rounds` 新增 `report_id`（INTEGER，可空）：SQLite 走 `_migrate_lightweight` 幂等加列，PostgreSQL 走 Alembic 迁移 `d1e2f3a4b5c6`

### 移除

- 清理 `docs/images/` 下 15 张过期 UI 截图（登录 / 仪表盘 / 漏洞列表 / 报告编辑 / 导入 / 资产 / 测试计划 / 用户角色 / 复测等），文档引用同步移除

---

## [Unreleased]

（暂无）

---

## [0.10.0] - 2026-08-07

报告列表显示生成时间、测试计划聚合筛选、报告导出历史管理与重复导出 / 重复生成检测、复测记录状态联动，以及对应数据库结构迁移。

### 新增

- **报告列表「生成时间」列**（`frontend/src/views/ReportList.vue` / `backend/app/api/v1/reports.py`）：报告列表新增可排序的「生成时间」列（`create_time`），流程抽屉报告项同步展示「生成于 …」，报告概要 schema 补充 `create_time` 字段
- **报告导出历史管理 + 重复导出检测**（`ReportList.vue` / `PlanWorkflowDrawer.vue` / `reports.py` / `report.py` / `worker/main.py`）：报告列表与流程抽屉改为一键展开查看导出历史版本，支持单条下载 / 预览 / 删除；导出任务记录报告内容指纹（`report_snapshot`：编辑版本 + 更新时间 + 关联漏洞编辑快照），导出前 `POST /reports/{id}/export-check` 检测同格式重复导出，前端弹窗确认「继续导出 / 取消」
- **报告生成高度相似性检查**（`reports.py` / `ReportList.vue`）：生成 / 保存报告时采集关联漏洞最后编辑时间快照（`reports.vul_edit_snapshot`），再次生成前 `POST /reports/similarity-check` 对比历史报告，高度相似时前端弹窗确认；存量报告首次对比时自动回填快照（幂等）
- **测试计划聚合筛选**（`frontend/src/components/FilterBuilder.vue` 新组件 / `TestingPlanList.vue` / `special.py`）：列表筛选升级为弹窗式聚合筛选构建器（多条件「且 / 或」连接、单条件「非」取反、文本 / 枚举 / 数值 / 日期区间操作符），后端 `filters` JSON 按字段白名单动态过滤；新增「显示待办流程」快捷筛选（未测试 / 初测中 / 复测中）
- **复测记录状态联动**（`vulns.py` / `VulnRetestPanel.vue` / `vuln_service.py`）：创建复测记录时可一并调整漏洞状态（复测未修复回修复中 / 已修复），状态流转统一校验复测结论完整性
- **工单序号复用**（`special.py`）：需求接收日期内分配最小未占用序号，删除 / 释放的工单 ID 可被后续记录重新使用

### 变更

- 测试计划列表筛选栏重排：原状态 / 类型 / 部门 / 日期范围下拉收敛进「筛选」弹窗，保留「当前可测试系统」「无人认领」并新增「待办流程」快捷勾选

### 数据库

- `reports` 新增 `vul_edit_snapshot`（JSON）、`export_jobs` 新增 `report_snapshot`（JSON）：SQLite 走 `_migrate_lightweight` 幂等加列，PostgreSQL 走 Alembic 迁移 `c3d4e5f6a7b8` / `d4e5f6a7b8c9`

---

## [0.9.2] - 2026-08-06

报告导出管线改造（回退 LibreOffice 目录自动更新、改用 Pillow 图片压缩）、全系统业务时间统一为 UTC+8 北京时区、测试计划认领与关联资产增强，以及多项部署 / 运维与文档优化。

以下为 `v0.9.1`（2026-07-31）之后至本版本的提交，按时间倒序排列。每个提交标注类型、具体改动、影响范围与关联模块，便于团队成员快速了解项目演进过程。

---

## [0.9.3] - 2026-08-07

报告编辑页章节导航支持鼠标拖拽排序，并修正拖拽 / 删除 / 移动后的导航高亮索引同步问题。

### 新增
- **报告编辑页章节导航拖拽排序**（`frontend/src/views/ReportEditor.vue`）：章节导航支持鼠标拖拽重排，含拖拽指示线、拖拽态样式（半透明 / 抓取光标）与落点高亮；同步修正 `removeSection` / `move` / 拖拽插入后的导航高亮索引，避免排序后高亮错位。

---

## [Unreleased]

（暂无）

> 说明：其中 `bd0d74d` / `bd5482c`（文本行尾规范化）、`02cad9b` / `8597ba8` / `ebbbb63`（repowiki 知识库本地化与文档同步）等提交以仓库规范与本地知识库同步为主，不产生运行时代码行为变化，已在各条目标注。

### 提交明细（2026-08-02 ~ 2026-08-06，时间倒序）

#### a5d7ab2 · 2026-08-06 · ♻️ refactor(report)
- **改动内容**: 回退报告导出目录（TOC）的 LibreOffice 服务端自动更新方案，改为前端提示用户手动更新域；新增报告图片压缩（Pillow）以解决高分辨率截图导致 docx 体积过大；前端目录提示提取为 `tocNotice.ts`（支持「不再显示」勾选，记 localStorage）；新增 Docker 腾讯云镜像加速脚本 `scripts/setup-docker-mirror.sh`。
- **影响范围**: 报告导出管线（worker 不再调用 soffice）、前端导出提示交互、部署镜像构建与 `.env` 配置项（新增 `REPORT_IMAGE_*`、移除 `ENABLE_LIBREOFFICE` 等）。
- **关联模块**: 报告导出（report_builder / worker）、前端（ReportEditor / ReportList / tocNotice）、部署（Dockerfile / docker-compose / .env / DEPLOY）、依赖（Pillow）。

#### e1caa0c · 2026-08-05 · 🔧 chore
- **改动内容**: 优化 `scripts/upgrade.sh` 升级前的备份触发条件；`.gitignore` 新增忽略调试临时文件（`_db.txt` / `_proc*.txt` / `_venv.txt` / `backend/_tz.txt` / `*.db.bak*`）。
- **影响范围**: 运维升级脚本、仓库忽略规则。
- **关联模块**: 部署 / 运维脚本。

#### 667f86b · 2026-08-05 · ✨ feat(frontend)
- **改动内容**: 测试计划流程抽屉支持计划认领 / 退出与漏洞库选择；报告编辑页正文与目录导航滚动分离、列表页主键由 ID 改为序号展示；多个列表 / 详情页（资产、用户组、导入、远程检测、春耕行动、测试计划、漏洞等）交互优化。
- **影响范围**: 测试计划认领与漏洞录入流程、报告编辑体验、多处列表展示。
- **关联模块**: 测试计划（前端 + `special.py` / `plan_service.py` 认领接口）、漏洞库、前端组件（PlanWorkflowDrawer / VulnFormPanel / AssetFormDialog）。

#### 564fefa · 2026-08-05 · ✨ feat(report)
- **改动内容**: 报告导出 docx 后由 worker 调用 LibreOffice 宏自动刷新 TOC 目录域（新增 `backend/app/services/libreoffice_toc.py`）；`ExportJob` 增加 `toc_auto_updated` 字段（含 Alembic 迁移）；`report_builder` 增加 pygments 代码高亮；Dockerfile 支持 `ENABLE_LIBREOFFICE` 按需安装 LibreOffice；补充 DEPLOY 章节。
- **影响范围**: 报告导出服务端新增 LibreOffice 依赖与目录自动刷新能力；前端导出后据 `toc_auto_updated` 决定是否提示手动更新。
- **关联模块**: 报告导出（report_builder / worker / Dockerfile）、前端（ReportList）、数据库迁移、部署文档。
- **注**: 该能力在后续 `a5d7ab2` 中已被回退，改为前端手动提示 + 图片压缩方案。

#### 1be784e · 2026-08-05 · 🕐 fix(timezone)
- **改动内容**: 全系统业务时间统一为 UTC+8 北京时区：`timeutil.now()` 基于 `settings.TIMEZONE` / Asia/Shanghai（依赖 zoneinfo + tzdata），`utcnow()` 仅用于 JWT 签发；全后端时间获取统一替换；新增 `migrate_utc_to_utc8.py` 历史数据迁移脚本。
- **影响范围**: 所有业务时间字段（创建 / 更新 / 提交 / 复测等）的展示与存储口径统一为北京时间；历史库需运行迁移脚本转换。
- **关联模块**: 时间工具（timeutil）、全部后端模型（business / dictionary / imports / knowledge / special / user 等）/ 接口（auth / dashboard / imports / vulns）、vuln_service、schemas、数据库迁移、部署（requirements / docker-compose / .env）。

#### bd0d74d · 2026-08-04 · chore
- **改动内容**: 在 `.gitattributes` 设置 `* text=auto` 并对仓库执行 renormalize，统一文本行尾（CRLF→LF）。
- **影响范围**: 101 个文件行尾规范化，无逻辑变更。
- **关联模块**: 仓库规范 / 版本控制。

#### 3fea32f · 2026-08-04 · fix(deploy)
- **改动内容**: nginx 改为动态解析 api 上游（避免容器 IP 变化导致 502）；`backup.sh` / `restore.sh` 增加幂等处理。
- **影响范围**: 生产反向代理稳定性、备份 / 恢复脚本健壮性。
- **关联模块**: 部署（frontend/nginx.conf、scripts/backup.sh、scripts/restore.sh）。

#### a44e30a · 2026-08-04 · feat(testing-plans)
- **改动内容**: 测试计划关联资产支持自动填充（按漏洞归属资产回写），列表筛选改为多条件并集。
- **影响范围**: 测试计划关联资产的准确性与筛选逻辑。
- **关联模块**: 测试计划（`special.py`）、前端（TestingPlanList）。

#### f7e6561 · 2026-08-04 · feat(report)
- **改动内容**: 报告生成 8 项优化：`reports.py` 接口与 `report_builder` 增强、worker 导出流程改进、`ReportList` 批量导出交互优化。
- **影响范围**: 报告构建与导出体验、批量下载。
- **关联模块**: 报告导出（reports.py / report_builder / worker）、前端（ReportList）。

#### 71f8a35 · 2026-08-04 · chore
- **改动内容**: 为 `backup.sh` / `migrate.sh` 补充 sudo 提权调用，适配非 root 执行。
- **影响范围**: 运维脚本执行权限兼容性。
- **关联模块**: 部署 / 运维脚本。

#### eb2b247 · 2026-08-04 · fix(worker)
- **改动内容**: 修复报告导出失败时事务未回滚，导致导出任务永久卡在 `running` 的问题（worker 增加异常回滚，compose / Dockerfile 资源限制微调）。
- **影响范围**: 异步导出任务的可靠性，避免任务堆积卡死。
- **关联模块**: 异步任务（worker/main.py）、部署（docker-compose / frontend/Dockerfile）。

#### 48155dd · 2026-08-04 · feat(testing-plans)
- **改动内容**: 测试计划新增「工单ID」字段并支持手动编辑与唯一校验；关联资产新增录入入口及自动填充；扩展 assets / imports / knowledge / misc / users / special 等接口与 schema，补充 `docker-compose` 端口与文档 / 截图。
- **影响范围**: 测试计划数据模型（新增工单ID）、关联资产录入、多个后端接口字段扩展。
- **关联模块**: 测试计划（special.py / models / schemas）、资产（assets.py）、用户（users.py）、知识库（knowledge.py）、导入（imports.py）、前端（TestingPlanList / GroupList / AssetFormDialog / VulnFormPanel 等）。

#### bd5482c · 2026-08-03 · chore
- **改动内容**: 升级脚本相关调整，含一次大范围文本行尾规范化（`upgrade.sh` 及约 100 文件 renormalize）。
- **影响范围**: 仓库行尾统一，无逻辑变更。
- **关联模块**: 仓库规范 / 运维脚本。

#### 02cad9b · 2026-08-03 · chore
- **改动内容**: 将 `.qoder` 目录（repowiki 知识库）加入 `.gitignore` 并停止跟踪，知识库仅保留本地。
- **影响范围**: 仓库移除约 153 个被跟踪的 repowiki 文件（约 3.8 万行删除），不改变运行时代码。
- **关联模块**: 仓库规范 / repowiki 知识库。

#### 8597ba8 · 2026-08-03 · chore
- **改动内容**: 开发环境端口调整（前端 27014 / 后端 27015），并同步 repowiki 文档（含大量知识库内容移除）。
- **影响范围**: 本地开发端口约定与文档；不含运行时代码逻辑变更。
- **关联模块**: 开发环境 / 部署 / repowiki。

#### bac5cb4 · 2026-08-02 · chore(build)
- **改动内容**: 加速镜像构建（基础镜像 / 层缓存优化），调整前端发布端口；补充知识库导入模板（vulnerabilities JSON 样例）。
- **影响范围**: Docker 构建速度与前端发布端口；新增知识库批量导入样例数据。
- **关联模块**: 构建（backend / frontend Dockerfile、docker-compose）、知识库。

#### ebbbb63 · 2026-08-02 · chore
- **改动内容**: 文档更新（`USER_GUIDE` 等）与后端修复，并同步 repowiki 知识库（约 127 文件变更，含文档与少量后端修正）。
- **影响范围**: 文档完善与后端小修复；repowiki 同步不纳入运行时代码。
- **关联模块**: 文档、后端。

---

## [0.9.1] - 2026-07-31

补充生产部署与运维工具链：一键升级 / 备份 / 恢复脚本、Alembic 结构迁移基线与部署手册。

### 新增

- 部署与运维手册 `docs/DEPLOY.md`：首次部署、SQLite 数据说明、版本升级、备份、更换 VPS 平滑迁移全流程
- 一键运维脚本 `scripts/backup.sh` / `scripts/restore.sh`（PostgreSQL 逻辑备份 + `storage` 卷打包，可跨机恢复）与 `scripts/migrate.sh`（在 api 容器内执行数据库结构迁移）
- 一键升级脚本 `scripts/upgrade.sh`：拉取代码 → 升级前备份 → 重建镜像 → 数据库结构迁移（先于 api 启动）→ 重启服务，支持 `--no-backup` / `--no-pull`
- 建立 Alembic 基线迁移（`backend/alembic/versions/`）与幂等迁移决策脚本 `backend/scripts/migrate.py`：自动纳管历史 `create_all` 库，支撑生产 PostgreSQL 已有表的字段级结构演进

---

## [0.9.0] - 2026-07-31

测试计划页集成测试全流程「统一流程抽屉」，从认领到复测完成可在单页一站式完成。

### 新增

- 测试计划列表操作列新增「流程」按钮，打开统一流程抽屉 `PlanWorkflowDrawer.vue`：顶部步骤条（认领 → 录入漏洞 → 生成报告 → 发起复测 → 复测处理 → 复测完成）按计划状态高亮；抽屉内完成认领 / 退出、录入漏洞、生成报告、发起复测、复测记录处理与漏洞状态流转、报告 Word/PDF 导出（提交后轮询任务并支持下载 / 预览），除报告章节深度编辑外全流程一站直达
- 抽取可复用组件 `VulnFormPanel.vue`（漏洞录入 / 编辑表单主体）与 `VulnRetestPanel.vue`（复测记录增删改面板），供独立页与流程抽屉共用
- 计划详情端点 `GET /testing-plans/{id}`（含测试人员 / 关联漏洞 / 关联报告 / 复测轮次），供抽屉打开与每次操作后局部刷新单条数据

### 变更

- `TestingPlanList.vue` 操作列精简为「流程 / 编辑 / 删除」，原「认领 / 退出、录入漏洞、生成报告」入口统一收敛进流程抽屉，消除重复入口
- `VulnEdit.vue` / `VulnRetest.vue` 改为薄壳，主体逻辑迁移至可复用组件，独立专项管理页功能与行为保持不变

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
