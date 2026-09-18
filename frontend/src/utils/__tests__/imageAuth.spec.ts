// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

/** 共享的打桩客户端：所有测试都断言同一个 get，故在模块重置之外持有它 */
const get = vi.fn()
vi.mock('../../api/client', () => ({
  default: { get: (...args: unknown[]) => get(...args) },
}))

import { installImageAuthHealer } from '../imageAuth'

/** 用例间推进假时钟用（补发节流基于 Date.now，需保证跨过节流窗口） */
let clockOffset = 0

/** 触发一次图片加载失败事件（资源错误不冒泡，由捕获阶段监听 document 收到；元素须在文档树内） */
function fireImageError(src: string) {
  const img = document.createElement('img')
  img.setAttribute('src', src)
  document.body.appendChild(img)
  img.dispatchEvent(new Event('error', { bubbles: false }))
  return img
}

describe('installImageAuthHealer', () => {
  // 与生产一致：监听器在应用启动时只安装一次
  beforeAll(() => {
    installImageAuthHealer()
    installImageAuthHealer() // 幂等：重复安装不应叠加监听器
  })

  beforeEach(() => {
    // 只伪造 Date（补发节流基于 Date.now），保留真实定时器以便 vi.waitFor 正常工作；
    // useFakeTimers 会把假时钟重置回真实时间，故显式前移，确保跨过上一个用例的节流窗口
    vi.useFakeTimers({ toFake: ['Date'] })
    clockOffset += 60_000
    vi.setSystemTime(Date.now() + clockOffset)
    get.mockReset()
    get.mockResolvedValue({ data: {} })
    localStorage.setItem('access_token', 'tok')
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  it('图片失败时补一次凭证并带时间戳重试一次', async () => {
    const img = fireImageError('/storage/uploads/images/aa.png')
    expect(get).toHaveBeenCalledWith('/auth/me')
    await vi.waitFor(() => {
      expect(img.getAttribute('src')).toMatch(/^\/storage\/uploads\/images\/aa\.png\?vp_retry=\d+$/)
    })
    // 重试后再次失败不再补发凭证（避免无限循环）
    const calls = get.mock.calls.length
    img.dispatchEvent(new Event('error', { bubbles: false }))
    expect(get.mock.calls.length).toBe(calls)
  })

  it('同一窗口内多张裂图只补发一次凭证', () => {
    fireImageError('/storage/uploads/images/c1.png')
    fireImageError('/storage/uploads/images/c2.png')
    fireImageError('/storage/uploads/images/c3.png')
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('非图片资源与站外图片不触发补发', () => {
    const script = document.createElement('script')
    document.body.appendChild(script)
    script.dispatchEvent(new Event('error', { bubbles: false }))
    fireImageError('https://example.com/storage/uploads/images/aa.png')
    fireImageError('/logo.svg')
    expect(get).not.toHaveBeenCalled()
  })

  it('未登录时不补发凭证（避免把登录页带进 401 错误页）', () => {
    localStorage.removeItem('access_token')
    fireImageError('/storage/uploads/images/bb.png')
    expect(get).not.toHaveBeenCalled()
  })
})
