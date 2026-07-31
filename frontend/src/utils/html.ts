import DOMPurify from 'dompurify'

// 富文本渲染前的前端兜底清洗（后端已做白名单过滤，这里作为纵深防御）
export function safeHtml(html?: string | null): string {
  return DOMPurify.sanitize(html || '')
}
