// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AUTOSAVE_STATE_LABEL, useAutosave, type LeaveChoice } from '../useAutosave'

/** 构造被测实例：默认关闭 beforeunload，避免用例间互相干扰（该行为单独用一组用例覆盖）。 */
function setup(overrides: Partial<Parameters<typeof useAutosave>[0]> = {}) {
  const save = vi.fn(async () => undefined)
  const askOnLeave = vi.fn(async (): Promise<LeaveChoice> => 'stay')
  const autosave = useAutosave({
    save,
    interval: 3000,
    askOnLeave,
    enableBeforeUnload: false,
    ...overrides,
  })
  return { save, askOnLeave, autosave }
}

describe('useAutosave 状态机', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('markDirty → dirty；3 秒防抖后自动保存并回到 saved', async () => {
    const { save, autosave } = setup()
    expect(autosave.state.value).toBe('saved')
    expect(autosave.hasUnsaved.value).toBe(false)

    autosave.markDirty()
    expect(autosave.state.value).toBe('dirty')
    expect(autosave.hasUnsaved.value).toBe(true)
    expect(save).not.toHaveBeenCalled()

    // 防抖窗口内继续编辑只保留一次保存（不会累积多次请求）
    autosave.markDirty()
    await vi.advanceTimersByTimeAsync(2999)
    expect(save).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(save).toHaveBeenCalledTimes(1)
    expect(autosave.state.value).toBe('saved')
    expect(autosave.hasUnsaved.value).toBe(false)
    autosave.dispose()
  })

  it('保存失败 → failed，保留输入并可重试成功', async () => {
    const onError = vi.fn()
    const save = vi.fn()
    save.mockRejectedValueOnce(new Error('network'))
    const { autosave } = setup({ save, onError })

    autosave.markDirty()
    expect(await autosave.saveNow()).toBe(false)
    expect(autosave.state.value).toBe('failed')
    expect(autosave.hasUnsaved.value).toBe(true) // 本地输入仍视为未落库
    expect(AUTOSAVE_STATE_LABEL.failed).toContain('重试')
    expect(onError).toHaveBeenCalledTimes(1)

    save.mockResolvedValueOnce(undefined)
    expect(await autosave.saveNow()).toBe(true)
    expect(autosave.state.value).toBe('saved')
    autosave.dispose()
  })

  it('409 → conflict 且交由 onConflict 处置（不静默覆盖）', async () => {
    const conflict = { response: { status: 409 } }
    const onConflict = vi.fn(async () => undefined)
    const save = vi.fn().mockRejectedValue(conflict)
    const { autosave } = setup({
      save,
      onConflict,
      isConflict: (err) => (err as { response?: { status?: number } }).response?.status === 409,
    })

    autosave.markDirty()
    expect(await autosave.saveNow()).toBe(false)
    expect(onConflict).toHaveBeenCalledTimes(1)
    expect(autosave.state.value).toBe('conflict')
    expect(autosave.hasUnsaved.value).toBe(true)

    // 冲突状态下再次编辑不得触发自动保存（避免与「加载最新」竞态循环）
    autosave.markDirty()
    await vi.advanceTimersByTimeAsync(4000)
    expect(save).toHaveBeenCalledTimes(1)

    // 选择「加载最新」后由调用方 markSaved 复位
    autosave.markSaved()
    expect(autosave.state.value).toBe('saved')
    autosave.dispose()
  })

  it('保存期间继续编辑不会被本次保存的成功回调误标为已保存', async () => {
    let release: (() => void) | undefined
    const save = vi.fn(() => new Promise<void>((resolve) => { release = resolve }))
    const { autosave } = setup({ save })

    autosave.markDirty()
    const pending = autosave.saveNow()
    autosave.markDirty() // 保存进行中继续输入
    release?.()
    await pending

    expect(autosave.state.value).toBe('dirty')
    expect(autosave.hasUnsaved.value).toBe(true)
    autosave.dispose()
  })
})

describe('useAutosave 离页三类分支', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('分支一：无修改直接放行，既不保存也不询问', async () => {
    const { save, askOnLeave, autosave } = setup()
    expect(await autosave.confirmLeave()).toBe(true)
    expect(save).not.toHaveBeenCalled()
    expect(askOnLeave).not.toHaveBeenCalled()
    autosave.dispose()
  })

  it('分支二：有修改先尝试保存，成功即放行（不打扰用户）', async () => {
    const { save, askOnLeave, autosave } = setup()
    autosave.markDirty()
    expect(await autosave.confirmLeave()).toBe(true)
    expect(save).toHaveBeenCalledTimes(1)
    expect(askOnLeave).not.toHaveBeenCalled()
    expect(autosave.state.value).toBe('saved')
    autosave.dispose()
  })

  it('分支三之一：保存失败 → 选择「继续保存」，成功后放行', async () => {
    const save = vi.fn()
    save.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(undefined)
    const { askOnLeave, autosave } = setup({ save })
    askOnLeave.mockResolvedValue('save')

    autosave.markDirty()
    expect(await autosave.confirmLeave()).toBe(true)
    expect(askOnLeave).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledTimes(2)
    expect(autosave.state.value).toBe('saved')
    autosave.dispose()
  })

  it('分支三之二：保存仍失败 → 选择「继续保存」后仍失败则留在当前页', async () => {
    const save = vi.fn().mockRejectedValue(new Error('boom'))
    const { askOnLeave, autosave } = setup({ save })
    askOnLeave.mockResolvedValue('save')

    autosave.markDirty()
    expect(await autosave.confirmLeave()).toBe(false)
    expect(autosave.state.value).toBe('failed')
    expect(autosave.hasUnsaved.value).toBe(true)
    autosave.dispose()
  })

  it('分支三之三：选择「放弃修改」放行，且同一流程内不再重复询问', async () => {
    const save = vi.fn().mockRejectedValue(new Error('boom'))
    const { askOnLeave, autosave } = setup({ save })
    askOnLeave.mockResolvedValue('discard')

    autosave.markDirty()
    expect(await autosave.confirmLeave()).toBe(true)
    expect(askOnLeave).toHaveBeenCalledTimes(1)
    // 已确认放弃：后续（如路由守卫与退出登录连着触发）直接放行
    expect(await autosave.confirmLeave()).toBe(true)
    expect(askOnLeave).toHaveBeenCalledTimes(1)
    autosave.dispose()
  })

  it('分支三之四：选择「留在当前页」拒绝离开', async () => {
    const save = vi.fn().mockRejectedValue(new Error('boom'))
    const { askOnLeave, autosave } = setup({ save })
    askOnLeave.mockResolvedValue('stay')

    autosave.markDirty()
    expect(await autosave.confirmLeave()).toBe(false)
    expect(autosave.hasUnsaved.value).toBe(true)
    // 再次离页仍会询问（未被静默放弃）
    expect(await autosave.confirmLeave()).toBe(false)
    expect(askOnLeave).toHaveBeenCalledTimes(2)
    autosave.dispose()
  })
})

describe('useAutosave beforeunload', () => {
  it('仅在确有未保存或保存失败内容时触发原生确认', async () => {
    const save = vi.fn(async () => undefined)
    const autosave = useAutosave({ save })
    const fire = () => {
      const event = new Event('beforeunload', { cancelable: true })
      window.dispatchEvent(event)
      return event.defaultPrevented
    }

    expect(fire()).toBe(false) // 已保存：不拦截
    autosave.markDirty()
    expect(fire()).toBe(true) // 有未保存修改：拦截
    await autosave.saveNow()
    expect(fire()).toBe(false) // 保存成功：不再拦截

    // 保存失败同样必须拦截（否则关标签页即丢稿）
    const failing = useAutosave({ save: vi.fn().mockRejectedValue(new Error('x')) })
    failing.markDirty()
    await failing.saveNow()
    expect(failing.state.value).toBe('failed')
    expect(fire()).toBe(true)

    autosave.dispose()
    failing.dispose()
    expect(fire()).toBe(false)
    failing.dispose()
  })
})
