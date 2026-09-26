/**
 * 未保存内容守卫注册表（P0-5）。
 *
 * 为什么需要独立注册表：路由离开、退出登录、切换账号、关闭标签页是**四条不同的触发路径**，
 * 若各自实现提示逻辑，必然出现「某条路径静默丢稿」。这里提供唯一入口：
 * 页面在挂载时注册守卫（返回 `true` 表示可以离开），所有离开动作统一调用 `confirmLeaveAll()`。
 *
 * 约定：守卫**自身负责交互**（例如先尝试保存、失败再弹窗让用户选择），
 * 返回值只表达「是否允许离开」。守卫抛错按「不允许离开」处理（宁可多问一次，不可丢稿）。
 */
export type UnsavedGuard = () => Promise<boolean>

const guards = new Set<UnsavedGuard>()

/** 注册守卫，返回注销函数（组件卸载时调用）。 */
export function registerUnsavedGuard(guard: UnsavedGuard): () => void {
  guards.add(guard)
  return () => {
    guards.delete(guard)
  }
}

/** 依次询问全部守卫：任一拒绝即不允许离开。 */
export async function confirmLeaveAll(): Promise<boolean> {
  for (const guard of Array.from(guards)) {
    try {
      if (!(await guard())) return false
    } catch {
      return false
    }
  }
  return true
}

/** 仅供测试：清空注册表。 */
export function resetUnsavedGuards(): void {
  guards.clear()
}
