/** 开放 API 指南等文档的 Markdown 渲染（唯一出口，视图不得自行引入渲染器）。
 *
 * html 关闭：原始 HTML 一律转义，渲染结果可安全 v-html；
 * 渲染产物用于「访问令牌」页的指南抽屉等只读展示场景。
 */
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: false, breaks: false })

export function renderMarkdown(source: string): string {
  return md.render(source)
}
