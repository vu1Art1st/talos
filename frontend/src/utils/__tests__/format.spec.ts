import { describe, expect, it } from 'vitest'
import { fmtDate, fmtDateTime } from '../format'

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
})
