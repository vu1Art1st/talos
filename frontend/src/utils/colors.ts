// 漏洞等级 / 状态全站统一色板（唯一色源，勿在视图内散落硬编码）

// 等级：严重-深红 高危-红 中危-橙 低危-蓝 安全-绿
export const LEVEL_COLORS: Record<number, string> = {
  10: '#A61B29', // 严重 深红
  20: '#F56C6C', // 高危 红
  30: '#E6A23C', // 中危 橙
  40: '#409EFF', // 低危 蓝
  50: '#67C23A', // 安全 绿
}

// Dashboard 等按中文名索引时使用
export const LEVEL_COLORS_BY_NAME: Record<string, string> = {
  严重: LEVEL_COLORS[10],
  高危: LEVEL_COLORS[20],
  中危: LEVEL_COLORS[30],
  低危: LEVEL_COLORS[40],
  安全: LEVEL_COLORS[50],
}

// 状态：未修复-红 修复中/复测中-橙 已修复-绿 已忽略/暂不处理-灰
export const STATUS_COLORS: Record<number, string> = {
  10: '#F56C6C', // 未修复
  50: '#E6A23C', // 修复中
  55: '#E6A23C', // 复测中
  60: '#67C23A', // 已修复
  20: '#909399', // 已忽略
  35: '#909399', // 暂不处理
}

export const STATUS_COLORS_BY_NAME: Record<string, string> = {
  未修复: STATUS_COLORS[10],
  修复中: STATUS_COLORS[50],
  复测中: STATUS_COLORS[55],
  已修复: STATUS_COLORS[60],
  已忽略: STATUS_COLORS[20],
  暂不处理: STATUS_COLORS[35],
}

export const levelColor = (lv: number) => LEVEL_COLORS[lv] ?? '#909399'
export const statusColor = (s: number) => STATUS_COLORS[s] ?? '#909399'

// 复测未通过为展示层状态：修复中(50) 且经历过复测(is_retest)，不新增状态码
export const RETEST_FAILED_COLOR = '#F56C6C'
export const isRetestFailed = (status: number, isRetest?: boolean) => status === 50 && !!isRetest
export const statusLabel = (status: number, isRetest: boolean | undefined, map?: Record<number, string>) =>
  isRetestFailed(status, isRetest) ? '复测未通过' : (map?.[status] ?? String(status))

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
   名称映射（全站唯一，消除各视图重复定义）
   ============================================================ */

// 风险等级中文名（对齐 VUL_LEVEL）
export const LEVEL_NAMES: Record<number, string> = {
  10: '严重',
  20: '高危',
  30: '中危',
  40: '低危',
  50: '安全',
}
export const levelName = (lv: number) => LEVEL_NAMES[lv] ?? String(lv)

// 漏洞状态中文名（对齐 VUL_STATUS）
export const STATUS_NAMES: Record<number, string> = {
  10: '未修复',
  20: '已忽略',
  35: '暂不处理',
  50: '修复中',
  55: '复测中',
  60: '已修复',
}
export const statusName = (s: number) => STATUS_NAMES[s] ?? String(s)

// 测试计划状态（对齐 TESTING_PLAN_STATUS：10未测试/20初测中/30等待复测/40复测申请/50复测中/60复测完成/70测试通过）
export const PLAN_STATUS_COLORS: Record<number, string> = {
  10: '#909399',
  20: '#E6A23C',
  30: '#4F46E5',
  40: '#F56C6C',
  50: '#E6A23C',
  60: '#67C23A',
  70: '#67C23A',
}
export const planStatusSoftStyle = (s: number) => softStyle(PLAN_STATUS_COLORS[s] ?? '#909399')

// 报告状态（字符串 draft/final/completed 兼容）
export const REPORT_STATUS: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: '#909399' },
  final: { label: '已定稿', color: '#4F46E5' },
  completed: { label: '已完成', color: '#67C23A' },
}
export const reportStatusName = (s: string) => REPORT_STATUS[s]?.label ?? s
export const reportStatusSoftStyle = (s: string) => softStyle(REPORT_STATUS[s]?.color ?? '#909399')

// 导出任务状态（done/failed/pending/running）
export const EXPORT_JOB_META: Record<string, { label: string; color: string }> = {
  done: { label: '已完成', color: '#67C23A' },
  failed: { label: '失败', color: '#F56C6C' },
  pending: { label: '生成中', color: '#E6A23C' },
  running: { label: '生成中', color: '#E6A23C' },
}
export const exportJobName = (s: string) => EXPORT_JOB_META[s]?.label ?? s
export const exportJobSoftStyle = (s: string) => softStyle(EXPORT_JOB_META[s]?.color ?? '#909399')

// 统计卡色板（渗透/漏扫基线工单统计卡片共用，语义化命名便于阅读）
export const STAT_CARD_COLORS = {
  blue: '#409EFF',
  green: '#67C23A',
  orange: '#E6A23C',
  red: '#F56C6C',
  gray: '#909399',
} as const

// Word 导入批次状态（pending/parsing/parsed/confirmed/failed）
export const IMPORT_STATUS: Record<string, { label: string; color: string }> = {
  pending: { label: '排队中', color: '#909399' },
  parsing: { label: '解析中', color: '#E6A23C' },
  parsed: { label: '待确认', color: '#4F46E5' },
  confirmed: { label: '已入库', color: '#67C23A' },
  failed: { label: '解析失败', color: '#F56C6C' },
}
export const importStatusMeta = (s: string) => IMPORT_STATUS[s] ?? { label: s, color: '#909399' }

// Word 导入记录状态（parsed/error/confirmed/discarded）
export const IMPORT_RECORD_STATUS: Record<string, { label: string; color: string }> = {
  parsed: { label: '待确认', color: '#4F46E5' },
  error: { label: '解析异常', color: '#E6A23C' },
  confirmed: { label: '已入库', color: '#67C23A' },
  discarded: { label: '已丢弃', color: '#909399' },
}
export const importRecordMeta = (s: string) => IMPORT_RECORD_STATUS[s] ?? { label: s, color: '#909399' }

// 资产状态（对齐 ASSET_STATUS：10线上/20上线前/30下线）
export const ASSET_STATUS_META: Record<number, { label: string; color: string }> = {
  10: { label: '线上', color: '#67C23A' },
  20: { label: '上线前', color: '#E6A23C' },
  30: { label: '下线', color: '#909399' },
}
export const assetStatusMeta = (s: number) => ASSET_STATUS_META[s] ?? { label: String(s), color: '#909399' }

// 公网URL 标签（对齐 URL_TAG：10互联网/20办公网）
export const URL_TAG_META: Record<number, { label: string; color: string }> = {
  10: { label: '互联网', color: '#4F46E5' },
  20: { label: '办公网', color: '#909399' },
}
export const urlTagMeta = (s: number) => URL_TAG_META[s] ?? { label: String(s), color: '#909399' }
