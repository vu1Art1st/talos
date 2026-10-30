import { describe, expect, it } from 'vitest'
// @ts-expect-error Vitest 在 Node 中运行，前端浏览器 tsconfig 不包含 Node 类型。
import { readFileSync } from 'node:fs'

const sources = import.meta.glob([
  '/src/*.{vue,css,ts}',
  '/src/**/*.{vue,css,ts}',
], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const styleCss = readFileSync('src/style.css', 'utf8')

function offenders(pattern: RegExp, label: string) {
  const found: string[] = []
  for (const [file, text] of Object.entries(sources)) {
    if (file.includes('/__tests__/')) continue
    if (pattern.test(text)) found.push(`${label}: ${file}`)
    pattern.lastIndex = 0
  }
  return found
}

function sourceOf(suffix: string) {
  return Object.entries(sources).find(([file]) => file.endsWith(suffix))?.[1] ?? ''
}

describe('UI 设计令牌守卫', () => {
  it('不直接使用颜色值、渐变或 U+00B7', () => {
    expect(offenders(/#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b|rgba?\(|color-mix\(/g, '直接颜色')).toEqual([])
    expect(
      offenders(/(?:linear|radial|conic)-gradient/g, '渐变')
        .filter((item) => !item.endsWith('/src/views/Login.vue')),
    ).toEqual([])
    expect(offenders(/\u00B7/g, '中点文案')).toEqual([])
  })

  it('字号只允许 12px / 14px / 16px', () => {
    expect(offenders(/font-size:\s*(?!12px|14px|16px|inherit|var\()[0-9.]+(?:px|rem)/g, '非法字号')).toEqual([])
    expect(offenders(/text-\[[^\]]+\]/g, '任意字号类')).toEqual([])
    expect(offenders(/font-weight:\s*(?:700|800|900)|font-(?:bold|extrabold|black)/g, '超限字重')).toEqual([])
  })

  it('边框使用 0.5px，圆角只使用 0 / 4px / 8px', () => {
    expect(offenders(/\bborder(?:-(?:top|right|bottom|left))?(?:-width)?:\s*(?:1px|[2-9]\d*px)/g, '粗边框')).toEqual([])
    expect(offenders(/border-radius:\s*(?:2px|3px|5px|6px|7px|9px|10px|11px|12px|999px)/g, '非法圆角')).toEqual([])
    expect(offenders(/rounded-\[[^\]]+\]/g, '任意圆角类')).toEqual([])
  })

  it('动效只使用 ease-out 250ms，禁止装饰动画', () => {
    expect(offenders(/transition:\s*all\b/g, 'transition all')).toEqual([])
    expect(offenders(/(?:^|[;{\s])animation\s*:/gm, 'animation 声明')).toEqual([])
    expect(offenders(/transition:[^;]*(?:ease-in|ease-in-out|ease(?!-out))/g, '非 ease-out 动效')).toEqual([])
  })

  it('保留原品牌配色并区分浅色正文与标题对比度', () => {
    const style = styleCss
    expect(style).toContain('--tl-bg: var(--sage-2)')
    expect(style).toContain('--tl-primary: var(--jade-9)')
    expect(style).toContain('--tl-text-strong: var(--sage-12)')
    expect(style).toContain('--tl-text-1: var(--sage-11)')
    expect(style).toContain('--tl-text-3: var(--sage-10)')
    expect(style).toMatch(/html\.dark[\s\S]*--tl-text-3: var\(--sage-11\)/)
    expect(offenders(/var\(--(?:gray|mint)-\d+\)/g, '旧 Radix 色族')).toEqual([])
  })

  it('列表表格恢复隔行底色并保留独立悬停态', () => {
    const style = styleCss
    expect(style).toContain('--tl-table-stripe: var(--sage-2)')
    expect(style).toContain('--tl-table-hover: var(--sage-4)')
    expect(style).toContain('.el-table__body tr.el-table__row--striped > td.el-table__cell')
    expect(style).toContain('.el-table__body tr.el-table__row--striped:hover > td.el-table__cell')
  })

  it('登录页保留完整品牌构图且使用 Radix Alpha 装饰色', () => {
    const login = sourceOf('/src/views/Login.vue')
    expect(login).toContain('login-dots')
    expect(login).toContain('login-orb')
    expect(login).toContain('var(--jade-a3)')
    expect(login).toContain('var(--sky-a3)')
    expect(login).toContain('linear-gradient(135deg, var(--jade-9), var(--jade-10) 55%, var(--jade-11))')
  })
})
