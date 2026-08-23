/**
 * URL 列表工具：工单「被测系统URL」等场景的多值合并。
 */

export type UrlLike = string | { url?: string }

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
