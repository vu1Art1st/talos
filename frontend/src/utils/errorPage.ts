/**
 * 错误页元数据与响应策略（纯逻辑模块）。
 *
 * 设计约束：本模块**禁止 import router / stores / api**，否则会形成
 * `router/index.ts → views/ErrorPage.vue → api/client.ts → utils/errorPage.ts → router` 循环依赖。
 * 一切导航动作由调用方（`api/client.ts` 拦截器、`views/ErrorPage.vue`）执行。
 *
 * 文案与图标基准：`design-demos/demo-error-pages.html` 的状态码表（本地设计稿，不入库）。
 */

/** 错误页按钮行为 */
export type ErrorActionKind = 'back' | 'home' | 'login' | 'reload'

export interface ErrorAction {
  label: string
  /** 内联 SVG sprite 的 symbol id（见 views/ErrorPage.vue） */
  icon: string
  act: ErrorActionKind
  primary?: boolean
}

export interface ErrorPageMeta {
  code: string
  chip: string
  title: string
  desc: string
  icon: string
  actions: ErrorAction[]
  hint: string
}

/** 非法状态码的兜底页面 */
export const FALLBACK_CODE = '404'

const back = (primary = false): ErrorAction => ({ label: '返回上一页', icon: '#i-back', act: 'back', primary })
const home = (primary = false): ErrorAction => ({ label: '返回首页', icon: '#i-home', act: 'home', primary })
const reload: ErrorAction = { label: '重新加载', icon: '#i-refresh', act: 'reload', primary: true }
const login: ErrorAction = { label: '重新登录', icon: '#i-login', act: 'login', primary: true }

type ErrorPageMetaBody = Omit<ErrorPageMeta, 'code'>

/** 专属文案页：系统实际会产出的 4xx / 5xx（含 nginx 侧的 502/503/504） */
const PAGES: Record<string, ErrorPageMetaBody> = {
  '400': {
    chip: 'HTTP 400 · 请求无效',
    title: '请求无法被识别',
    desc: '提交的请求格式有误或参数不完整，服务器无法处理。请返回上一步检查填写内容后重新提交。',
    icon: '#i-400',
    actions: [back(true), home()],
    hint: '若为接口调用，请核对请求参数与格式。',
  },
  '401': {
    chip: 'HTTP 401 · 身份未验证',
    title: '登录状态已失效',
    desc: '你的登录凭证已过期或尚未登录，无法访问该页面。请重新登录，登录后会自动返回原页面。',
    icon: '#i-401',
    actions: [login, home()],
    hint: '登录成功后会回到你原本访问的页面。',
  },
  '403': {
    chip: 'HTTP 403 · 无访问权限',
    title: '你没有访问权限',
    desc: '当前账号无权访问该页面或资源。如确需使用，请联系管理员为账号开通相应权限。',
    icon: '#i-403',
    actions: [home(true), back()],
    hint: '权限有误请联系管理员核对角色与权限组。',
  },
  '404': {
    chip: 'HTTP 404 · 页面未找到',
    title: '哎呀，页面走丢了',
    desc: '你访问的页面不存在，可能已被移动或删除，也可能是链接地址输入有误，请核对后再试。',
    icon: '#i-404',
    actions: [home(true), back()],
    hint: '仍无法解决？请联系管理员核对访问地址。',
  },
  '500': {
    chip: 'HTTP 500 · 服务器内部错误',
    title: '服务器开小差了',
    desc: '服务在处理这次请求时发生异常，通常与你的操作无关。请稍后重试，或联系管理员。',
    icon: '#i-500',
    actions: [reload, home()],
    hint: '反馈时请附上页面地址与操作时间，便于定位。',
  },
  '502': {
    chip: 'HTTP 502 · 网关错误',
    title: '服务暂时不可用',
    desc: '网关暂时无法连接到上游服务，可能是服务正在重启或短暂过载。请稍后刷新重试。',
    icon: '#i-502',
    actions: [reload, home()],
    hint: '若长时间未恢复，请联系管理员确认服务状态。',
  },
  '503': {
    chip: 'HTTP 503 · 服务不可用',
    title: '服务正在维护中',
    desc: '服务当前不可用，可能正在重启或处于维护状态。请稍后刷新重试。',
    icon: '#i-502',
    actions: [reload, home()],
    hint: '若长时间未恢复，请联系管理员确认服务状态。',
  },
  '504': {
    chip: 'HTTP 504 · 网关超时',
    title: '请求响应超时',
    desc: '上游服务在规定时间内未返回结果，可能是任务繁忙或网络拥塞。请稍后刷新重试。',
    icon: '#i-502',
    actions: [reload, home()],
    hint: '若长时间未恢复，请联系管理员确认服务状态。',
  },
}

/** 未登记状态码的通用模板：按首位数字归属 4xx / 5xx，保证任意三位码都有页面 */
function generic4xx(code: string): ErrorPageMetaBody {
  return {
    chip: `HTTP ${code} · 请求未能完成`,
    title: '请求未能完成',
    desc: '服务器拒绝了本次请求，可能是参数、状态或资源已发生变化。请返回上一步核对后重试。',
    icon: '#i-400',
    actions: [back(true), home()],
    hint: '若反复出现，请联系管理员并提供页面地址与操作时间。',
  }
}

function generic5xx(code: string): ErrorPageMetaBody {
  return {
    chip: `HTTP ${code} · 服务异常`,
    title: '服务出现异常',
    desc: '服务在处理这次请求时发生异常，通常与你的操作无关。请稍后重试，或联系管理员。',
    icon: '#i-500',
    actions: [reload, home()],
    hint: '反馈时请附上页面地址与操作时间，便于定位。',
  }
}

/** 归一化状态码：仅接受 4xx / 5xx 三位码，其余（缺省、非数字、2xx/3xx、超长）一律兜底 404 */
export function normalizeCode(raw: unknown): string {
  const value = String(raw ?? '').trim()
  return /^[45]\d{2}$/.test(value) ? value : FALLBACK_CODE
}

/** 按状态码解析页面元数据（未登记码走通用模板，永不抛错） */
export function getErrorMeta(raw: unknown): ErrorPageMeta {
  const code = normalizeCode(raw)
  const hit = PAGES[code]
  if (hit) return { code, ...hit }
  return { code, ...(code.startsWith('5') ? generic5xx(code) : generic4xx(code)) }
}

/**
 * 归一化站内跳转地址（`from` / `redirect` 查询参数）：
 * 只接受以单个 `/` 开头的相对路径，拒绝 `//host`、`/\host` 与任意 scheme，避免被当作跳转跳板。
 */
export function normalizeRedirect(raw: unknown, fallback = ''): string {
  const value = typeof raw === 'string' ? raw.trim() : ''
  if (value === '/') return value
  return /^\/[^/\\]/.test(value) ? value : fallback
}

/** 响应处理策略：page=全屏错误页 / toast=轻提示 / silent=静默（由调用方自行提示） */
export type ErrorPolicy = 'page' | 'toast' | 'silent'

export interface PolicyInput {
  /** HTTP 状态码；缺省表示网络中断、请求取消等无响应场景 */
  status?: number
  /** 请求方法，用于 403 分档（页面级读取 vs 行内写操作） */
  method?: string
  /** 请求级豁免：后台轮询等场景不触发清屏 */
  skipErrorPage?: boolean
}

/** 保持轻提示：多为可就地修正的参数 / 资源类错误 */
const TOAST_CODES = new Set([400, 404, 405, 406, 410, 413, 415, 422, 429])
/** 保持静默：冲突类文案由调用方负责（如「报告已被他人修改，请刷新后重试」） */
const SILENT_CODES = new Set([409])

/**
 * 状态码 → 处理策略：
 * - 401：登录态失效不可豁免，一律进 401 页（登录接口自身的 401 属凭证错误，由拦截器另行处理）
 * - 403：GET/HEAD 这类页面级读取进 403 页；POST/PUT/PATCH/DELETE 等行内操作只提示，保留用户上下文
 * - 5xx：服务端故障，全屏告知并提供「重新加载」
 * - 无响应（断网 / 超时）：仅提示，避免离线时反复跳页
 */
export function resolveErrorPolicy({ status, method = 'GET', skipErrorPage }: PolicyInput): ErrorPolicy {
  if (status == null) return 'toast'
  if (SILENT_CODES.has(status)) return 'silent'
  if (TOAST_CODES.has(status)) return 'toast'
  if (status === 401) return 'page'
  const pageEligible =
    status === 403 ? ['GET', 'HEAD'].includes(String(method).toUpperCase()) : status >= 500
  if (!pageEligible) return 'toast'
  return skipErrorPage ? 'toast' : 'page'
}

/** 判定需要跳页时，解析目标路由状态码（非法值兜底 500，保证错误页本身可用） */
export function resolvePageCode(status: number): string {
  const value = String(status)
  return /^[45]\d{2}$/.test(value) ? value : '500'
}
