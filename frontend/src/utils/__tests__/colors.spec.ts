import { beforeEach, describe, expect, it } from 'vitest'
import {
  applyDictMeta,
  assetStatusMeta,
  dotStyle,
  exportJobName,
  exportJobSoftStyle,
  importOutcomeMeta,
  importStatusMeta,
  isDarkTheme,
  levelBadgeStyle,
  levelColor,
  levelColorByName,
  levelName,
  nonpenActionLabel,
  nonpenActions,
  nonpenItemMeta,
  nonpenItems,
  notifyDeliveryMeta,
  patScopeName,
  patScopeOptions,
  retestStateName,
  retestStateSoftStyle,
  slaStateMeta,
  slaStateSoftStyle,
  solidColor,
  softStyle,
  statusColorByName,
  statusLabel,
  statusSoftStyleWithRetest,
  tone,
  vulTypeColor,
  type DictMetaPayload,
} from '../colors'

/** 与后端 /meta 契约一致的最小字典夹具（键名/结构与 misc.py 下发一一对应，色值为 demo-2 浅色版） */
function metaFixture(): DictMetaPayload {
  return {
    vul_level: { 10: '严重', 50: '安全' },
    vul_status: { 50: '修复中', 60: '已修复' },
    asset_status: { 10: '线上' },
    url_tag: { 10: '互联网' },
    import_batch_status: { parsed: '待确认' },
    import_record_status: { confirmed: '已入库' },
    export_job_status: { done: '已完成' },
    colors: {
      vul_level: { 10: 'red', 50: 'jade' },
      vul_status: { 50: 'amber', 60: 'jade' },
      vul_type: { 55: 'jade' },
      testing_plan_status: { 70: 'jade' },
      asset_status: { 10: 'jade' },
      url_tag: { 10: 'sky' },
      nonpen_item: { not_started: 'sage' },
      import_batch_status: { parsed: 'sky' },
      import_record_status: { confirmed: 'jade' },
      export_job_status: { done: 'jade' },
    },
    nonpen: {
      items: [{ key: 'baseline', name: '基线扫描', desc: '配置基线 / 安全基线核查' }],
      status: { not_started: '未开始' },
      actions: { not_started: ['start', 'ignore'] },
      action_names: { start: '开始初测' },
    },
  }
}

beforeEach(() => {
  isDarkTheme.value = false
  applyDictMeta(metaFixture())
})

describe('colors 字典注册表（meta 单源）', () => {
  it('applyDictMeta 注入后按码查询名称与色值', () => {
    expect(levelName(10)).toBe('严重')
    expect(levelColor(10)).toBe('var(--red-11)')
  })

  it('未知码回退：色值灰色、名称原样输出', () => {
    expect(levelColor(999)).toBe('var(--sage-11)')
    expect(levelName(999)).toBe('999')
  })

  it('meta 到达前（注册表为空）查询不抛错并走兜底', () => {
    applyDictMeta({
      ...metaFixture(),
      vul_level: {},
      colors: { ...metaFixture().colors, vul_level: {} },
    })
    expect(levelColor(10)).toBe('var(--sage-11)')
    expect(levelName(10)).toBe('10')
  })

  it('meta 漏发任一 key 时兜底为空对象而非 undefined，标签查询不抛错（防报告区域消失回归）', () => {
    // 故意构造「漏发 export_job_status」的不完整 meta（本用例即验证兜底），故顶层与 colors 均放宽为 Partial
    type PartialMeta = Partial<Omit<DictMetaPayload, 'colors'>> & { colors?: Partial<DictMetaPayload['colors']> }
    const partial = metaFixture() as PartialMeta
    delete partial.export_job_status
    delete partial.colors?.export_job_status
    applyDictMeta(partial as DictMetaPayload)
    expect(exportJobSoftStyle('done')).toEqual(softStyle('sage'))
    expect(exportJobName('done')).toBe('done')
  })

  it('softStyle 生成 Radix Alpha 底 + 11 级文字', () => {
    expect(softStyle('red')).toEqual({ background: 'var(--red-a3)', color: 'var(--red-11)' })
  })

  // P1 批次新增字典：/meta 未下发时按原值兜底，不抛错
  it('P1 新增字典（SLA / 投递 / scope）在 meta 缺省时回退原值', () => {
    expect(slaStateMeta('overdue').label).toBe('overdue')
    expect(slaStateSoftStyle('overdue')).toEqual(softStyle('sage'))
    expect(notifyDeliveryMeta('dead').label).toBe('dead')
    expect(patScopeName('plan_write')).toBe('plan_write')
    expect(patScopeOptions()).toEqual([])
    expect(importOutcomeMeta('merged').label).toBe('merged')
  })

  it('P1 新增字典注入后按码查询名称与色值', () => {
    applyDictMeta({
      ...metaFixture(),
      sla_state: { overdue: '已逾期' },
      notify_delivery_status: { dead: '死信' },
      pat_scope: { read: '只读' },
      colors: {
        ...metaFixture().colors,
        sla_state: { overdue: 'red' },
        notify_delivery_status: { dead: 'red' },
      },
    })
    expect(slaStateMeta('overdue')).toEqual({ label: '已逾期', color: 'var(--red-11)' })
    expect(notifyDeliveryMeta('dead').label).toBe('死信')
    expect(patScopeOptions()).toEqual([{ value: 'read', label: '只读' }])
  })

  it('statusSoftStyleWithRetest 复测未通过覆盖状态色，普通状态走字典色', () => {
    expect(statusSoftStyleWithRetest(50, true)).toEqual(softStyle('ruby'))
    expect(statusSoftStyleWithRetest(50, false)).toEqual(softStyle('amber'))
  })

  it('statusLabel：复测未通过优先，map 参数优先于注册表', () => {
    expect(statusLabel(50, true)).toBe('复测未通过')
    expect(statusLabel(50, false, { 50: '自定义' })).toBe('自定义')
    expect(statusLabel(50, false)).toBe('修复中')
  })

  it('levelBadgeStyle 数量>0 实心底色，数量=0 柔和标签', () => {
    expect(levelBadgeStyle(10, 3)).toEqual({ background: 'var(--red-9)', color: 'var(--tl-on-primary)' })
    expect(levelBadgeStyle(10, 0)).toEqual(softStyle('red'))
  })

  it('dotStyle 输出 --c 变量；明暗模式由 Radix 变量切换', () => {
    expect(dotStyle('red')).toEqual({ '--c': 'var(--red-9)' })
    expect(solidColor('var(--sky-11)')).toBe('var(--sky-9)')
    isDarkTheme.value = true
    expect(tone('red')).toBe('var(--red-11)')
    expect(tone('jade')).toBe('var(--jade-11)')
    expect(softStyle('red')).toEqual({ background: 'var(--red-a3)', color: 'var(--red-11)' })
    expect(dotStyle('jade')).toEqual({ '--c': 'var(--jade-9)' })
    expect(tone('unknown-family')).toBe('var(--sage-11)')
    isDarkTheme.value = false
    expect(tone('red')).toBe('var(--red-11)')
  })

  it('按名反查：levelColorByName / statusColorByName', () => {
    expect(levelColorByName('严重')).toBe('var(--red-11)')
    expect(statusColorByName('已修复')).toBe('var(--jade-11)')
    expect(levelColorByName('不存在的等级')).toBe('var(--sage-11)')
  })

  it('vulTypeColor：已知类型取字典色，null/undefined/未知码兜底灰色', () => {
    expect(vulTypeColor(55)).toBe('var(--jade-11)')
    expect(vulTypeColor(null)).toBe('var(--sage-11)')
    expect(vulTypeColor(undefined)).toBe('var(--sage-11)')
    expect(vulTypeColor(1000)).toBe('var(--sage-11)')
  })

  it('导入批次 / 资产状态查询走 meta 名称 + 色值', () => {
    expect(importStatusMeta('parsed')).toEqual({ label: '待确认', color: 'var(--sky-11)' })
    expect(importStatusMeta('unknown')).toEqual({ label: 'unknown', color: 'var(--sage-11)' })
    expect(assetStatusMeta(10)).toEqual({ label: '线上', color: 'var(--jade-11)' })
  })

  it('nonpen 命名空间助手：测试项 / 状态标签 / 操作与文案', () => {
    expect(nonpenItems()).toEqual([{ key: 'baseline', name: '基线扫描', desc: '配置基线 / 安全基线核查' }])
    expect(nonpenItemMeta('not_started')).toEqual({ label: '未开始', color: 'var(--sage-11)' })
    expect(nonpenItemMeta('unknown')).toEqual({ label: 'unknown', color: 'var(--sage-11)' })
    expect(nonpenActions('not_started')).toEqual(['start', 'ignore'])
    expect(nonpenActions('unknown')).toEqual([])
    expect(nonpenActionLabel('start')).toBe('开始初测')
    expect(nonpenActionLabel('unknown')).toBe('unknown')
  })

  it('报告复测状态：三态名称与柔和样式（未知/缺省回落「未发起复测」）', () => {
    expect(retestStateName('none')).toBe('未发起复测')
    expect(retestStateName('ongoing')).toBe('复测中')
    expect(retestStateName('done')).toBe('复测完成')
    expect(retestStateName(undefined)).toBe('未发起复测')
    expect(retestStateName('unknown')).toBe('未发起复测')
    expect(retestStateSoftStyle('done')).toEqual(softStyle('jade'))
    expect(retestStateSoftStyle(null)).toEqual(softStyle('sage'))
  })
})
