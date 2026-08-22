# Talos 演进路线（ROADMAP）

本文件是功能与重构规划的唯一入库真相源。维护原则：

- 每项含**验收标准**，完成即在 `docs/RELEASE.md` 记录版本并从本文件移入「已完成归档」；
- 排期按「近期（重构还债）→ 中期（功能演进）→ 远期（方向）」三档，不承诺具体日期，按迭代节奏推进；
- 新增条目必须评估对现有口径（漏洞来源、统计口径、工单状态机）的影响，破坏性变更升主版本号。

**现状基线**：2.2.0（2026-08-22）——中期功能 F3 通知渠道 / F4 CVSS 计算器 / F6 开放 API / F7 审计已落地，会话令牌改为空闲 24 小时滑动过期；F2 扫描器报告接入与 F5 定期报表订阅已取消（暂无计划）。

---

## 中期：v2.3+ —— 功能演进（按用户价值排序）

### F1 SLA 修复时限

按漏洞等级配置修复时限（如高危 7 天），超期漏洞在列表/仪表盘高亮并统计超期率。
**依赖**：R6（等级字典单源）已满足（2.1.0 完成）。

---

## 远期：方向探索（不排期）

- 多租户 / 部门级数据隔离；
- 漏洞自动验证（PoC 复验）插件化接入；
- 与资产测绘工具联动的新资产生命周期；
- 移动端适配（当前仅响应式降级）。

---

## 已取消（暂无计划）

| 条目 | 说明 |
| --- | --- |
| F2 扫描器报告接入 | AWVS/Nessus 等 HTML/XML 解析接入导入链路；暂无计划，如需重启按「依赖 R3（已完成）」评估 |
| F5 定期报表订阅 | 按周/月自动生成汇总报告（PDF）邮件推送；暂无计划，重启时可复用 Gotenberg 与导出任务队列 |

---

## 已完成归档（自旧版 ROADMAP 移入）

| 条目 | 完成情况 |
| --- | --- |
| F3 通知渠道扩展 | 2.2.0 完成：notification_channels 后台可配置（企业微信/钉钉 webhook + 邮件），四类事件（漏洞创建/工单认领/状态流转/复测完成）触发点分发 `send_notify_task`，前端「系统管理 → 通知渠道」 |
| F4 CVSS 3.1 计算器 | 2.2.0 完成：表单内嵌 `CvssCalculator`（8 指标实时评分 + 按评分同步等级），score 迁移 Float、漏洞与知识库新增 `cvss_vector`，套用模板双向带出 |
| F6 开放 API（PAT） | 2.2.0 完成：`tlp_` 个人访问令牌（sha256 入库、明文仅一次、7-365 天档位），`/open/vulns` 与 `/open/stats` 只读接口，每令牌限流复用 ratelimit |
| F7 登录与操作审计 | 2.2.0 完成：`operation_logs` 统一记录登录成败（IP/UA）与敏感操作，`GET /audit/logs` 查询端点 + 前端「审计日志」双 tab 页 |
| 会话令牌空闲滑动过期 | 2.2.0 完成：refresh token 24 小时空闲窗口（`VP_REFRESH_TOKEN_EXPIRE_HOURS`），轮换即重置计时，前端临期主动静默续期；PAT 不受限 |
| R1 拆分 special.py | 2.1.0 完成：remote_testing / testing_plan / spring_action 三路由 + core/filters 通用筛选引擎 + services/plan_query / plan_io，单文件 ≤ 600 行，路径与权限零变化 |
| R2 拆分 schemas.py | 2.1.0 完成：schemas/ 包 8 个域文件经 `__init__.py` 重导出，调用方零改动 |
| R3 拆解 confirm_batch | 2.1.0 完成：路由约 65 行 + services/import_service（解析校验/报告编排/知识库回填/去重合并/收尾）+ services/report_html |
| R4 前端测试覆盖 | 2.1.0 完成：9 例 → 45 例（format/colors/useAssetSelect/useDictOptions/useCrudDialog/useExportJobs 单测 + VulnList/ReportEditor 冒烟） |
| R5 表单校验体系 | 2.1.0 完成：三类主表单 + 7 处轻量表单全部迁移 el-form rules，跨字段规则用自定义 validator，无 warning 弹窗式校验残留 |
| R6 字典单源化 | 2.1.0 完成：/meta 下发 colors 命名空间 + nonpen 命名空间 + 导入/导出/报告状态字典，前端 colors.ts 改 meta 注册表，constants/nonpen.ts 已删除 |
| 漏洞知识库 | 已实现（`models/knowledge.py`、`api/v1/knowledge.py`、KnowledgeList 视图、漏洞表单一键套用模板） |
| 报告导出（docx/PDF）与版本历史 | 已实现（导出任务队列 + 重复导出检测 + TOC 域提示） |
| 结构治理（composables / 令牌化暗黑 / 公共函数单源） | 2.0.1 后完成，见 RELEASE.md 对应版本段 |
