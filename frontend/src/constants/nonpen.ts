// 非渗透计划前端常量：与后端 app/constants.py 的 NONPEN_* 保持一致（唯一来源在后端，此处仅镜像）

// 测试项定义（key -> 名称/说明/图标）
export const NONPEN_ITEMS = [
  { key: 'baseline', name: '基线扫描', desc: '配置基线 / 安全基线核查' },
  { key: 'host', name: '主机漏洞扫描', desc: '服务 / 端口 / 补丁漏洞' },
  { key: 'web', name: 'Web漏洞扫描', desc: 'Web 应用 / 接口漏洞' },
] as const

// 测试项状态（忽略用更浅的灰弱化，与「未开始」的正常灰区分）
export const NONPEN_ITEM_STATUS: Record<string, string> = {
  not_started: '未开始',
  testing: '初测中',
  wait_retest: '等待复测',
  retesting: '复测中',
  retest_done: '复测完成',
  ignored: '忽略',
}

// 状态 -> 展示色值（明/暗双主题通用）
export const NONPEN_ITEM_COLORS: Record<string, string> = {
  not_started: '#909399',
  testing: '#409EFF',
  wait_retest: '#E6A23C',
  retesting: '#E6A23C',
  retest_done: '#67C23A',
  ignored: '#c0c4cc',
}

// 状态 -> 允许的操作（与后端 NONPEN_ITEM_ACTIONS 一致，用于渲染按钮）
export const NONPEN_ITEM_ACTIONS: Record<string, string[]> = {
  not_started: ['start', 'ignore'],
  testing: ['done', 'direct_done', 'ignore'],
  wait_retest: ['start_retest', 'ignore'],
  retesting: ['pass', 'fail', 'ignore'],
  retest_done: ['reset'],
  ignored: ['unignore'],
}

// 操作名 -> 按钮文案
export const NONPEN_ACTION_LABELS: Record<string, string> = {
  start: '开始初测',
  done: '初测完成',
  direct_done: '直接完成',
  start_retest: '发起复测',
  pass: '复测通过',
  fail: '复测未通过',
  reset: '置回未开始',
  ignore: '忽略',
  unignore: '取消忽略',
}

export const nonpenItemMeta = (status: string) => ({
  label: NONPEN_ITEM_STATUS[status] ?? status,
  color: NONPEN_ITEM_COLORS[status] ?? '#909399',
})
