# 回退（返回上一级）UX 优化方案

> 状态：**已落地**（2026-09-22）。§五 列出的 9 个文件已按本方案改造完毕，`pnpm typecheck` /
> `pnpm test`（29 文件 176 用例）/ `pnpm run build` 三门禁全绿；下方描述保留为设计依据与验收口径。
> 范围：前端（`frontend/`），不涉及后端契约变更。
> 关联规范：`AGENTS.md` 前端编码规范、`.codebuddy/rules/MASTER.md` 视觉与交互真值来源。

## 一、问题现象（用户场景还原）

从提供的截图可还原出典型链路：

1. 「渗透测试工单」列表（`/testing-plans`）→ 点击某工单，打开「测试流程」抽屉；
2. 抽屉内某漏洞行点击「编辑」→ 整页跳转到 `/vulns/:id/edit`；
3. 编辑页顶栏面包屑仅显示 `Talos / 编辑漏洞`，**无来源页信息、不可点**；
4. 表单「取消」按钮固定跳 `/vulns`（历史漏洞库），**回不到原工单流程**；
5. 保存后固定跳漏洞详情 `/vulns/:id`，同样脱离工单上下文；
6. 用户只能依赖浏览器后退，但后退后抽屉已关闭、需重新找行、重新展开、重新滚动。

## 二、根因分析

### 2.1 返回路径丢失（核心痛点）

| 现象 | 代码定位 | 根因 |
|---|---|---|
| 编辑页取消固定回漏洞库 | `frontend/src/views/VulnEdit.vue` 模板 `#actions-right` | `router.push('/vulns')` 硬编码，无视进入来源 |
| 保存后固定跳详情 | 同上 `onSaved()` | `router.push('/vulns/${editId}')`，未携带来源 |
| 复测按钮无来源透传 | 同上 `#actions-left` | `router.push('/vulns/${editId}/retest')` 无 redirect 参数 |
| 抽屉「编辑」跳转不带来源 | `frontend/src/components/PlanWorkflowDrawer.vue` 漏洞行操作列 | `router.push('/vulns/${row.id}/edit')` 纯路径跳转 |
| 面包屑静态不可点 | `frontend/src/layouts/MainLayout.vue` 顶栏 | 仅渲染 `Talos / {route.meta.title}`，无父级链 |
| 报告编辑无返回入口 | `frontend/src/views/ReportEditor.vue` | 抽屉「编辑内容」→ `/reports/:id` 后，目标页无任何返回按钮 |

### 2.2 回退后状态丢失

- **抽屉状态不入 URL**：`TestingPlanList.vue` 的 `workflowVisible` / `workflowPlanId` 仅存于组件 `ref`，离开页面即销毁；回退后必须重新定位工单行、重开抽屉。
- **展开行与滚动丢失**：`PlanWorkflowDrawer.vue` 的漏洞表 `el-table` 展开行状态、抽屉内滚动位置均为内存态，重建后回到顶部、行收起。
- **列表页滚动不恢复**：`router/index.ts` 未配置 `scrollBehavior`，且页面滚动容器为 `el-main`（非 `window`），浏览器后退返回列表后停在顶部。

### 2.3 回退安全性缺失

- `frontend/src/views/VulnRetest.vue` 的「返回」按钮使用裸 `router.back()`：当用户直接粘贴 URL 进入（无站内历史）时，会退回浏览器上一站，**可能直接退出系统**。
- 现有 `ErrorPage.vue` 与 `Login.vue` 已有 `state.back` / `redirect` 查询参数的先例（`utils/errorPage.ts::normalizeRedirect` 已做站内路径归一化），但业务页未沿用该惯例。

### 2.4 过渡与反馈（现状评估）

- 路由切换已有 `fade-slide` 过渡（`MainLayout.vue` 的 `<transition>`），此项**不缺**，无需改动。

## 三、优化方案

### 设计原则

1. **分层兜底**：显式 `redirect` 查询参数 > 浏览器站内历史（`history.state.back`）> 安全默认页。任一层都只接受站内路径（复用 `normalizeRedirect`），保证「返回」永不退出站点。
2. **与现有惯例一致**：沿用 `Login.vue`/`ErrorPage.vue` 的 `redirect` 参数语义，不引入新机制。
3. **状态外化到 URL**：抽屉打开的工单、回退定位的漏洞以 `?plan=&vuln=` 查询参数承载，使回退后状态可恢复、链接可分享。
4. **零后端改动**：纯前端路由与交互层调整，不触碰 API 契约。
5. **遵守 `MASTER.md`**：所有新增交互元素沿用全局色值、圆角、间距、过渡时长变量。

### 3.1 来源感知返回基建（新增组合式函数）

**新增文件**：`frontend/src/composables/useNavBack.ts`

导出三个能力：

| 函数 | 职责 |
|---|---|
| `resolveBackPath(route)` | 解析返回目标：优先 `route.query.redirect`（经 `normalizeRedirect` 归一化），回落 `window.history.state.back`（vue-router 写入的站内上一条），过滤 `/login`、`/error` 等过渡页；均无则返回 `null` |
| `goBack(router, route, fallback)` | 有站内历史则 `router.back()`（保留前进栈）；有 redirect 参数则 `router.push(path)`；否则 `router.replace(fallback)` 兜底（再缺省回落 `/dashboard`） |
| `withRedirect(path, from)` | 构造带来源的跳转目标 `{ path, query: { redirect: from } }`，供跨页跳转携带来源 |

依赖：复用 `utils/errorPage.ts::normalizeRedirect`（已存在，做站内路径白名单校验）。

### 3.2 编辑 / 复测链路改造

**文件**：`frontend/src/views/VulnEdit.vue`

- 读取 `route.query.redirect`（归一化）作为 `redirectTarget`。
- 「取消」按钮：调用 `goBack(router, route, '/vulns')`——来源优先，无来源时安全回落漏洞库。
- 「保存」：`redirectTarget` 存在则 `router.replace(redirectTarget)`（用 `replace` 避免浏览器后退又退回已保存的表单页，形成死循环）；否则维持现状（编辑→详情、新建→详情或列表）。
- 「复测」按钮：`router.push(withRedirect('/vulns/${editId}/retest', route.fullPath))`，把来源透传给复测页。

**文件**：`frontend/src/views/VulnRetest.vue`

- 「返回」按钮：由裸 `router.back()` 改为 `goBack(router, route, '/vulns/${vulId}')`，直接粘贴 URL 进入时回落到漏洞详情而非退出站点。
- 「返回编辑」按钮：`router.push(withRedirect('/vulns/${vulId}/edit', route.fullPath))`，透传来源。

### 3.3 抽屉状态进 URL（状态恢复核心）

**文件**：`frontend/src/views/TestingPlanList.vue`

- 新增 `useRoute`；抽屉显隐与 `?plan=` 查询参数双向同步：
  - `openWorkflow(row)` 打开时 `router.replace({ query: { ...route.query, plan: row.id } })`；
  - 抽屉关闭时移除 `plan` 与 `vuln` 参数（`replace`，不污染历史栈）。
- `onMounted` 读取 `route.query.plan`：有效则自动重开抽屉（覆盖编辑页 redirect 回跳场景）。
- 新增 `focusVulnId` 计算属性（来自 `route.query.vuln`），作为 prop 传给 `PlanWorkflowDrawer`。

**文件**：`frontend/src/components/PlanWorkflowDrawer.vue`

- 新增可选 prop `focusVulnId?: number | null`。
- 漏洞表 `el-table` 增加 `:expand-row-keys="expandedVulnKeys"`；`watch([focusVulnId, vulns])` 在漏洞数据加载后展开对应行，`nextTick` 后 `scrollIntoView` 滚动到可见位置。
- 抽屉「编辑」按钮改为调用 `editVuln(row)`：`router.push(withRedirect('/vulns/${row.id}/edit', hostFullPath(row.id)))`，其中 `hostFullPath` 把当前页 fullPath（含 `plan` 状态位）+ `vuln=row.id` 写入 redirect。
- 抽屉「编辑内容」（报告）按钮同理携带来源 redirect（不带 `vuln`）。

### 3.4 面包屑来源链

**文件**：`frontend/src/layouts/MainLayout.vue`

- 顶栏在 `Talos /` 与当前标题之间插入可点的来源链：`‹ 来源页标题 /`。
- `crumbBack` 计算属性：调用 `resolveBackPath(route)` 取目标 path，经 `router.resolve(path).meta.title` 解析来源页标题；与当前标题相同或为过渡页时不渲染。
- 点击行为：`isHistoryBack` 为真则 `router.back()`（保留前进栈），否则 `router.push(path)`（redirect 来源回跳）。
- 视觉：沿用 `nav-item` 的 hover 语汇（`--tl-surface-2` 背景、`--tl-primary` 文字），12px 字号、6px 圆角、150ms 过渡，符合 `MASTER.md` 交互状态规范。

### 3.5 滚动位置记忆

**文件**：`frontend/src/layouts/MainLayout.vue`

- 给 `el-main` 加 `ref`；监听其 `scroll` 事件（`passive`、`requestAnimationFrame` 节流），按 `route.fullPath` 记录 `{ top, position }` 到模块级 `Map`（上限 120 条，LRU 淘汰）。
- `watch(route.fullPath)`：
  - 同页 query 变化（`route.path` 不变，如筛选、抽屉状态位）**不干预**滚动；
  - 返回式导航（判据：`history.state.position` 不高于离开时记录值）→ 恢复滚动，数据异步加载期间高度不足时以 `rAF` 重试至到位或 1200ms 超时；
  - 前进式导航 → 置顶。
- `onBeforeUnmount` 移除监听、取消未决 `rAF`。

### 3.6 ReportEditor 返回入口

**文件**：`frontend/src/views/ReportEditor.vue`

- 在「报告信息」卡片 header 左侧新增「返回」按钮（`ArrowLeft` 图标 + 文字），调用 `goBack(router, route, '/reports')`：从工单抽屉进入时回抽屉，常规进入时回报告中心。

## 四、边界情况处理

| 场景 | 处理 |
|---|---|
| 首级页面（如 `/dashboard`） | `resolveBackPath` 返回 `null`，面包屑维持原静态形态，不渲染来源链 |
| 直接粘贴 URL 进入编辑/复测页 | 无 redirect 且无站内历史 → `goBack` 走安全默认页，不退出站点 |
| 多级嵌套（edit → retest → edit） | 每页将自身 fullPath 作为 redirect 透传，面包屑显示即时来源标题，链路自洽 |
| 抽屉关闭 | `watch(workflowVisible)` 清除 `plan` 与 `vuln` 参数，避免残留 |
| 同页 query 变化（筛选、抽屉状态位） | 滚动恢复逻辑比较 `route.path` 跳过，不误重置滚动 |
| `history.state` 不可用（jsdom / 首次进入） | `resolveBackPath` 守卫 `typeof` 判空，回落 `null` |
| redirect 参数非法（`//host` 外跳） | `normalizeRedirect` 拒绝，回落浏览器历史或默认页 |
| 抽屉 `destroy-on-close` 重建 | `focusVulnId` 经 `watch` 在 `vulns` 加载后触发展开，时序可靠 |

## 五、影响范围与实施顺序

### 涉及文件

| 文件 | 改动类型 |
|---|---|
| `frontend/src/composables/useNavBack.ts` | 新增 |
| `frontend/src/composables/__tests__/useNavBack.spec.ts` | 新增（单测） |
| `frontend/src/views/VulnEdit.vue` | 修改 |
| `frontend/src/views/VulnRetest.vue` | 修改 |
| `frontend/src/components/PlanWorkflowDrawer.vue` | 修改 |
| `frontend/src/components/__tests__/PlanWorkflowDrawer.spec.ts` | 修改（补 `useRoute` mock） |
| `frontend/src/views/TestingPlanList.vue` | 修改 |
| `frontend/src/layouts/MainLayout.vue` | 修改 |
| `frontend/src/views/ReportEditor.vue` | 修改 |

### 实施顺序

1. `useNavBack.ts` + 单测（先建基建，可独立验证）。
2. `VulnEdit.vue` / `VulnRetest.vue`（编辑复测链路，依赖 1）。
3. `TestingPlanList.vue` + `PlanWorkflowDrawer.vue`（抽屉状态进 URL，依赖 1）。
4. `MainLayout.vue`（面包屑 + 滚动记忆，依赖 1）。
5. `ReportEditor.vue`（返回入口，依赖 1）。
6. `PlanWorkflowDrawer.spec.ts` 补 mock。

### 提交前门禁（`AGENTS.md`）

- `pnpm typecheck`（`vue-tsc --noEmit`）全绿；
- `pnpm test`（vitest）全绿——含新增 `useNavBack.spec.ts` 与更新后的 `PlanWorkflowDrawer.spec.ts`；
- `pnpm run build` 全绿。

## 六、验收口径

### 功能

- 从工单抽屉「编辑」进入编辑页，取消与保存均原路返回抽屉，抽屉自动重开、漏洞行自动展开并滚动到位。
- 从历史漏洞库「编辑」进入编辑页，取消回漏洞库、保存跳详情（维持现状，不回归）。
- 复测页「返回」与「返回编辑」均安全回退，直接粘贴 URL 进入不退出站点。
- 报告编辑页「返回」回抽屉或报告中心。
- 面包屑来源链可点击回跳。

### 状态恢复

- 浏览器后退返回列表时滚动位置恢复；前进置顶；同页 query 变化不重置滚动。
- 抽屉经 URL 参数恢复，刷新或分享链接均可重开。

### 边界

- 首级页面无来源链；非法 redirect 不外跳；多级嵌套链路自洽。

### 视觉

- 来源链按钮、返回按钮符合 `MASTER.md` 色值/圆角/过渡规范，明暗模式可读，对比度 ≥ 4.5:1。

### 回归

- 既有 `PlanWorkflowDrawer` 单测（认领、生成报告、复测状态标注）不回归；新增 `useNavBack` 单测覆盖四层兜底与非法输入。

## 七、风险与回滚

| 风险 | 缓解 |
|---|---|
| `history.state.back` 在不同 vue-router 版本/SSR 下语义差异 | `resolveBackPath` 对 `typeof` 与字符串形态做守卫，失败回落 `null` |
| 滚动恢复在数据慢加载时定位不准 | `rAF` 重试 + 1200ms 超时，仅作用于返回式导航，前进置顶不受影响 |
| 抽屉 `replace` 同址导航触发 vue-router 重复导航告警 | `.catch(() => {})` 吞掉 `NavigationDuplicated` |
| 改动文件较多 | 按实施顺序分步提交，每步过门禁；基建（`useNavBack`）可先行独立合入 |

回滚方式：改动集中于前端 9 个文件，且不触碰后端与数据库迁移；如需回滚，按文件反向还原即可，无数据面影响。
