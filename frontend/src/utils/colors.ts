// 字典展示唯一出口：名称/色值全部由后端 /meta 下发（applyDictMeta 注册，改后端 constants.py 一处即全端生效），
// 本文件不再持有任何字典镜像数据；纯展示逻辑（softStyle / 统计卡色板 / 复测未通过派生态）保留于此。

import { reactive } from 'vue'

// 未知字典值 / meta 尚未到达时的兜底色
const FALLBACK_COLOR = '#909399'

type NameDict = Record<string, string>

interface NonpenItemDef {
  key: string
  name: string
  desc: string
}

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
   等级 / 状态色值与柔和标签（配合 .tl-tag 类使用）
   ============================================================ */

export const levelColor = (lv: number) => dict.colors.vulLevel[lv] ?? FALLBACK_COLOR
export const statusColor = (s: number) => dict.colors.vulStatus[s] ?? FALLBACK_COLOR

// 复测未通过为展示层状态：修复中(50) 且经历过复测(is_retest)，不新增状态码
export const RETEST_FAILED_COLOR = '#F56C6C'
export const isRetestFailed = (status: number, isRetest?: boolean) => status === 50 && !!isRetest
export const statusLabel = (status: number, isRetest: boolean | undefined, map?: Record<number, string>) =>
  isRetestFailed(status, isRetest) ? '复测未通过' : ((map ?? dict.vulStatusNames)[status] ?? String(status))

// 柔和标签样式：半透明底 + 同色文字（现代化标签风，替代实心 effect="dark"）
// 返回可直接绑定到 :style 的对象，配合 .tl-tag 类使用
export const softStyle = (color: string) => ({
  background: color + '1f',
  color,
})
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
  return (code !== undefined ? colors[code] : undefined) ?? FALLBACK_COLOR
}
export const levelColorByName = (name: string) => colorByName(dict.vulLevelNames, dict.colors.vulLevel, name)
export const statusColorByName = (name: string) => colorByName(dict.vulStatusNames, dict.colors.vulStatus, name)

/* ============================================================
   计划 / 报告 / 导出任务 / 导入批次状态标签
   ============================================================ */

export const planStatusSoftStyle = (s: number) =>
  softStyle(dict.colors.testingPlanStatus[s] ?? FALLBACK_COLOR)

export const reportStatusName = (s: string) => dict.reportStatusNames[s] ?? s
export const reportStatusSoftStyle = (s: string) =>
  softStyle(dict.colors.reportStatus[s] ?? FALLBACK_COLOR)

export const exportJobName = (s: string) => dict.exportJobStatusNames[s] ?? s
export const exportJobColor = (s: string) => dict.colors.exportJobStatus[s] ?? FALLBACK_COLOR
export const exportJobSoftStyle = (s: string) => softStyle(exportJobColor(s))

export const importStatusMeta = (s: string) => ({
  label: dict.importBatchStatusNames[s] ?? s,
  color: dict.colors.importBatchStatus[s] ?? FALLBACK_COLOR,
})

export const importRecordMeta = (s: string) => ({
  label: dict.importRecordStatusNames[s] ?? s,
  color: dict.colors.importRecordStatus[s] ?? FALLBACK_COLOR,
})

/* ============================================================
   资产 / URL 标签 / 漏洞类型
   ============================================================ */

export const assetStatusMeta = (s: number) => ({
  label: dict.assetStatusNames[s] ?? String(s),
  color: dict.colors.assetStatus[s] ?? FALLBACK_COLOR,
})

export const urlTagMeta = (s: number) => ({
  label: dict.urlTagNames[s] ?? String(s),
  color: dict.colors.urlTag[s] ?? FALLBACK_COLOR,
})

// 未知类型码（含动态新增 code≥1000）自动落到灰色
export const vulTypeColor = (t: number | null | undefined) =>
  dict.colors.vulType[Number(t) ?? 75] ?? FALLBACK_COLOR
export const vulTypeSoftStyle = (t: number | null | undefined) => softStyle(vulTypeColor(t))

/* ============================================================
   漏扫基线工单（nonpen 命名空间：测试项 / 状态 / 操作）
   ============================================================ */

export const nonpenItems = () => dict.nonpen.items
export const nonpenItemMeta = (status: string) => ({
  label: dict.nonpen.status[status] ?? status,
  color: dict.colors.nonpenItem[status] ?? FALLBACK_COLOR,
})
export const nonpenActions = (status: string) => dict.nonpen.actions[status] ?? []
export const nonpenActionLabel = (action: string) => dict.nonpen.actionNames[action] ?? action

/* ============================================================
   纯 UI 色板（非字典，属界面设计令牌）
   ============================================================ */

// 统计卡色板（渗透/漏扫基线工单统计卡片共用，语义化命名便于阅读）
export const STAT_CARD_COLORS = {
  blue: '#409EFF',
  green: '#67C23A',
  orange: '#E6A23C',
  red: '#F56C6C',
  gray: '#909399',
} as const
