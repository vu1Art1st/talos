/**
 * URL 列表工具：工单「被测系统URL」等场景的多值合并。
 */

/** URL 条目：字符串，或资产的 `{ url, tag }` 对象；`tag` 等附加字段不参与归一化，故以索引签名放行 */
export type UrlLike = string | { url?: string; [key: string]: unknown }

/** 提取并归一化单个 URL：兼容字符串与 { url } 对象（资产 public_urls 条目），trim 后过滤空值 */
const normalize = (u: UrlLike): string =>
  (typeof u === 'string' ? u : (u?.url ?? '')).trim()

/** 去重保序合并 URL 列表：新增项追加在既有列表之后，已存在的（trim 后相同）不重复带入 */
export function mergeUrls(existing: UrlLike[], added: UrlLike[]): string[] {
  const out: string[] = []
  for (const u of [...(existing ?? []), ...(added ?? [])]) {
    const v = normalize(u)
    if (v && !out.includes(v)) out.push(v)
  }
  return out
}

/** 提交前清洗：trim、去空、去重保序 */
export function cleanUrls(urls: UrlLike[]): string[] {
  return mergeUrls([], urls ?? [])
}

/** 资产的全部 URL（公网 {url,tag} 对象 + 内网字符串），用于自动带出 */
export function assetUrls(asset: { public_urls?: UrlLike[]; internal_urls?: UrlLike[] } | null | undefined): string[] {
  if (!asset) return []
  return mergeUrls(asset.public_urls ?? [], asset.internal_urls ?? [])
}

// ---------- 影响URL（漏洞多值字段，后端以「换行分隔单字段」存储） ----------

/** 上限与后端 `app/schemas/common.py` 保持一致，改动须两端同步 */
export const AFFECTED_URL_MAX_COUNT = 100
export const AFFECTED_URL_ITEM_MAX_LENGTH = 2048

/** 分隔符：换行（LF/CRLF）与中英文分号（粘贴多行 / 分号文本时切分） */
const AFFECTED_URL_SPLIT_RE = /[\r\n;；]+/

/** 影响URL 文本 → 多值列表：按换行/分号切分，逐条 trim、去空、去重保序 */
export function parseAffectedUrl(raw: string | null | undefined): string[] {
  return cleanUrls((raw ?? '').split(AFFECTED_URL_SPLIT_RE))
}

/** 多值列表 → 后端单字段口径（换行分隔）；已 trim、去空、去重保序 */
export function joinAffectedUrl(urls: UrlLike[]): string {
  return cleanUrls(urls ?? []).join('\n')
}

export interface AffectedUrlValidation {
  ok: boolean
  /** 不合规时的可读文案（与后端 `normalize_affected_url` 文案一致，两端呈现统一） */
  message: string
  /** 不合规条目下标（0 基），供行内高亮 */
  invalidIndexes: number[]
}

/** 条目是否含空白或控制字符（多为从富文本/表格误粘的脏数据，URL 中不应出现） */
const hasIllegalChar = (url: string): boolean => /[\s\u0000-\u001f\u007f]/.test(url)

/**
 * 影响URL 校验，与后端 `normalize_affected_url` 同一口径：
 * 条数上限、单条长度上限、条目含空白或控制字符。
 */
export function validateAffectedUrls(urls: string[]): AffectedUrlValidation {
  const list = urls ?? []
  if (list.length > AFFECTED_URL_MAX_COUNT) {
    return {
      ok: false,
      message: `影响URL 最多 ${AFFECTED_URL_MAX_COUNT} 条，当前共 ${list.length} 条，请分批录入`,
      invalidIndexes: [],
    }
  }
  const invalidIndexes: number[] = []
  let message = ''
  list.forEach((url, i) => {
    if (url.length > AFFECTED_URL_ITEM_MAX_LENGTH) {
      invalidIndexes.push(i)
      message ||= `第 ${i + 1} 条影响URL 长度 ${url.length} 超出上限 ${AFFECTED_URL_ITEM_MAX_LENGTH} 字符`
    } else if (hasIllegalChar(url)) {
      invalidIndexes.push(i)
      message ||= `第 ${i + 1} 条影响URL 含空格或非法字符，请修正后再提交`
    }
  })
  return { ok: message === '', message, invalidIndexes }
}

