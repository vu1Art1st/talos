import { onBeforeUnmount, watch, type Ref } from 'vue'

export interface UseClickOutsideOptions {
  /**
   * 命中这些选择器的元素视为「内部点击」。
   *
   * Element Plus 的 `el-select` / `el-date-picker` / `el-popconfirm` 浮层默认 teleport 到 body，
   * 不在容器 DOM 内 —— 必须按选择器显式放行，否则点开下拉就会把外层浮层一起关掉
   * （这正是聚合筛选面板当初改用 `trigger="manual"` 的原因）。
   */
  ignoreSelectors?: string[]
  /** Esc 是否同样触发收回（默认 true） */
  escape?: boolean
}

type ElementRef = Ref<HTMLElement | null | undefined>

/**
 * 浮层失焦自动收回：点击目标元素之外（或按 Esc）时执行 `onOutside`。
 *
 * 本项目未引入 `v-click-outside` 指令，浮层默认依赖 Element Plus 内建 trigger 行为；
 * `trigger="manual"` 的浮层（如工单列表的聚合筛选面板）不享受内建的「点击外部关闭」，
 * 需用本函数补回该能力。
 *
 * 只在 `enabled` 为真时挂监听，避免全局常驻；组件卸载时必定解绑。
 */
export function useClickOutside(
  targets: ElementRef[],
  enabled: Ref<boolean>,
  onOutside: () => void,
  options: UseClickOutsideOptions = {},
): void {
  const { ignoreSelectors = [], escape = true } = options

  function isInside(target: EventTarget | null): boolean {
    if (!(target instanceof Element)) return false
    if (targets.some((el) => el.value?.contains(target))) return true
    return ignoreSelectors.some((selector) => target.closest(selector) !== null)
  }

  function onMouseDown(event: MouseEvent) {
    if (!isInside(event.target)) onOutside()
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') onOutside()
  }

  function bind(active: boolean) {
    if (!active) {
      document.removeEventListener('mousedown', onMouseDown, true)
      document.removeEventListener('keydown', onKeydown)
      return
    }
    document.addEventListener('mousedown', onMouseDown, true)
    if (escape) document.addEventListener('keydown', onKeydown)
  }

  watch(enabled, bind, { immediate: true })
  onBeforeUnmount(() => bind(false))
}
