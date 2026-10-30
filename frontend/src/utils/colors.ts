// 字典展示唯一出口：名称/Radix 色族由后端 /meta 下发（applyDictMeta 注册，改后端 constants.py 一处即全端生效），
// 本文件不再持有任何字典镜像数据；纯展示逻辑（softStyle / 点标 / 统计卡色板 / 复测未通过派生态）保留于此。

import { reactive, ref } from 'vue'

type ColorFamily =
  | 'sage' | 'jade' | 'red' | 'orange' | 'amber' | 'sky' | 'blue'
  | 'ruby' | 'violet' | 'pink' | 'cyan' | 'teal' | 'grass'

// 未知字典值 / meta 尚未到达时的兜底语义色
const FALLBACK_COLOR = 'sage'

type NameDict = Record<string, string>

interface NonpenItemDef {
  key: string
  name: string
  desc: string
}

/* ============================================================
   后端 /meta 下发 Radix 语义色族；前端统一解析为 Radix UI Colors 的 CSS 变量。
   Radix 的浅色和暗色文件分别覆盖同一批变量，因此组件不需要再根据主题手工换色。
   ============================================================ */
export const isDarkTheme = ref(
  typeof document !== 'undefined' && document.documentElement.classList.contains('dark'),
)
if (typeof document !== 'undefined') {
  new MutationObserver(() => {
    isDarkTheme.value = document.documentElement.classList.contains('dark')
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
}

const FAMILY_NAMES = new Set<ColorFamily>([
  'sage', 'jade', 'red', 'orange', 'amber', 'sky', 'blue',
  'ruby', 'violet', 'pink', 'cyan', 'teal', 'grass',
])

function familyOf(color: string): ColorFamily {
  const value = color.trim()
  const cssVar = /--(sage|jade|red|orange|amber|sky|blue|ruby|violet|pink|cyan|teal|grass)-/.exec(value)?.[1]
  if (cssVar) return cssVar as ColorFamily
  if (FAMILY_NAMES.has(value as ColorFamily)) return value as ColorFamily
  return 'sage'
}

/** 将语义族名统一解析为 Radix 次级前景色变量。 */
export const tone = (color: string) => `var(--${familyOf(color)}-11)`

const solidTone = (color: string) => `var(--${familyOf(color)}-9)`
const softTone = (color: string) => `var(--${familyOf(color)}-a3)`

/** 图表、趋势条和色点使用 Radix 9 实心数据色；文字仍使用 11。 */
export const solidColor = (color: string) => solidTone(color)

/** /meta 响应中字典相关部分的契约（键与后端 misc.py /meta 一一对应） */
export interface DictMetaPayload {
  vul_level: NameDict
  vul_status: NameDict
  asset_status: NameDict
  url_tag: NameDict
  import_batch_status: NameDict
  import_record_status: NameDict
  export_job_status: NameDict
  // P1 批次新增字典（缺省时走空对象兜底，不改变既有行为）
  sla_state?: NameDict
  sla_day_basis?: NameDict
  message_type?: NameDict
  todo_type?: NameDict
  notify_delivery_status?: NameDict
  pat_scope?: NameDict
  report_template_type?: NameDict
  dashboard_view_scope?: NameDict
  data_scope?: NameDict
  import_outcome?: NameDict
  colors: {
    vul_level: NameDict
    vul_status: NameDict
    vul_type: NameDict
    testing_plan_status: NameDict
    asset_status: NameDict
    url_tag: NameDict
    nonpen_item: NameDict
    import_batch_status: NameDict
    import_record_status: NameDict
    export_job_status: NameDict
    sla_state?: NameDict
    notify_delivery_status?: NameDict
  }
  nonpen: {
    items: NonpenItemDef[]
    status: NameDict
    actions: Record<string, string[]>
    action_names: NameDict
  }
}

// /meta 注册表：reactive 保证 meta 到达后已渲染的标签自动重渲染
const dict = reactive({
  vulLevelNames: {} as NameDict,
  vulStatusNames: {} as NameDict,
  assetStatusNames: {} as NameDict,
  urlTagNames: {} as NameDict,
  importBatchStatusNames: {} as NameDict,
  importRecordStatusNames: {} as NameDict,
  exportJobStatusNames: {} as NameDict,
  colors: {
    vulLevel: {} as NameDict,
    vulStatus: {} as NameDict,
    vulType: {} as NameDict,
    testingPlanStatus: {} as NameDict,
    assetStatus: {} as NameDict,
    urlTag: {} as NameDict,
    nonpenItem: {} as NameDict,
    importBatchStatus: {} as NameDict,
    importRecordStatus: {} as NameDict,
    exportJobStatus: {} as NameDict,
    // P1 批次新增色族字典
    slaState: {} as NameDict,
    notifyDeliveryStatus: {} as NameDict,
  },
  nonpen: {
    items: [] as NonpenItemDef[],
    status: {} as NameDict,
    actions: {} as Record<string, string[]>,
    actionNames: {} as NameDict,
  },
  // P1 批次字典
  slaStateNames: {} as NameDict,
  slaDayBasisNames: {} as NameDict,
  messageTypeNames: {} as NameDict,
  todoTypeNames: {} as NameDict,
  notifyDeliveryStatusNames: {} as NameDict,
  patScopeNames: {} as NameDict,
  reportTemplateTypeNames: {} as NameDict,
  dashboardViewScopeNames: {} as NameDict,
  importOutcomeNames: {} as NameDict,
})

/** 把 /meta 响应注入注册表（auth store fetchMeta 调用，全站唯一入口）。
 *  每个字段都带空值兜底：后端漏发任何 key 时字典保持空对象，色族走 FALLBACK_COLOR 灰色，
 *  绝不注入 undefined（否则 dict.colors.xxx[s] 会 TypeError 导致整页渲染崩溃）。 */
export function applyDictMeta(meta: DictMetaPayload) {
  dict.vulLevelNames = meta.vul_level ?? {}
  dict.vulStatusNames = meta.vul_status ?? {}
  dict.assetStatusNames = meta.asset_status ?? {}
  dict.urlTagNames = meta.url_tag ?? {}
  dict.importBatchStatusNames = meta.import_batch_status ?? {}
  dict.importRecordStatusNames = meta.import_record_status ?? {}
  dict.exportJobStatusNames = meta.export_job_status ?? {}
  dict.colors.vulLevel = meta.colors.vul_level ?? {}
  dict.colors.vulStatus = meta.colors.vul_status ?? {}
  dict.colors.vulType = meta.colors.vul_type ?? {}
  dict.colors.testingPlanStatus = meta.colors.testing_plan_status ?? {}
  dict.colors.assetStatus = meta.colors.asset_status ?? {}
  dict.colors.urlTag = meta.colors.url_tag ?? {}
  dict.colors.nonpenItem = meta.colors.nonpen_item ?? {}
  dict.colors.importBatchStatus = meta.colors.import_batch_status ?? {}
  dict.colors.importRecordStatus = meta.colors.import_record_status ?? {}
  dict.colors.exportJobStatus = meta.colors.export_job_status ?? {}
  dict.nonpen.items = meta.nonpen.items ?? []
  dict.nonpen.status = meta.nonpen.status ?? {}
  dict.nonpen.actions = meta.nonpen.actions ?? {}
  dict.nonpen.actionNames = meta.nonpen.action_names ?? {}
  // P1 批次字典：后端未下发时保持空对象（调用方兜底原文）
  dict.slaStateNames = meta.sla_state ?? {}
  dict.slaDayBasisNames = meta.sla_day_basis ?? {}
  dict.messageTypeNames = meta.message_type ?? {}
  dict.todoTypeNames = meta.todo_type ?? {}
  dict.notifyDeliveryStatusNames = meta.notify_delivery_status ?? {}
  dict.patScopeNames = meta.pat_scope ?? {}
  dict.reportTemplateTypeNames = meta.report_template_type ?? {}
  dict.dashboardViewScopeNames = meta.dashboard_view_scope ?? {}
  dict.importOutcomeNames = meta.import_outcome ?? {}
  dict.colors.slaState = meta.colors.sla_state ?? {}
  dict.colors.notifyDeliveryStatus = meta.colors.notify_delivery_status ?? {}
}

/* ============================================================
   等级 / 状态色族与标签（表格行内用 dotStyle + .dot-tag；筛选/详情用 softStyle + .tl-tag）
   ============================================================ */

export const levelColor = (lv: number) => tone(dict.colors.vulLevel[lv] ?? FALLBACK_COLOR)
export const statusColor = (s: number) => tone(dict.colors.vulStatus[s] ?? FALLBACK_COLOR)

// 复测未通过为展示层状态：修复中(50) 且经历过复测(is_retest)，不新增状态码
export const RETEST_FAILED_COLOR = 'var(--ruby-11)'
export const isRetestFailed = (status: number, isRetest?: boolean) => status === 50 && !!isRetest
export const statusLabel = (status: number, isRetest: boolean | undefined, map?: Record<number, string>) =>
  isRetestFailed(status, isRetest) ? '复测未通过' : ((map ?? dict.vulStatusNames)[status] ?? String(status))

// 点标样式：配合 .dot-tag 类（色点颜色走 --c 变量）
export const dotStyle = (color: string) => ({ '--c': solidTone(color) } as Record<string, string>)
export const levelDotStyle = (lv: number) => dotStyle(levelColor(lv))
export const statusDotStyle = (status: number, isRetest?: boolean) =>
  dotStyle(isRetestFailed(status, isRetest) ? RETEST_FAILED_COLOR : statusColor(status))

// 柔和标签样式：Radix Alpha 背景 + 11 级文字，保证明暗模式语义一致
export const softStyle = (color: string) => {
  return { background: softTone(color), color: tone(color) }
}
export const levelSoftStyle = (lv: number) => softStyle(levelColor(lv))
export const statusSoftStyle = (s: number) => softStyle(statusColor(s))

// 统计徽章双模式：数量>0 实心底色，数量=0 柔和底色
export const levelBadgeStyle = (lv: number, count: number) =>
  count > 0
    ? { background: solidTone(levelColor(lv)), color: 'var(--tl-on-primary)' }
    : softStyle(levelColor(lv))
export const statusSoftStyleWithRetest = (status: number, isRetest?: boolean) =>
  softStyle(isRetestFailed(status, isRetest) ? RETEST_FAILED_COLOR : statusColor(status))

/* ============================================================
   名称查询
   ============================================================ */

export const levelName = (lv: number) => dict.vulLevelNames[lv] ?? String(lv)
export const statusName = (s: number) => dict.vulStatusNames[s] ?? String(s)

// Dashboard 等按中文名反查色族：先由名称定位字典码，再取对应语义色族
const colorByName = (names: NameDict, colors: NameDict, name: string) => {
  const code = Object.keys(names).find(k => names[k] === name)
  return tone((code !== undefined ? colors[code] : undefined) ?? FALLBACK_COLOR)
}
export const levelColorByName = (name: string) => colorByName(dict.vulLevelNames, dict.colors.vulLevel, name)
export const statusColorByName = (name: string) => colorByName(dict.vulStatusNames, dict.colors.vulStatus, name)

/* ============================================================
   计划 / 导出任务 / 导入批次状态标签
   ============================================================ */

export const planStatusColor = (s: number) => tone(dict.colors.testingPlanStatus[s] ?? FALLBACK_COLOR)
export const planStatusSoftStyle = (s: number) =>
  softStyle(dict.colors.testingPlanStatus[s] ?? FALLBACK_COLOR)
export const planStatusDotStyle = (s: number) => dotStyle(planStatusColor(s))

export const exportJobName = (s: string) => dict.exportJobStatusNames[s] ?? s
export const exportJobColor = (s: string) => tone(dict.colors.exportJobStatus[s] ?? FALLBACK_COLOR)
export const exportJobSoftStyle = (s: string) => softStyle(exportJobColor(s))

export const importStatusMeta = (s: string) => ({
  label: dict.importBatchStatusNames[s] ?? s,
  color: tone(dict.colors.importBatchStatus[s] ?? FALLBACK_COLOR),
})

export const importRecordMeta = (s: string) => ({
  label: dict.importRecordStatusNames[s] ?? s,
  color: tone(dict.colors.importRecordStatus[s] ?? FALLBACK_COLOR),
})

/* ============================================================
   资产 / URL 标签 / 漏洞类型
   ============================================================ */

export const assetStatusMeta = (s: number) => ({
  label: dict.assetStatusNames[s] ?? String(s),
  color: tone(dict.colors.assetStatus[s] ?? FALLBACK_COLOR),
})

export const urlTagMeta = (s: number) => ({
  label: dict.urlTagNames[s] ?? String(s),
  color: tone(dict.colors.urlTag[s] ?? FALLBACK_COLOR),
})

// 未知类型码（含动态新增 code≥1000）自动落到灰色
export const vulTypeColor = (t: number | null | undefined) =>
  tone(dict.colors.vulType[Number(t) ?? 75] ?? FALLBACK_COLOR)
export const vulTypeSoftStyle = (t: number | null | undefined) => softStyle(vulTypeColor(t))

/* ============================================================
   漏扫基线工单（nonpen 命名空间：测试项 / 状态 / 操作）
   ============================================================ */

export const nonpenItems = () => dict.nonpen.items
export const nonpenItemMeta = (status: string) => ({
  label: dict.nonpen.status[status] ?? status,
  color: tone(dict.colors.nonpenItem[status] ?? FALLBACK_COLOR),
})
export const nonpenActions = (status: string) => dict.nonpen.actions[status] ?? []
export const nonpenActionLabel = (action: string) => dict.nonpen.actionNames[action] ?? action

/* ============================================================
   纯 UI 色板（非字典，属界面设计令牌；暗色经 tone() 自动降饱和）
   ============================================================ */

// 统计卡色板（渗透/漏扫基线工单统计卡片共用，语义化命名便于阅读）
export const STAT_CARD_COLORS = {
  blue: 'var(--sky-11)',
  green: 'var(--jade-11)',
  orange: 'var(--amber-11)',
  red: 'var(--red-11)',
  gray: 'var(--sage-11)',
} as const

/* ============================================================
   报告复测状态（派生展示语义，非字典：后端 plan_service.retest_state_of）
   ============================================================ */

// none 未发起复测 / ongoing 复测中 / done 复测完成
const RETEST_STATE_META: Record<string, { name: string; color: string }> = {
  none: { name: '未发起复测', color: STAT_CARD_COLORS.gray },
  ongoing: { name: '复测中', color: STAT_CARD_COLORS.orange },
  done: { name: '复测完成', color: STAT_CARD_COLORS.green },
}

export const retestStateName = (state?: string | null) =>
  RETEST_STATE_META[state ?? 'none']?.name ?? RETEST_STATE_META.none.name
export const retestStateSoftStyle = (state?: string | null) =>
  softStyle(RETEST_STATE_META[state ?? 'none']?.color ?? RETEST_STATE_META.none.color)

/* ============================================================
   P1 批次字典出口（SLA / 站内消息 / 通知投递 / 令牌 scope / 模板 / 看板视图 / 导入结果）
   ============================================================ */

export const slaStateMeta = (state?: string | null) => ({
  label: dict.slaStateNames[state ?? 'none'] ?? (state ?? 'none'),
  color: tone(dict.colors.slaState[state ?? 'none'] ?? FALLBACK_COLOR),
})
export const slaStateSoftStyle = (state?: string | null) => {
  const meta = slaStateMeta(state)
  return softStyle(meta.color)
}
export const slaDayBasisName = (basis?: string | null) =>
  dict.slaDayBasisNames[basis ?? 'natural'] ?? (basis ?? 'natural')

export const messageTypeName = (t: string) => dict.messageTypeNames[t] ?? t
export const todoTypeName = (t: string) => dict.todoTypeNames[t] ?? t

export const notifyDeliveryMeta = (s: string) => ({
  label: dict.notifyDeliveryStatusNames[s] ?? s,
  color: tone(dict.colors.notifyDeliveryStatus[s] ?? FALLBACK_COLOR),
})
export const notifyDeliverySoftStyle = (s: string) => softStyle(notifyDeliveryMeta(s).color)

export const patScopeName = (s?: string | null) => dict.patScopeNames[s ?? 'full'] ?? (s ?? 'full')
export const reportTemplateTypeName = (t?: string | null) =>
  dict.reportTemplateTypeNames[t ?? 'all'] ?? (t ?? 'all')
export const dashboardViewScopeName = (s?: string | null) =>
  dict.dashboardViewScopeNames[s ?? 'personal'] ?? (s ?? 'personal')
export const importOutcomeMeta = (s?: string | null) => ({
  label: s ? (dict.importOutcomeNames[s] ?? s) : '未入库',
  color: tone(
    s === 'created' ? STAT_CARD_COLORS.green
      : s === 'updated' ? STAT_CARD_COLORS.blue
        : s === 'merged' ? 'var(--violet-11)'
          : s === 'failed' ? STAT_CARD_COLORS.red
            : s === 'skipped' ? STAT_CARD_COLORS.gray
              : FALLBACK_COLOR,
  ),
})
export const patScopeOptions = () =>
  Object.keys(dict.patScopeNames).map(k => ({ value: k, label: dict.patScopeNames[k] }))
export const reportTemplateTypeOptions = () =>
  Object.keys(dict.reportTemplateTypeNames).map(k => ({ value: k, label: dict.reportTemplateTypeNames[k] }))
export const slaDayBasisOptions = () =>
  Object.keys(dict.slaDayBasisNames).map(k => ({ value: k, label: dict.slaDayBasisNames[k] }))
export const slaStateOptions = () =>
  Object.keys(dict.slaStateNames).map(k => ({ value: k, label: dict.slaStateNames[k] }))
export const messageTypeOptions = () =>
  Object.keys(dict.messageTypeNames).map(k => ({ value: k, label: dict.messageTypeNames[k] }))
export const notifyDeliveryStatusOptions = () =>
  Object.keys(dict.notifyDeliveryStatusNames).map(k => ({ value: k, label: dict.notifyDeliveryStatusNames[k] }))
