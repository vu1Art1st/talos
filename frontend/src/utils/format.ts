// 全站统一时间格式化（唯一时间展示口径，禁止视图内散落 slice/replace 自定义格式）
import dayjs from 'dayjs'

/** 日期时间：YYYY-MM-DD HH:mm，空值回退 '-' */
export function fmtDateTime(v?: string | null): string {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : String(v)
}

/** 日期：YYYY-MM-DD，空值回退 '-' */
export function fmtDate(v?: string | null): string {
  if (!v) return '-'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD') : String(v)
}

/** SLA 剩余时长展示（唯一口径，禁止视图内自行换算）：小时 → 「3 天 4 小时」/「-2 天」 */
export function fmtSlaRemaining(hours?: number | null): string {
  if (hours === null || hours === undefined) return '-'
  const overdue = hours < 0
  const abs = Math.abs(hours)
  const days = Math.floor(abs / 24)
  const rest = Math.round(abs % 24)
  const text = days > 0 ? `${days} 天${rest ? ` ${rest} 小时` : ''}` : `${rest} 小时`
  return overdue ? `已逾期 ${text}` : text
}
