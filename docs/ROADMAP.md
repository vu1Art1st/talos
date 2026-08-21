# Talos 演进路线（ROADMAP）

本文件是功能与重构规划的唯一入库真相源。维护原则：

- 每项含**验收标准**，完成即在 `docs/RELEASE.md` 记录版本并从本文件移入「已完成归档」；
- 排期按「近期（重构还债）→ 中期（功能演进）→ 远期（方向）」三档，不承诺具体日期，按迭代节奏推进；
- 新增条目必须评估对现有口径（漏洞来源、统计口径、工单状态机）的影响，破坏性变更升主版本号。

**现状基线**：2.0.1（2026-08-19）——前后端结构治理已完成一轮：前端列表/CRUD/资产选择/导出任务已收敛为 composables，暗黑模式全站令牌化，后端公共函数（xlsx/人天/查询解析/富文本消毒）已单源化。

---

## 近期：v2.1.x —— 重构还债（稳定性与可维护性优先）

### R1 拆分 `backend/app/api/v1/special.py`（1345 行）

按业务域拆为 `remote_testing.py` / `spring_action.py` / `testing_plan.py` 三个路由模块，通用筛选引擎留 `special.py` 或入 core。
**验收**：单文件 ≤ 600 行；路由路径与权限点零变化；`pytest` 全绿。

### R2 拆分 `backend/app/schemas.py`（约 790 行）

按域拆为 `schemas/` 包（vuln / report / import_ / special / knowledge / common），对外经 `schemas/__init__.py` 重导出，调用方零改动。
**验收**：`from app.schemas import ...` 全部引用不变；`pytest` 全绿。

### R3 拆解 `imports.py::confirm_batch`（约 260 行单函数）

按「解析校验 → 去重合并 → 建漏洞/关联报告 → 复测轮次」拆为服务层函数（`services/import_service.py`），路由层只做参数编排。
**验收**：单函数 ≤ 80 行；导入相关测试覆盖等价。

### R4 前端测试覆盖扩展

以 `src/composables/` 与 `src/utils/` 为锚点，覆盖 useAssetSelect / useExportJobs / useCrudDialog / colors / format；关键视图（VulnList、ReportEditor）引入 `@vue/test-utils` 做冒烟测试。
**验收**：`pnpm test` 用例数 ≥ 30，核心纯逻辑分支覆盖。

### R5 表单校验体系（el-form rules）

当前全站表单为「手动 if + ElMessage.warning」浅校验。统一切换 Element Plus `rules` 校验（必填/格式/长度），错误提示内联到字段。
**验收**：资产/漏洞/工单三类主表单完成迁移；提交前无 warning 弹窗式校验残留。

### R6 前后端字典单源化

`constants/nonpen.ts` 等前端镜像与 `/meta` 下发的名称/颜色双源问题：`/meta` 接口扩展下发颜色与展示名，前端删除镜像文件，状态标签完全由 meta 驱动。
**验收**：改后端字典一处即全端生效；前端无字典镜像文件。

---

## 中期：v2.2+ —— 功能演进（按用户价值排序）

### F1 SLA 修复时限

按漏洞等级配置修复时限（如高危 7 天），超期漏洞在列表/仪表盘高亮并统计超期率。
**依赖**：R6（等级字典单源）先行。

### F2 扫描器报告接入

在现有 Word 导入链路（docx_parser）基础上扩展 AWVS/Nessus 等扫描器 HTML/XML 报告解析，复用导入预览与去重合并。
**依赖**：R3（导入服务化）先行。

### F3 通知渠道扩展

漏洞指派、工单流转、复测完成等事件通知（企业微信/钉钉 webhooks 优先，邮件次之），后台可配置。
**依赖**：F7（审计事件）复用事件总线。

### F4 CVSS 3.1 计算器

漏洞表单内嵌向量字符串计算器，评分写入 `score` 字段；知识库条目支持关联 CVSS 向量。

### F5 定期报表订阅

按周/月自动生成管理侧汇总报告（PDF），邮件推送订阅者；复用 Gotenberg 与导出任务队列。

### F6 开放 API（PAT）

个人访问令牌 + 只读 API（漏洞查询/统计），供内部看板与脚本集成；限流复用 `core/ratelimit.py`。

### F7 登录与操作审计

登录日志（IP/UA/成败）与敏感操作审计查询页；现有 `OperationLog` 模型扩展。

---

## 远期：方向探索（不排期）

- 多租户 / 部门级数据隔离；
- 漏洞自动验证（PoC 复验）插件化接入；
- 与资产测绘工具联动的新资产生命周期；
- 移动端适配（当前仅响应式降级）。

---

## 已完成归档（自旧版 ROADMAP 移入）

| 条目 | 完成情况 |
| --- | --- |
| 漏洞知识库 | 已实现（`models/knowledge.py`、`api/v1/knowledge.py`、KnowledgeList 视图、漏洞表单一键套用模板） |
| 报告导出（docx/PDF）与版本历史 | 已实现（导出任务队列 + 重复导出检测 + TOC 域提示） |
| 结构治理（composables / 令牌化暗黑 / 公共函数单源） | 2.0.1 后完成，见 RELEASE.md 对应版本段 |
