/** 富文本图片的凭证自愈（安全整改 批次 E 配套）。
 *
 * 背景：图片改由鉴权端点 `/storage/uploads/images/<name>` 下发，浏览器凭证是登录时下发的
 * HttpOnly Cookie（`vp_img`，Path 限定到该路径，见后端 core/security.py）。该 Cookie 只在
 * 「登录 / 刷新令牌 / 改密 / GET /auth/me」时下发，于是存在空窗：
 * 1. 升级前已打开的页面（当时还没有这个 Cookie）——在下次整页加载前，所有图片都 401；
 * 2. 页面长时间停留、Cookie 与访问令牌同时过期后新渲染出来的图片。
 *
 * 处理：捕获阶段的资源加载失败事件里识别图片路径，静默补一次凭证（GET /auth/me 会续订
 * Cookie）后重试原图一次。只重试一次、凭证获取做节流，避免整页裂图时反复打接口。
 */
import client from '../api/client'

const IMAGE_PATH = '/storage/uploads/images/'
const RETRY_DATASET_KEY = 'vpImgRetried'
/** 凭证补发节流窗口：整页裂图时只打一次 /auth/me */
const HEAL_THROTTLE_MS = 5000

let installed = false
let healing: Promise<unknown> | null = null
let lastHealAt = 0

/** 补发图片凭证：成功即让后续图片请求带上新的 vp_img Cookie。 */
function healCredential(): Promise<unknown> {
  // 未登录时不尝试（避免把登录页上的残留图片请求带进 401 错误页流程）
  if (!localStorage.getItem('access_token')) return Promise.resolve()
  if (healing) return healing
  if (Date.now() - lastHealAt < HEAL_THROTTLE_MS) return Promise.resolve()
  lastHealAt = Date.now()
  healing = client
    .get('/auth/me')
    .catch(() => undefined)
    .finally(() => {
      healing = null
    })
  return healing
}

function isImageElement(target: EventTarget | null): target is HTMLImageElement {
  return typeof HTMLImageElement !== 'undefined' && target instanceof HTMLImageElement
}

/** 是否为本系统富文本图片（同源且路径命中）：站外地址无法受益于 Cookie，不做补发 */
function isGatedImageSrc(src: string): boolean {
  if (!src) return false
  try {
    const url = new URL(src, window.location.href)
    return url.origin === window.location.origin && url.pathname.startsWith(IMAGE_PATH)
  } catch {
    return false
  }
}

export function installImageAuthHealer() {
  if (installed) return
  installed = true
  // 资源加载错误不冒泡，必须用捕获阶段监听 document 才能收到
  document.addEventListener(
    'error',
    (event) => {
      const el = event.target
      if (!isImageElement(el)) return
      const src = el.getAttribute('src') || ''
      if (!isGatedImageSrc(src)) return
      if (el.dataset[RETRY_DATASET_KEY] === '1') return
      el.dataset[RETRY_DATASET_KEY] = '1'
      void healCredential().then(() => {
        // 追加时间戳避开浏览器对同一失败 URL 的复用，重试且仅重试这一次
        el.src = `${src}${src.includes('?') ? '&' : '?'}vp_retry=${Date.now()}`
      })
    },
    true,
  )
}
