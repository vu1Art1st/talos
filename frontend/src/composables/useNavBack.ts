import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import { normalizeRedirect } from '../utils/errorPage'

/**
 * 来源感知返回（回退 UX 统一入口）：
 * 三层兜底 —— 显式 `redirect` 查询参数 > 浏览器站内历史（vue-router 写入 history.state.back）> 调用方安全默认页。
 * 任何一层都只接受站内路径（normalizeRedirect 拒绝 `//host` 等），保证「返回」永远不会把用户退回站外。
 */

interface BackTarget {
  path: string
  /** true：来自浏览器历史，走 router.back()（保留前进栈）；false：来自 redirect 参数，走 push */
  isHistoryBack: boolean
}

/** 判断是否为不应作为返回目标的过渡页（登录 / 错误页） */
function isTransientPath(path: string): boolean {
  return path.startsWith('/login') || path.startsWith('/error')
}

/**
 * 解析当前页的返回目标：
 * 1. `route.query.redirect`（跳转时显式携带的来源 fullPath）；
 * 2. vue-router 在 history.state.back 记录的站内上一条（覆盖「无 redirect 参数的常规跳转」，
 *    如列表 → 编辑、详情 → 编辑）；直接粘贴 URL 进入时为 null。
 */
export function resolveBackPath(route: RouteLocationNormalizedLoaded): BackTarget | null {
  // query 在最小 route 桩（单测）下可能缺失，取不到来源时继续走历史兜底
  const explicit = normalizeRedirect(route.query?.redirect)
  if (explicit) return { path: explicit, isHistoryBack: false }

  // history.state 由 vue-router 维护；jsdom / 首次进入时可能为 null
  const state = window.history?.state as { back?: unknown } | null
  const back = typeof state?.back === 'string' ? state.back : ''
  if (back && back !== route.fullPath && !isTransientPath(back)) {
    return { path: back, isHistoryBack: true }
  }
  return null
}

/**
 * 安全返回：有站内历史/来源则回退，否则 replace 到调用方给定的默认页（再兜底到工作台）。
 * 用于「取消 / 返回」类按钮，替代裸 router.back()。
 */
export async function goBack(
  router: Router,
  route: RouteLocationNormalizedLoaded,
  fallback = '/dashboard',
): Promise<void> {
  const back = resolveBackPath(route)
  if (back?.isHistoryBack) {
    router.back()
    return
  }
  if (back) {
    await router.push(back.path)
    return
  }
  await router.replace(normalizeRedirect(fallback, '/dashboard') || '/dashboard')
}

/** 构造带来源的跳转目标：跳到 path 的同时把 from（来源页 fullPath）写进 redirect 参数 */
export function withRedirect(path: string, from: string): { path: string; query: { redirect: string } } {
  return { path, query: { redirect: from } }
}
