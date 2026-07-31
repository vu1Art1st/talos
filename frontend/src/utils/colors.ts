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
