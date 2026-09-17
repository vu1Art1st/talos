import { describe, expect, it } from 'vitest'
import { escapeHtml, highlight } from '../highlight'

describe('escapeHtml', () => {
  it('转义五个危险字符', () => {
    expect(escapeHtml(`<script>alert("x")</script>&'`)).toBe(
      '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;&amp;&#39;',
    )
  })

  it('空值回退空串', () => {
    expect(escapeHtml('')).toBe('')
    expect(escapeHtml(undefined as unknown as string)).toBe('')
  })
})

describe('highlight', () => {
  it('关键词为空时仅转义，不加标记', () => {
    expect(highlight('<b>SQL注入</b>', '')).toBe('&lt;b&gt;SQL注入&lt;/b&gt;')
    expect(highlight('<b>SQL注入</b>', '   ')).toBe('&lt;b&gt;SQL注入&lt;/b&gt;')
  })

  it('大小写不敏感命中并包裹 mark', () => {
    expect(highlight('Fastjson 反序列化', 'fastjson')).toBe(
      '<mark class="tl-hl">Fastjson</mark> 反序列化',
    )
  })

  it('多处命中全部高亮，保留原始大小写', () => {
    expect(highlight('注入与注入', '注入')).toBe(
      '<mark class="tl-hl">注入</mark>与<mark class="tl-hl">注入</mark>',
    )
  })

  it('命中内容先转义，不产生标签注入', () => {
    const out = highlight('<img src=x onerror=alert(1)>', 'onerror')
    expect(out).toContain('<mark class="tl-hl">onerror</mark>')
    expect(out).not.toContain('<img')
    expect(out.startsWith('&lt;img')).toBe(true)
  })

  it('未命中时原样转义返回', () => {
    expect(highlight('SQL注入', 'CVE-2020-1957')).toBe('SQL注入')
  })
})
