# Talos 演进路线（ROADMAP）

本文件是功能与重构规划的唯一入库真相源。维护原则：

- 每项含**验收标准**，完成即在 `docs/RELEASE.md` 记录版本并从本文件移入「已完成归档」；
- 排期按「近期（重构还债）→ 中期（功能演进）→ 远期（方向）」三档，不承诺具体日期，按迭代节奏推进；
- 新增条目必须评估对现有口径（漏洞来源、统计口径、工单状态机）的影响，破坏性变更升主版本号。

**现状基线**：2.1.0（2026-08-22）——重构还债（R1-R6）已完成：special 路由与 schemas 按域拆分、导入确认服务化、前后端字典单源（名称/色值/nonpen 随 /meta 下发，前端无镜像）、全站表单 el-form rules 校验、前端测试 45 例。

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
| R1 拆分 special.py | 2.1.0 完成：remote_testing / testing_plan / spring_action 三路由 + core/filters 通用筛选引擎 + services/plan_query / plan_io，单文件 ≤ 600 行，路径与权限零变化 |
| R2 拆分 schemas.py | 2.1.0 完成：schemas/ 包 8 个域文件经 `__init__.py` 重导出，调用方零改动 |
| R3 拆解 confirm_batch | 2.1.0 完成：路由约 65 行 + services/import_service（解析校验/报告编排/知识库回填/去重合并/收尾）+ services/report_html |
| R4 前端测试覆盖 | 2.1.0 完成：9 例 → 45 例（format/colors/useAssetSelect/useDictOptions/useCrudDialog/useExportJobs 单测 + VulnList/ReportEditor 冒烟） |
| R5 表单校验体系 | 2.1.0 完成：三类主表单 + 7 处轻量表单全部迁移 el-form rules，跨字段规则用自定义 validator，无 warning 弹窗式校验残留 |
| R6 字典单源化 | 2.1.0 完成：/meta 下发 colors 命名空间 + nonpen 命名空间 + 导入/导出/报告状态字典，前端 colors.ts 改 meta 注册表，constants/nonpen.ts 已删除 |
| 漏洞知识库 | 已实现（`models/knowledge.py`、`api/v1/knowledge.py`、KnowledgeList 视图、漏洞表单一键套用模板） |
| 报告导出（docx/PDF）与版本历史 | 已实现（导出任务队列 + 重复导出检测 + TOC 域提示） |
| 结构治理（composables / 令牌化暗黑 / 公共函数单源） | 2.0.1 后完成，见 RELEASE.md 对应版本段 |
