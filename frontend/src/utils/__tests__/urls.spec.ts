import { describe, expect, it } from 'vitest'
import {
  AFFECTED_URL_ITEM_MAX_LENGTH,
  AFFECTED_URL_MAX_COUNT,
  assetUrls,
  cleanUrls,
  joinAffectedUrl,
  mergeUrls,
  parseAffectedUrl,
  validateAffectedUrls,
} from '../urls'

describe('urls 工单被测系统URL工具', () => {
  it('mergeUrls 去重保序合并，新增项追加在后', () => {
    expect(mergeUrls(['https://a.com', 'http://b.com'], ['http://b.com', 'https://c.com']))
      .toEqual(['https://a.com', 'http://b.com', 'https://c.com'])
  })

  it('mergeUrls 兼容 { url } 对象与字符串混排（资产 public_urls 条目）', () => {
    expect(mergeUrls([], [{ url: 'https://a.com' }, 'http://b.com', { url: '' }]))
      .toEqual(['https://a.com', 'http://b.com'])
  })

  it('mergeUrls trim 后比较去重，空值/空白过滤', () => {
    expect(mergeUrls([' https://a.com '], ['https://a.com', '  ', '']))
      .toEqual(['https://a.com'])
  })

  it('mergeUrls 空入参安全', () => {
    expect(mergeUrls([], [])).toEqual([])
  })

  it('cleanUrls 提交前清洗：trim、去空、去重保序', () => {
    expect(cleanUrls([' https://a.com ', '', 'https://a.com', 'http://b.com']))
      .toEqual(['https://a.com', 'http://b.com'])
  })

  it('assetUrls 汇总资产公网+内网 URL，空资产回退空数组', () => {
    expect(assetUrls({
      public_urls: [{ url: 'https://a.com', tag: 10 }],
      internal_urls: ['http://10.0.0.8:8080'],
    })).toEqual(['https://a.com', 'http://10.0.0.8:8080'])
    expect(assetUrls(null)).toEqual([])
    expect(assetUrls({})).toEqual([])
  })
})

describe('urls 影响URL 解析与校验', () => {
  it('parseAffectedUrl 按换行、分号（含全角）切分并 trim/去空/去重保序', () => {
    expect(parseAffectedUrl('https://a.com/1\nhttps://a.com/2\r\nhttps://a.com/3'))
      .toEqual(['https://a.com/1', 'https://a.com/2', 'https://a.com/3'])
    expect(parseAffectedUrl('https://a.com/1;https://a.com/2；https://a.com/3'))
      .toEqual(['https://a.com/1', 'https://a.com/2', 'https://a.com/3'])
    expect(parseAffectedUrl('  https://b.com/1  \n\n https://a.com/2 \nhttps://b.com/1'))
      .toEqual(['https://b.com/1', 'https://a.com/2'])
    expect(parseAffectedUrl('')).toEqual([])
    expect(parseAffectedUrl(null)).toEqual([])
    expect(parseAffectedUrl(';;；\n')).toEqual([])
  })

  it('joinAffectedUrl 输出后端换行分隔单字段口径', () => {
    expect(joinAffectedUrl([' https://a.com/1 ', '', 'https://a.com/1', 'https://b.com/2']))
      .toBe('https://a.com/1\nhttps://b.com/2')
    expect(joinAffectedUrl([])).toBe('')
  })

  it('validateAffectedUrls 合法输入通过（含 100 条与单条 2048 字符上界）', () => {
    expect(validateAffectedUrls([]).ok).toBe(true)
    const max = Array.from({ length: AFFECTED_URL_MAX_COUNT }, (_, i) => `https://a.com/${i}`)
    expect(validateAffectedUrls(max).ok).toBe(true)
    const longest = 'https://a.com/' + 'a'.repeat(AFFECTED_URL_ITEM_MAX_LENGTH - 14)
    expect(longest.length).toBe(AFFECTED_URL_ITEM_MAX_LENGTH)
    expect(validateAffectedUrls([longest]).ok).toBe(true)
  })

  it('validateAffectedUrls 条数超限报错（与后端同文案）', () => {
    const over = Array.from({ length: AFFECTED_URL_MAX_COUNT + 1 }, (_, i) => `https://a.com/${i}`)
    const result = validateAffectedUrls(over)
    expect(result.ok).toBe(false)
    expect(result.message).toBe('影响URL 最多 100 条，当前共 101 条，请分批录入')
  })

  it('validateAffectedUrls 单条超长与含空白字符报错并给出条目序号', () => {
    const tooLong = 'https://a.com/' + 'a'.repeat(AFFECTED_URL_ITEM_MAX_LENGTH)
    const long = validateAffectedUrls(['https://a.com/1', tooLong])
    expect(long.ok).toBe(false)
    expect(long.invalidIndexes).toEqual([1])
    expect(long.message).toContain('第 2 条影响URL 长度')
    expect(long.message).toContain('超出上限 2048 字符')

    const spaced = validateAffectedUrls(['https://a.com/1', 'https://a.com/2 描述'])
    expect(spaced.ok).toBe(false)
    expect(spaced.invalidIndexes).toEqual([1])
    expect(spaced.message).toBe('第 2 条影响URL 含空格或非法字符，请修正后再提交')

    const tabbed = validateAffectedUrls(['https://a.com/1\tx'])
    expect(tabbed.ok).toBe(false)
  })

  it('100 条切分去重为线性量级（万级字符输入不阻塞）', () => {
    const raw = Array.from({ length: AFFECTED_URL_MAX_COUNT }, (_, i) => `https://a.com/path/${i}`).join('\n')
    const start = performance.now()
    const parsed = parseAffectedUrl(raw)
    const cost = performance.now() - start
    expect(parsed.length).toBe(AFFECTED_URL_MAX_COUNT)
    expect(cost).toBeLessThan(50)
  })
})
