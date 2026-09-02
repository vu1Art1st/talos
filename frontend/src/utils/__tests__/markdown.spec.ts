import { describe, expect, it } from 'vitest'
import { renderMarkdown } from '../markdown'

describe('renderMarkdown', () => {
  it('渲染标题 / 列表 / 段落', () => {
    const html = renderMarkdown('# 标题\n\n- 项目一\n- 项目二\n\n正文段落')
    expect(html).toContain('<h1>标题</h1>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>项目一</li>')
    expect(html).toContain('<p>正文段落</p>')
  })

  it('渲染表格与代码块（指南文档的主体结构）', () => {
    const html = renderMarkdown(
      '| 参数 | 类型 |\n|---|---|\n| page | int |\n\n```bash\ncurl -sS "$URL"\n```',
    )
    expect(html).toContain('<table>')
    expect(html).toContain('<th>参数</th>')
    expect(html).toContain('<td>page</td>')
    expect(html).toContain('<pre><code class="language-bash">')
  })

  it('原始 HTML 一律转义，渲染结果可安全 v-html', () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
  })

  it('行内代码与加粗', () => {
    const html = renderMarkdown('`tlp_xxx` 与 **Bearer**')
    expect(html).toContain('<code>tlp_xxx</code>')
    expect(html).toContain('<strong>Bearer</strong>')
  })
})
