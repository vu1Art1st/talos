import { describe, expect, it } from 'vitest'
import {
  FALLBACK_CODE,
  getErrorMeta,
  normalizeCode,
  normalizeRedirect,
  resolveErrorPolicy,
  resolvePageCode,
} from '../errorPage'

describe('errorPage 元数据', () => {
  it('专属文案页覆盖 400/401/403/404/500/502/503/504', () => {
    for (const code of ['400', '401', '403', '404', '500', '502', '503', '504']) {
      const meta = getErrorMeta(code)
      expect(meta.code).toBe(code)
      expect(meta.title).toBeTruthy()
      expect(meta.desc).toBeTruthy()
      expect(meta.hint).toBeTruthy()
      expect(meta.chip).toContain(code)
      expect(meta.icon).toMatch(/^#i-\d{3}$/)
      expect(meta.actions.length).toBeGreaterThan(0)
      expect(meta.actions.filter((a) => a.primary)).toHaveLength(1)
    }
  })

  it('未登记的 4xx / 5xx 走通用模板，不影响页面可用性', () => {
    const four = getErrorMeta('418')
    expect(four.code).toBe('418')
    expect(four.chip).toContain('418')
    expect(four.title).toBe('请求未能完成')
    expect(four.icon).toBe('#i-400')

    for (const code of ['507', '599']) {
      const five = getErrorMeta(code)
      expect(five.chip).toContain(code)
      expect(five.title).toBe('服务出现异常')
      expect(five.icon).toBe('#i-500')
      expect(five.actions.some((a) => a.act === 'reload')).toBe(true)
    }
  })

  it('非法状态码归一化为 404 兜底页', () => {
    for (const raw of ['abc', '', '99', '1000', '200', '301', undefined, null, {}, '五十']) {
      expect(getErrorMeta(raw).code).toBe(FALLBACK_CODE)
      expect(getErrorMeta(raw).title).toBe('哎呀，页面走丢了')
    }
    // 数字入参同样可解析
    expect(getErrorMeta(500).code).toBe('500')
  })

  it('normalizeCode 仅接受 4xx / 5xx 三位码', () => {
    expect(normalizeCode('502')).toBe('502')
    expect(normalizeCode('  404 ')).toBe('404')
    expect(normalizeCode('0404')).toBe('404')
    expect(normalizeCode('600')).toBe('404')
  })
})

describe('errorPage 跳转地址归一化', () => {
  it('只接受站内相对路径', () => {
    expect(normalizeRedirect('/vulns/1?tab=2')).toBe('/vulns/1?tab=2')
    expect(normalizeRedirect('/')).toBe('/')
  })

  it('拒绝协议外跳 / 绝对地址 / 非字符串', () => {
    expect(normalizeRedirect('//evil.example.com')).toBe('')
    expect(normalizeRedirect('/\\evil')).toBe('')
    expect(normalizeRedirect('https://evil.example.com')).toBe('')
    expect(normalizeRedirect('javascript:alert(1)')).toBe('')
    expect(normalizeRedirect(['/x'])).toBe('')
    expect(normalizeRedirect(undefined, '/dashboard')).toBe('/dashboard')
  })
})

describe('errorPage 响应策略', () => {
  const policy = (status?: number, method?: string, skipErrorPage?: boolean) =>
    resolveErrorPolicy({ status, method, skipErrorPage })

  it('登录态失效一律进 401 页（不可豁免）', () => {
    expect(policy(401)).toBe('page')
    expect(policy(401, 'GET', true)).toBe('page')
  })

  it('403 按请求方法分档：页面级读取跳页，行内写操作只提示', () => {
    expect(policy(403, 'GET')).toBe('page')
    expect(policy(403, 'get')).toBe('page')
    expect(policy(403, 'HEAD')).toBe('page')
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
      expect(policy(403, method)).toBe('toast')
    }
  })

  it('5xx 跳错误页，豁免请求降级为轻提示', () => {
    for (const status of [500, 502, 503, 504, 507]) {
      expect(policy(status)).toBe('page')
      expect(policy(status, 'GET', true)).toBe('toast')
    }
  })

  it('可就地修正的业务错误保持轻提示', () => {
    for (const status of [400, 404, 405, 406, 410, 413, 415, 422, 429, 418]) {
      expect(policy(status)).toBe('toast')
    }
  })

  it('409 保持静默（冲突文案由调用方给出）', () => {
    expect(policy(409)).toBe('silent')
  })

  it('无响应（断网 / 超时）不清屏', () => {
    expect(policy(undefined)).toBe('toast')
  })

  it('resolvePageCode 兜底非法状态码', () => {
    expect(resolvePageCode(502)).toBe('502')
    expect(resolvePageCode(401)).toBe('401')
    expect(resolvePageCode(999)).toBe('500')
  })
})
