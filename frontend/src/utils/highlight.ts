// 关键词高亮工具：先转义再加 <mark>，返回可安全 v-html 的片段（禁止直接拼接原始数据）。

/** HTML 转义：& < > " ' 五字符，避免用户可控文本注入标签 */
export function escapeHtml(text: string): string {
  return (text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 命中关键词高亮：大小写不敏感，全部命中片段包 `<mark class="tl-hl">`。
 * 关键词为空时仅做转义；正则特殊字符无需处理（用 indexOf 逐段切分）。
 */
export function highlight(text: string, keyword: string): string {
  const src = text ?? ''
  const key = (keyword ?? '').trim()
  if (!key) return escapeHtml(src)

  const lowerSrc = src.toLowerCase()
  const lowerKey = key.toLowerCase()
  let out = ''
  let from = 0
  for (;;) {
    const at = lowerSrc.indexOf(lowerKey, from)
    if (at < 0) {
      out += escapeHtml(src.slice(from))
      break
    }
    out += escapeHtml(src.slice(from, at))
    out += '<mark class="tl-hl">' + escapeHtml(src.slice(at, at + lowerKey.length)) + '</mark>'
    from = at + lowerKey.length
  }
  return out
}
