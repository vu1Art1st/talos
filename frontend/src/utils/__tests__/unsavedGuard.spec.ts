import { beforeEach, describe, expect, it, vi } from 'vitest'

import { confirmLeaveAll, registerUnsavedGuard, resetUnsavedGuards } from '../unsavedGuard'

describe('未保存内容守卫注册表', () => {
  beforeEach(() => {
    resetUnsavedGuards()
  })

  it('无守卫时直接放行', async () => {
    expect(await confirmLeaveAll()).toBe(true)
  })

  it('任一守卫拒绝即不允许离开（退出登录与路由离开共用同一判定）', async () => {
    const allow = vi.fn(async () => true)
    const deny = vi.fn(async () => false)
    registerUnsavedGuard(allow)
    registerUnsavedGuard(deny)

    expect(await confirmLeaveAll()).toBe(false)
    expect(allow).toHaveBeenCalledTimes(1)
  })

  it('守卫抛错按「不允许离开」处理（宁可多问一次，不可丢稿）', async () => {
    registerUnsavedGuard(async () => {
      throw new Error('dialog crashed')
    })
    expect(await confirmLeaveAll()).toBe(false)
  })

  it('注销后不再参与判定', async () => {
    const unregister = registerUnsavedGuard(async () => false)
    expect(await confirmLeaveAll()).toBe(false)
    unregister()
    expect(await confirmLeaveAll()).toBe(true)
  })
})
