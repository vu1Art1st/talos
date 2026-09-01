import { describe, expect, it } from 'vitest'
import dayjs from 'dayjs'
import { computeDateRange, mondayOf } from '../dateRange'

// 固定一个周三作为「今天」，规避周日边界歧义（2026-09-02 为周三）
const today = dayjs('2026-09-02')

describe('mondayOf', () => {
  it('周日归到本周周一', () => {
    expect(mondayOf(dayjs('2026-09-06')).format('YYYY-MM-DD')).toBe('2026-08-31')
  })
  it('周一不变', () => {
    expect(mondayOf(dayjs('2026-08-31')).format('YYYY-MM-DD')).toBe('2026-08-31')
  })
})

describe('computeDateRange', () => {
  it('今天', () => {
    expect(computeDateRange('today', null, today)).toEqual(['2026-09-02', '2026-09-02'])
  })
  it('本周（周一起始，止于今天）', () => {
    expect(computeDateRange('this_week', null, today)).toEqual(['2026-08-31', '2026-09-02'])
  })
  it('上周（周一至周日）', () => {
    expect(computeDateRange('last_week', null, today)).toEqual(['2026-08-24', '2026-08-30'])
  })
  it('本月', () => {
    expect(computeDateRange('this_month', null, today)).toEqual(['2026-09-01', '2026-09-02'])
  })
  it('上月（含月末边界）', () => {
    expect(computeDateRange('last_month', null, today)).toEqual(['2026-08-01', '2026-08-31'])
  })
  it('自定义区间原样返回', () => {
    expect(computeDateRange('custom', ['2026-08-04', '2026-08-13'], today))
      .toEqual(['2026-08-04', '2026-08-13'])
  })
  it('空值返回 null', () => {
    expect(computeDateRange('', null, today)).toBeNull()
  })
})
