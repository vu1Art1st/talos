import { describe, expect, it } from 'vitest'
import { assetUrls, cleanUrls, mergeUrls } from '../urls'

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
