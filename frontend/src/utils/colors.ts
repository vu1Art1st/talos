// 字典展示唯一出口：名称/色值全部由后端 /meta 下发（applyDictMeta 注册，改后端 constants.py 一处即全端生效），
// 本文件不再持有任何字典镜像数据；纯展示逻辑（softStyle / 点标 / 统计卡色板 / 复测未通过派生态）保留于此。

import { reactive, ref } from 'vue'

// 未知字典值 / meta 尚未到达时的兜底色
const FALLBACK_COLOR = '#8A968F'

type NameDict = Record<string, string>

interface NonpenItemDef {
  key: string
  name: string
  desc: string
}

/* ============================================================
   明暗 tone 映射层：后端 /meta 下发浅色版语义色（导出文档同为浅色口径），
   html.dark 时前端映射为 demo-2 降饱和暗色变体；未收录的色值走通用提亮算法。
   isDarkTheme 通过观察 html.class 变化保持响应式，主题切换后已渲染标签自动重渲染。
   ============================================================ */
export const isDarkTheme = ref(
  typeof document !== 'undefined' && document.documentElement.classList.contains('dark'),
)
if (typeof document !== 'undefined') {
  new MutationObserver(() => {
    isDarkTheme.value = document.documentElement.classList.contains('dark')
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
}

// 关键语义色的暗色变体（key 为 /meta 下发的浅色 hex，大写）
const DARK_TONE: Record<string, string> = {
  '#DC2626': '#f87171', '#EA580C': '#fb923c', '#D97706': '#fbbf24',
  '#0284C7': '#7dd3fc', '#059669': '#34d399', '#E11D48': '#fb7185',
  '#8A968F': '#6b7f78', '#A6B1AB': '#54645e',
  '#F59E0B': '#fbbf24', '#0EA5E9': '#7dd3fc', '#DB2777': '#f472b6', '#9333EA': '#c084fc',
}

// 未收录色值的通用暗色处理：向白色混合提亮
const lighten = (hex: string, amt = 0.35) => {
  const m = hex.replace('#', '')
  if (m.length !== 6) return hex
  const n = parseInt(m, 16)
  const mix = (c: number) => Math.round(c + (255 - c) * amt)
  const rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(mix)
  return `#${((rgb[0] << 16) | (rgb[1] << 8) | rgb[2]).toString(16).padStart(6, '0')}`
}

/** 主题感知色值解析：暗色下映射降饱和变体，其余原样返回（幂等） */
export const tone = (hex: string) =>
  isDarkTheme.value ? (DARK_TONE[hex.toUpperCase()] ?? lighten(hex)) : hex

/** /meta 响应中字典相关部分的契约（键与后端 misc.py /meta 一一对应） */
export interface DictMetaPayload {
  vul_level: NameDict
  vul_status: NameDict
  asset_status: NameDict
  url_tag: NameDict
  report_status: NameDict
  import_batch_status: NameDict
  import_record_status: NameDict
  export_job_status: NameDict
  colors: {
    vul_level: NameDict
    vul_status: NameDict
    vul_type: NameDict
    testing_plan_status: NameDict
    report_status: NameDict
    asset_status: NameDict
    url_tag: NameDict
    nonpen_item: NameDict
    import_batch_status: NameDict
    import_record_status: NameDict
    export_job_status: NameDict
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
  reportStatusNames: {} as NameDict,
  importBatchStatusNames: {} as NameDict,
  importRecordStatusNames: {} as NameDict,
  exportJobStatusNames: {} as NameDict,
  colors: {
    vulLevel: {} as NameDict,
    vulStatus: {} as NameDict,
    vulType: {} as NameDict,
    testingPlanStatus: {} as NameDict,
    reportStatus: {} as NameDict,
    assetStatus: {} as NameDict,
    urlTag: {} as NameDict,
    nonpenItem: {} as NameDict,
    importBatchStatus: {} as NameDict,
    importRecordStatus: {} as NameDict,
    exportJobStatus: {} as NameDict,
  },
  nonpen: {
    items: [] as NonpenItemDef[],
    status: {} as NameDict,
    actions: {} as Record<string, string[]>,
    actionNames: {} as NameDict,
  },
})

/** 把 /meta 响应注入注册表（auth store fetchMeta 调用，全站唯一入口）。
 *  每个字段都带空值兜底：后端漏发任何 key 时字典保持空对象，色值走 FALLBACK_COLOR 灰色，
 *  绝不注入 undefined（否则 dict.colors.xxx[s] 会 TypeError 导致整页渲染崩溃）。 */
export function applyDictMeta(meta: DictMetaPayload) {
  dict.vulLevelNames = meta.vul_level ?? {}
  dict.vulStatusNames = meta.vul_status ?? {}
  dict.assetStatusNames = meta.asset_status ?? {}
  dict.urlTagNames = meta.url_tag ?? {}
  dict.reportStatusNames = meta.report_status ?? {}
  dict.importBatchStatusNames = meta.import_batch_status ?? {}
  dict.importRecordStatusNames = meta.import_record_status ?? {}
  dict.exportJobStatusNames = meta.export_job_status ?? {}
  dict.colors.vulLevel = meta.colors.vul_level ?? {}
  dict.colors.vulStatus = meta.colors.vul_status ?? {}
  dict.colors.vulType = meta.colors.vul_type ?? {}
  dict.colors.testingPlanStatus = meta.colors.testing_plan_status ?? {}
  dict.colors.reportStatus = meta.colors.report_status ?? {}
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
}

/* ============================================================
   等级 / 状态色值与标签（表格行内用 dotStyle + .dot-tag；筛选/详情用 softStyle + .tl-tag）
   ============================================================ */

export const levelColor = (lv: number) => tone(dict.colors.vulLevel[lv] ?? FALLBACK_COLOR)
export const statusColor = (s: number) => tone(dict.colors.vulStatus[s] ?? FALLBACK_COLOR)

// 复测未通过为展示层状态：修复中(50) 且经历过复测(is_retest)，不新增状态码
export const RETEST_FAILED_COLOR = '#E11D48'
export const isRetestFailed = (status: number, isRetest?: boolean) => status === 50 && !!isRetest
export const statusLabel = (status: number, isRetest: boolean | undefined, map?: Record<number, string>) =>
  isRetestFailed(status, isRetest) ? '复测未通过' : ((map ?? dict.vulStatusNames)[status] ?? String(status))

// 点标样式：配合 .dot-tag 类（色点颜色走 --c 变量，暗色辉光由 CSS 控制）
export const dotStyle = (color: string) => ({ '--c': tone(color) } as Record<string, string>)
export const levelDotStyle = (lv: number) => dotStyle(levelColor(lv))
export const statusDotStyle = (status: number, isRetest?: boolean) =>
  dotStyle(isRetestFailed(status, isRetest) ? RETEST_FAILED_COLOR : statusColor(status))

// 柔和标签样式：半透明底 + 同色文字（替代实心 effect="dark"）
// 返回可直接绑定到 :style 的对象，配合 .tl-tag 类使用；色值经 tone() 主题感知
export const softStyle = (color: string) => {
  const c = tone(color)
  return { background: c + '1f', color: c }
}
export const levelSoftStyle = (lv: number) => softStyle(levelColor(lv))
export const statusSoftStyle = (s: number) => softStyle(statusColor(s))

// 统计徽章双模式：数量>0 深背景白字（醒目），数量=0 浅背景深字（弱化）
export const levelBadgeStyle = (lv: number, count: number) =>
  count > 0 ? { background: levelColor(lv), color: '#fff' } : softStyle(levelColor(lv))
export const statusSoftStyleEx = (status: number, isRetest?: boolean) =>
  softStyle(isRetestFailed(status, isRetest) ? RETEST_FAILED_COLOR : statusColor(status))

/* ============================================================
   名称查询
   ============================================================ */

export const levelName = (lv: number) => dict.vulLevelNames[lv] ?? String(lv)
export const statusName = (s: number) => dict.vulStatusNames[s] ?? String(s)

// Dashboard 等按中文名反查色值：先由名称定位字典码，再取对应色值
const colorByName = (names: NameDict, colors: NameDict, name: string) => {
  const code = Object.keys(names).find(k => names[k] === name)
  return tone((code !== undefined ? colors[code] : undefined) ?? FALLBACK_COLOR)
}
export const levelColorByName = (name: string) => colorByName(dict.vulLevelNames, dict.colors.vulLevel, name)
export const statusColorByName = (name: string) => colorByName(dict.vulStatusNames, dict.colors.vulStatus, name)

/* ============================================================
   计划 / 报告 / 导出任务 / 导入批次状态标签
   ============================================================ */

export const planStatusColor = (s: number) => tone(dict.colors.testingPlanStatus[s] ?? FALLBACK_COLOR)
export const planStatusSoftStyle = (s: number) =>
  softStyle(dict.colors.testingPlanStatus[s] ?? FALLBACK_COLOR)
export const planStatusDotStyle = (s: number) => dotStyle(planStatusColor(s))

export const reportStatusName = (s: string) => dict.reportStatusNames[s] ?? s
export const reportStatusSoftStyle = (s: string) =>
  softStyle(dict.colors.reportStatus[s] ?? FALLBACK_COLOR)
export const reportStatusColor = (s: string) => tone(dict.colors.reportStatus[s] ?? FALLBACK_COLOR)

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
  blue: '#0284C7',
  green: '#059669',
  orange: '#D97706',
  red: '#DC2626',
  gray: '#8A968F',
} as const
