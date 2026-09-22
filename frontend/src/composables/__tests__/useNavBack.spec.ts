// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'

import { goBack, resolveBackPath, withRedirect } from '../useNavBack'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

/** 构造最小 route / router 桩：只提供 useNavBack 实际消费的字段 */
function stubRoute(fullPath: string, query: Record<string, unknown> = {}) {
  return { fullPath, query } as unknown as RouteLocationNormalizedLoaded
}

function stubRouter() {
  return {
    back: vi.fn(),
    push: vi.fn().mockResolvedValue(undefined),
    replace: vi.fn().mockResolvedValue(undefined),
  }
}

describe('useNavBack 来源感知返回', () => {
  it('redirect 查询参数优先：push 到来源页（保留前进栈语义）', async () => {
    const router = stubRouter()
    await goBack(router as never, stubRoute('/vulns/1/edit', { redirect: '/testing-plans?plan=5' }), '/vulns')
    expect(router.push).toHaveBeenCalledWith('/testing-plans?plan=5')
    expect(router.back).not.toHaveBeenCalled()
    expect(router.replace).not.toHaveBeenCalled()
  })

  it('无 redirect 时回落浏览器站内历史：router.back()（可前进）', async () => {
    window.history.replaceState({ back: '/vulns', position: 3 }, '')
    const router = stubRouter()
    await goBack(router as never, stubRoute('/vulns/1/edit'), '/vulns')
    expect(router.back).toHaveBeenCalledTimes(1)
    expect(router.push).not.toHaveBeenCalled()
  })

  it('直接粘贴 URL 进入（无 redirect 且无历史）：replace 到安全默认页，不退出站点', async () => {
    window.history.replaceState(null, '')
    const router = stubRouter()
    await goBack(router as never, stubRoute('/vulns/1/edit'), '/vulns')
    expect(router.replace).toHaveBeenCalledWith('/vulns')
  })

  it('历史上一条是登录/错误页时不作为返回目标：走安全默认页', async () => {
    window.history.replaceState({ back: '/login?redirect=/vulns/1/edit', position: 2 }, '')
    const router = stubRouter()
    await goBack(router as never, stubRoute('/vulns/1/edit'), '/vulns')
    expect(router.back).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith('/vulns')
  })

  it('resolveBackPath：redirect 非法（外跳 //host）时被归一化拒绝，回落历史', () => {
    window.history.replaceState({ back: '/vulns', position: 3 }, '')
    const back = resolveBackPath(stubRoute('/vulns/1/edit', { redirect: '//evil.example.com' }))
    expect(back).toEqual({ path: '/vulns', isHistoryBack: true })
  })

  it('withRedirect：把来源 fullPath 写进 redirect 查询参数', () => {
    expect(withRedirect('/vulns/9/edit', '/testing-plans?plan=5&vuln=9')).toEqual({
      path: '/vulns/9/edit',
      query: { redirect: '/testing-plans?plan=5&vuln=9' },
    })
  })
})
