// 部门名称相似度：仅服务于资产录入时的「相似部门」提示，不改变后端精确匹配口径。
import type { Group } from '../types'

/** 相似度阈值（0-1）：低于该值不再提示，避免误报。 */
export const DEPT_SIMILARITY_THRESHOLD = 0.62

// 通用组织后缀：剥离后核心相同（如 集成部 / 集成服务部）时视为高相似。
const GENERIC_SUFFIXES = ['事业部', '分公司', '有限公司', '公司', '中心', '团队', '小组', '组', '部', '室']
const PUNCTUATION_RE = /[\s\u3000()（）\[\]【】{}<>《》·,，.。;；:：!！?？'"`~\-—_/\\|]/g

/** 归一化部门名：全半角统一、去空白与常见标点、英文小写。 */
export function normalizeDeptName(name: string): string {
  return (name ?? '').normalize('NFKC').trim().toLowerCase().replace(PUNCTUATION_RE, '')
}

function lcsLength(a: string, b: string): number {
  const prev = new Array<number>(b.length + 1).fill(0)
  for (let i = 1; i <= a.length; i++) {
    let diagonal = 0
    for (let j = 1; j <= b.length; j++) {
      const up = prev[j]
      prev[j] = a[i - 1] === b[j - 1] ? diagonal + 1 : Math.max(up, prev[j - 1])
      diagonal = up
    }
  }
  return prev[b.length]
}

function stripGenericSuffix(value: string): string {
  for (const suffix of GENERIC_SUFFIXES) {
    if (value.length > suffix.length && value.endsWith(suffix)) {
      return value.slice(0, -suffix.length)
    }
  }
  return value
}

/** 两个部门名的相似度（0-1）；完全相等返回 1。 */
export function deptSimilarity(a: string, b: string): number {
  const na = normalizeDeptName(a)
  const nb = normalizeDeptName(b)
  if (!na || !nb) return 0
  if (na === nb) return 1
  const lcs = (2 * lcsLength(na, nb)) / (na.length + nb.length)
  const ca = stripGenericSuffix(na)
  const cb = stripGenericSuffix(nb)
  const core = ca && cb && (ca.includes(cb) || cb.includes(ca))
    ? Math.min(ca.length, cb.length) / Math.max(ca.length, cb.length)
    : 0
  return Math.max(lcs, core)
}

/** 按相似度倒序返回候选组织；精确同名不算相似。 */
export function findSimilarDepartments(name: string, groups: Group[]): Group[] {
  const key = normalizeDeptName(name)
  if (key.length < 2) return []
  const raw = (name ?? '').trim()
  return groups
    .map((group) => ({ group, score: deptSimilarity(key, group.name) }))
    .filter(({ group, score }) => group.name.trim() !== raw && score >= DEPT_SIMILARITY_THRESHOLD)
    .sort((a, b) => b.score - a.score)
    .map(({ group }) => group)
}
