import { beforeEach, describe, expect, it } from 'vitest'
import {
  applyDictMeta,
  assetStatusMeta,
  dotStyle,
  exportJobName,
  exportJobSoftStyle,
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
  softStyle,
  statusColorByName,
  statusLabel,
  statusSoftStyleEx,
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
    report_status: { draft: '草稿' },
    import_batch_status: { parsed: '待确认' },
    import_record_status: { confirmed: '已入库' },
    export_job_status: { done: '已完成' },
    colors: {
      vul_level: { 10: '#DC2626', 50: '#059669' },
      vul_status: { 50: '#D97706', 60: '#059669' },
      vul_type: { 55: '#059669' },
      testing_plan_status: { 70: '#059669' },
      report_status: { draft: '#8A968F' },
      asset_status: { 10: '#059669' },
      url_tag: { 10: '#0284C7' },
      nonpen_item: { not_started: '#8A968F' },
      import_batch_status: { parsed: '#0284C7' },
      import_record_status: { confirmed: '#059669' },
      export_job_status: { done: '#059669' },
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
    expect(levelColor(10)).toBe('#DC2626')
  })

  it('未知码回退：色值灰色、名称原样输出', () => {
    expect(levelColor(999)).toBe('#8A968F')
    expect(levelName(999)).toBe('999')
  })

  it('meta 到达前（注册表为空）查询不抛错并走兜底', () => {
    applyDictMeta({
      ...metaFixture(),
      vul_level: {},
      colors: { ...metaFixture().colors, vul_level: {} },
    })
    expect(levelColor(10)).toBe('#8A968F')
    expect(levelName(10)).toBe('10')
  })

  it('meta 漏发任一 key 时兜底为空对象而非 undefined，标签查询不抛错（防报告区域消失回归）', () => {
    const partial = metaFixture() as any
    delete partial.export_job_status
    delete partial.colors.export_job_status
    applyDictMeta(partial)
    expect(exportJobSoftStyle('done')).toEqual(softStyle('#8A968F'))
    expect(exportJobName('done')).toBe('done')
  })

  it('softStyle 生成半透明底 + 同色文字', () => {
    expect(softStyle('#DC2626')).toEqual({ background: '#DC26261f', color: '#DC2626' })
  })

  it('statusSoftStyleEx 复测未通过覆盖状态色，普通状态走字典色', () => {
    expect(statusSoftStyleEx(50, true)).toEqual(softStyle('#E11D48'))
    expect(statusSoftStyleEx(50, false)).toEqual(softStyle('#D97706'))
  })

  it('statusLabel：复测未通过优先，map 参数优先于注册表', () => {
    expect(statusLabel(50, true)).toBe('复测未通过')
    expect(statusLabel(50, false, { 50: '自定义' } as any)).toBe('自定义')
    expect(statusLabel(50, false)).toBe('修复中')
  })

  it('levelBadgeStyle 数量>0 深底白字，数量=0 柔和标签', () => {
    expect(levelBadgeStyle(10, 3)).toEqual({ background: '#DC2626', color: '#fff' })
    expect(levelBadgeStyle(10, 0)).toEqual(softStyle('#DC2626'))
  })

  it('dotStyle 输出 --c 变量；暗色 tone 映射为降饱和变体', () => {
    expect(dotStyle('#DC2626')).toEqual({ '--c': '#DC2626' })
    isDarkTheme.value = true
    expect(tone('#DC2626')).toBe('#f87171')
    expect(tone('#059669')).toBe('#34d399')
    expect(softStyle('#DC2626')).toEqual({ background: '#f871711f', color: '#f87171' })
    // 未收录色值走通用提亮（#123456 各通道向白混合 35% → #657b91）
    expect(tone('#123456')).toBe('#657b91')
    isDarkTheme.value = false
    expect(tone('#DC2626')).toBe('#DC2626')
  })

  it('按名反查：levelColorByName / statusColorByName', () => {
    expect(levelColorByName('严重')).toBe('#DC2626')
    expect(statusColorByName('已修复')).toBe('#059669')
    expect(levelColorByName('不存在的等级')).toBe('#8A968F')
  })

  it('vulTypeColor：已知类型取字典色，null/undefined/未知码兜底灰色', () => {
    expect(vulTypeColor(55)).toBe('#059669')
    expect(vulTypeColor(null)).toBe('#8A968F')
    expect(vulTypeColor(undefined)).toBe('#8A968F')
    expect(vulTypeColor(1000)).toBe('#8A968F')
  })

  it('导入批次 / 资产状态查询走 meta 名称 + 色值', () => {
    expect(importStatusMeta('parsed')).toEqual({ label: '待确认', color: '#0284C7' })
    expect(importStatusMeta('unknown')).toEqual({ label: 'unknown', color: '#8A968F' })
    expect(assetStatusMeta(10)).toEqual({ label: '线上', color: '#059669' })
  })

  it('nonpen 命名空间助手：测试项 / 状态标签 / 操作与文案', () => {
    expect(nonpenItems()).toEqual([{ key: 'baseline', name: '基线扫描', desc: '配置基线 / 安全基线核查' }])
    expect(nonpenItemMeta('not_started')).toEqual({ label: '未开始', color: '#8A968F' })
    expect(nonpenItemMeta('unknown')).toEqual({ label: 'unknown', color: '#8A968F' })
    expect(nonpenActions('not_started')).toEqual(['start', 'ignore'])
    expect(nonpenActions('unknown')).toEqual([])
    expect(nonpenActionLabel('start')).toBe('开始初测')
    expect(nonpenActionLabel('unknown')).toBe('unknown')
  })
})
