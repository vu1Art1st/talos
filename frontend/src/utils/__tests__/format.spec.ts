import { describe, expect, it } from 'vitest'
import { fmtDate, fmtDateTime, fmtSlaRemaining } from '../format'

describe('format 时间格式化', () => {
  it('fmtDateTime 格式化为 YYYY-MM-DD HH:mm', () => {
    expect(fmtDateTime('2026-08-19T10:30:00')).toBe('2026-08-19 10:30')
  })

  it('fmtDateTime 空值回退 "-"', () => {
    expect(fmtDateTime(undefined)).toBe('-')
    expect(fmtDateTime(null)).toBe('-')
    expect(fmtDateTime('')).toBe('-')
  })

  it('fmtDateTime 非法值原样返回（不抛错）', () => {
    expect(fmtDateTime('不是时间')).toBe('不是时间')
  })

  it('fmtDate 格式化为 YYYY-MM-DD，空值回退 "-"', () => {
    expect(fmtDate('2026-08-19T10:30:00')).toBe('2026-08-19')
    expect(fmtDate(undefined)).toBe('-')
  })

  // P1-1 SLA 剩余时长：唯一换算口径（天 + 小时 / 逾期前缀）
  it('fmtSlaRemaining 按天 + 小时展示剩余时长', () => {
    expect(fmtSlaRemaining(3)).toBe('3 小时')
    expect(fmtSlaRemaining(24)).toBe('1 天')
    expect(fmtSlaRemaining(52)).toBe('2 天 4 小时')
  })

  it('fmtSlaRemaining 负值（已逾期）加前缀', () => {
    expect(fmtSlaRemaining(-5)).toBe('已逾期 5 小时')
    expect(fmtSlaRemaining(-48)).toBe('已逾期 2 天')
  })

  it('fmtSlaRemaining 未设置截止时间回退 "-"', () => {
    expect(fmtSlaRemaining(null)).toBe('-')
    expect(fmtSlaRemaining(undefined)).toBe('-')
  })
})
