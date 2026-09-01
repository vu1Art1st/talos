// 时间范围快捷项计算：按「初测完成时间」筛选渗透测试工单（周一起始），供结论输出使用
import dayjs, { type Dayjs } from 'dayjs'

export const DATE_RANGE_OPTIONS = [
  { label: '今天', value: 'today' },
  { label: '本周', value: 'this_week' },
  { label: '上周', value: 'last_week' },
  { label: '本月', value: 'this_month' },
  { label: '上月', value: 'last_month' },
  { label: '自定义', value: 'custom' },
] as const

export type DateRangeKind = (typeof DATE_RANGE_OPTIONS)[number]['value']

// 周一起始计算（dayjs 默认周日，业务口径周一为一周起点）
export function mondayOf(d: Dayjs): Dayjs {
  const dow = d.day() // 0=周日 ... 6=周六
  return d.add(dow === 0 ? -6 : 1 - dow, 'day')
}

/** 由快捷项与自定义区间计算 [起, 止] 日期（YYYY-MM-DD）；无有效范围返回 null。 */
export function computeDateRange(
  kind: string,
  custom: [string, string] | null,
  today: Dayjs = dayjs(),
): [string, string] | null {
  switch (kind) {
    case 'today':
      return [today.format('YYYY-MM-DD'), today.format('YYYY-MM-DD')]
    case 'this_week':
      return [mondayOf(today).format('YYYY-MM-DD'), today.format('YYYY-MM-DD')]
    case 'last_week': {
      const start = mondayOf(today).subtract(1, 'week')
      return [start.format('YYYY-MM-DD'), start.add(6, 'day').format('YYYY-MM-DD')]
    }
    case 'this_month':
      return [today.startOf('month').format('YYYY-MM-DD'), today.format('YYYY-MM-DD')]
    case 'last_month': {
      const start = today.subtract(1, 'month').startOf('month')
      return [start.format('YYYY-MM-DD'), today.subtract(1, 'month').endOf('month').format('YYYY-MM-DD')]
    }
    case 'custom':
      return custom
    default:
      return null
  }
}
