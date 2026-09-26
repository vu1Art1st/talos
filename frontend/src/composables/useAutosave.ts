/**
 * 自动保存状态机（P0-5 报告防丢稿）。
 *
 * 状态：`saved / dirty / saving / failed / conflict`。抽取成 composable 的原因：
 * 离页保护（路由离开、退出登录、关闭标签页）与自动保存必须共享**同一个**状态判断，
 * 否则「刚触发 3 秒防抖但还没保存就离开」必然丢稿。
 *
 * 关键设计：
 * - `hasUnsaved` 覆盖 `dirty / saving / failed / conflict`：保存中或保存失败也属于「未落库」，
 *   关闭标签页同样需要原生确认（`beforeunload`）。
 * - 保存期间用户继续编辑（`dirtyWhileSaving`）不会被本次保存的成功回调误标为 `saved`。
 * - 409 冲突**不静默覆盖**：进入 `conflict` 状态并把处置权交给调用方（加载最新 / 继续编辑）。
 * - `confirmLeave()` 是四条离开路径共用的唯一判定入口，三类分支（无需保存 / 保存成功 /
 *   保存失败后由用户选择「继续保存 / 放弃修改 / 留在当前页」）均在此实现，便于单测覆盖。
 */
import { computed, getCurrentInstance, onBeforeUnmount, ref } from 'vue'
import { ElMessageBox } from 'element-plus'

export type AutosaveState = 'saved' | 'dirty' | 'saving' | 'failed' | 'conflict'

/** 离开确认结果：继续保存 / 放弃修改 / 留在当前页 */
export type LeaveChoice = 'save' | 'discard' | 'stay'

export const AUTOSAVE_STATE_LABEL: Record<AutosaveState, string> = {
  saved: '已保存',
  dirty: '有未保存修改',
  saving: '保存中…',
  failed: '保存失败，请重试',
  conflict: '版本冲突，请先处理',
}

export interface UseAutosaveOptions {
  /** 实际保存动作（由调用方提供 HTTP 细节）；抛错即视为保存失败 */
  save: () => Promise<void>
  /** 防抖间隔（毫秒），默认 3000（既有报告编辑器口径） */
  interval?: number
  /** 判定响应是否为版本冲突（409） */
  isConflict?: (err: unknown) => boolean
  /** 冲突处置：由调用方弹窗决定「加载最新 / 继续编辑」 */
  onConflict?: (err: unknown) => Promise<void> | void
  /** 保存失败回调（非 409）；错误提示仍由 axios 拦截器统一承担 */
  onError?: (err: unknown) => void
  /** 离开确认弹窗（默认实现用 ElMessageBox；测试可注入） */
  askOnLeave?: () => Promise<LeaveChoice>
  /** 是否注册 beforeunload（默认 true；测试可关闭） */
  enableBeforeUnload?: boolean
}

async function defaultAskOnLeave(): Promise<LeaveChoice> {
  try {
    await ElMessageBox.confirm(
      '当前报告有未保存的修改，离开将丢失这些内容。',
      '未保存的修改',
      {
        confirmButtonText: '继续保存',
        cancelButtonText: '放弃修改',
        distinguishCancelAndClose: true,
        type: 'warning',
      },
    )
    return 'save'
  } catch (action) {
    // distinguishCancelAndClose=true 时：cancel = 放弃修改，close(X/ESC) = 留在当前页
    return action === 'cancel' ? 'discard' : 'stay'
  }
}

export function useAutosave(options: UseAutosaveOptions) {
  const interval = options.interval ?? 3000
  const state = ref<AutosaveState>('saved')
  let timer: ReturnType<typeof setTimeout> | undefined
  let dirtyWhileSaving = false
  /** 用户已明确「放弃修改」：同一次离开流程内不再重复询问 */
  let discardConfirmed = false

  const saving = computed(() => state.value === 'saving')
  const hasUnsaved = computed(() => state.value !== 'saved')

  function clearTimer() {
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
  }

  function schedule() {
    clearTimer()
    timer = setTimeout(() => {
      timer = undefined
      void saveNow()
    }, interval)
  }

  /** 标记内容已修改：进入 dirty 并启动 3 秒防抖自动保存。 */
  function markDirty() {
    discardConfirmed = false
    if (state.value === 'saving') {
      dirtyWhileSaving = true // 本次保存的结果不能代表最新内容
      return
    }
    if (state.value === 'conflict') {
      // 冲突未处理前不再自动重试，避免与「加载最新」竞态；用户再次编辑仍可手动保存
      state.value = 'conflict'
      return
    }
    state.value = 'dirty'
    schedule()
  }

  /** 立即保存；返回是否保存成功（失败/冲突均返回 false，状态已同步更新）。 */
  async function saveNow(): Promise<boolean> {
    clearTimer()
    if (state.value === 'saving') return false
    const previous = state.value
    state.value = 'saving'
    dirtyWhileSaving = false
    try {
      await options.save()
    } catch (err) {
      if (options.isConflict?.(err)) {
        state.value = 'conflict'
        await options.onConflict?.(err)
        return false
      }
      state.value = 'failed'
      options.onError?.(err)
      return false
    }
    if (dirtyWhileSaving) {
      state.value = 'dirty'
      schedule()
      return true
    }
    state.value = 'saved'
    if (previous === 'dirty' || previous === 'failed') discardConfirmed = false
    return true
  }

  /** 服务端内容已（重新）载入本地：视为已保存。 */
  function markSaved() {
    clearTimer()
    dirtyWhileSaving = false
    discardConfirmed = false
    state.value = 'saved'
  }

  /**
   * 离页统一判定：无修改直接放行；有修改先尝试保存，失败后询问用户。
   * 返回 `true` 表示允许离开（调用方据此继续导航 / 登出）。
   */
  async function confirmLeave(): Promise<boolean> {
    if (discardConfirmed || !hasUnsaved.value) return true
    if (await saveNow()) return true
    const choice = await (options.askOnLeave ?? defaultAskOnLeave)()
    if (choice === 'save') return await saveNow()
    if (choice === 'discard') {
      discardConfirmed = true
      clearTimer()
      state.value = 'saved' // 本地修改将被丢弃，不再拦截后续离开
      return true
    }
    return false
  }

  function onBeforeUnload(event: BeforeUnloadEvent) {
    if (!hasUnsaved.value) return
    event.preventDefault()
    event.returnValue = ''
  }

  function dispose() {
    clearTimer()
    if (options.enableBeforeUnload !== false) {
      window.removeEventListener('beforeunload', onBeforeUnload)
    }
  }

  if (options.enableBeforeUnload !== false) {
    window.addEventListener('beforeunload', onBeforeUnload)
  }
  if (getCurrentInstance()) onBeforeUnmount(dispose)

  return { state, saving, hasUnsaved, markDirty, saveNow, markSaved, confirmLeave, dispose }
}
