import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'
import { normalizeRedirect, resolveErrorPolicy, resolvePageCode } from '../utils/errorPage'
import type { ApiErrorShape } from '../types'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /**
     * 错误页豁免：置 true 时该请求失败不触发全屏错误页（仅保留轻提示）。
     * 用于后台轮询等场景，避免编辑中途被错误页清屏。401（登录态失效）不受此豁免影响。
     */
    meta?: { skipErrorPage?: boolean }
  }
}

const client = axios.create({ baseURL: '/api/v1', timeout: 30000 })

let refreshing: Promise<string | null> | null = null
/** 正在跳转的错误码：并发请求同时失败时只跳一次 */
let redirecting: string | null = null

async function refreshToken(): Promise<string | null> {
  const refresh = localStorage.getItem('refresh_token')
  if (!refresh) return null
  try {
    const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refresh })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    return data.access_token
  } catch {
    return null
  }
}

function tokenExpiresIn(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return typeof payload.exp === 'number' ? payload.exp - Date.now() / 1000 : null
  } catch {
    return null
  }
}

function clearCredentials() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

function toastError(error: ApiErrorShape) {
  const msg = error?.response?.data?.detail || error?.message || '请求失败'
  ElMessage.error(typeof msg === 'string' ? msg : '请求失败')
}

/** 跳错误页（幂等）：当前已是同一错误页、或同码跳转正在进行时不重复导航 */
function goErrorPage(status: number, query: Record<string, string> = {}) {
  const code = resolvePageCode(status)
  const current = router.currentRoute.value
  if (current.name === 'error' && String(current.params.code) === code) return
  if (redirecting === code) return
  redirecting = code
  void router
    .replace({ name: 'error', params: { code }, query })
    .catch(() => undefined)
    .finally(() => {
      redirecting = null
    })
}

client.interceptors.request.use(async (config) => {
  let token = localStorage.getItem('access_token')
  // 临期主动刷新：距过期不足 5 分钟先续期（单飞去重），保证活跃用户的空闲窗口持续顺延
  const expiresIn = token ? tokenExpiresIn(token) : null
  if (token && expiresIn !== null && expiresIn < 300) {
    refreshing = refreshing ?? refreshToken()
    token = await refreshing
    refreshing = null
    if (!token) token = localStorage.getItem('access_token')
  }
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (resp) => resp,
  async (error) => {
    const { response, config } = error
    const status: number | undefined = response?.status
    const method = String(config?.method || 'get').toUpperCase()
    const url = typeof config?.url === 'string' ? config.url : ''
    // 登录 / 刷新接口自身的 401 是「凭证错误」的业务语义，须就地提示，不进错误页
    const isAuthPath = url.includes('/auth/login') || url.includes('/auth/refresh')

    if (status === 401 && !isAuthPath) {
      // 先静默刷新并重放；刷新失败（或重放后仍 401）说明登录态已彻底失效
      if (!config._retried) {
        config._retried = true
        refreshing = refreshing ?? refreshToken()
        const token = await refreshing
        refreshing = null
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
          return client(config)
        }
      }
      clearCredentials()
      // 保留原访问意图：401 页「重新登录」后回到该页面
      goErrorPage(401, { redirect: normalizeRedirect(router.currentRoute.value.fullPath) })
      return Promise.reject(error)
    }

    // 未改密账号的 403（服务端拦截，见 core/deps.py::_enforce_password_change）：
    // 由不可关闭的改密弹框接管，静默处理避免整页接口集体弹提示刷屏
    if (status === 403 && response?.headers?.['x-must-change-password'] === '1') {
      return Promise.reject(error)
    }

    const policy = resolveErrorPolicy({ status, method, skipErrorPage: config?.meta?.skipErrorPage === true })
    if (policy === 'page' && status != null) {
      goErrorPage(status, { from: normalizeRedirect(router.currentRoute.value.fullPath) })
    } else if (policy === 'toast') {
      toastError(error)
    }
    return Promise.reject(error)
  },
)

export default client
