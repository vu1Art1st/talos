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
