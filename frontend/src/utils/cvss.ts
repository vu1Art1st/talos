/** CVSS 3.1 基础评分计算（Base Score），供漏洞表单计算器与知识库向量预览共用。
 *
 * 仅实现基础评分（8 个指标），时间/环境指标不在录入范围。
 * 公式与取值依据 FIRST CVSS v3.1 Specification。
 */

export interface CvssMetrics {
  AV: string // 攻击途径：N 网络 / A 相邻 / L 本地 / P 物理
  AC: string // 攻击复杂度：L 低 / H 高
  PR: string // 所需权限：N 无 / L 低 / H 高
  UI: string // 用户交互：N 不需要 / R 需要
  S: string // 影响范围：U 不变 / C 改变
  C: string // 机密性影响：H 高 / L 低 / N 无
  I: string // 完整性影响：H 高 / L 低 / N 无
  A: string // 可用性影响：H 高 / L 低 / N 无
}

export type CvssMetricKey = keyof CvssMetrics

export const CVSS_METRIC_DEFS: { key: CvssMetricKey; label: string; options: { value: string; label: string }[] }[] = [
  {
    key: 'AV', label: '攻击途径',
    options: [
      { value: 'N', label: '网络' },
      { value: 'A', label: '相邻' },
      { value: 'L', label: '本地' },
      { value: 'P', label: '物理' },
    ],
  },
  {
    key: 'AC', label: '攻击复杂度',
    options: [
      { value: 'L', label: '低' },
      { value: 'H', label: '高' },
    ],
  },
  {
    key: 'PR', label: '所需权限',
    options: [
      { value: 'N', label: '无' },
      { value: 'L', label: '低' },
      { value: 'H', label: '高' },
    ],
  },
  {
    key: 'UI', label: '用户交互',
    options: [
      { value: 'N', label: '不需要' },
      { value: 'R', label: '需要' },
    ],
  },
  {
    key: 'S', label: '影响范围',
    options: [
      { value: 'U', label: '不变' },
      { value: 'C', label: '改变' },
    ],
  },
  {
    key: 'C', label: '机密性影响',
    options: [
      { value: 'H', label: '高' },
      { value: 'L', label: '低' },
      { value: 'N', label: '无' },
    ],
  },
  {
    key: 'I', label: '完整性影响',
    options: [
      { value: 'H', label: '高' },
      { value: 'L', label: '低' },
      { value: 'N', label: '无' },
    ],
  },
  {
    key: 'A', label: '可用性影响',
    options: [
      { value: 'H', label: '高' },
      { value: 'L', label: '低' },
      { value: 'N', label: '无' },
    ],
  },
]

const VALID: Record<CvssMetricKey, Set<string>> = {
  AV: new Set(['N', 'A', 'L', 'P']),
  AC: new Set(['L', 'H']),
  PR: new Set(['N', 'L', 'H']),
  UI: new Set(['N', 'R']),
  S: new Set(['U', 'C']),
  C: new Set(['H', 'L', 'N']),
  I: new Set(['H', 'L', 'N']),
  A: new Set(['H', 'L', 'N']),
}

const AV_WEIGHT: Record<string, number> = { N: 0.85, A: 0.62, L: 0.55, P: 0.2 }
const AC_WEIGHT: Record<string, number> = { L: 0.77, H: 0.44 }
const UI_WEIGHT: Record<string, number> = { N: 0.85, R: 0.62 }
const CIA_WEIGHT: Record<string, number> = { H: 0.56, L: 0.22, N: 0 }

function prWeight(pr: string, scopeChanged: boolean): number {
  if (pr === 'N') return 0.85
  if (pr === 'L') return scopeChanged ? 0.68 : 0.62
  return scopeChanged ? 0.5 : 0.27
}

/** 官方 Roundup（v3.1 规范伪代码）：向上取到一位小数，内部放大 10^5 消除二进制浮点误差。 */
export function roundup(value: number): number {
  const intInput = Math.round(value * 100000)
  if (intInput % 10000 === 0) return intInput / 100000
  return (Math.floor(intInput / 10000) + 1) / 10
}

/** 解析 CVSS 3.1 向量字符串；不完整/非法返回 null。 */
export function parseVector(vector: string): CvssMetrics | null {
  if (!vector) return null
  const parts = vector.trim().split('/').map((s) => s.trim())
  if (parts.length !== 9 || !/^CVSS:3\.[01]$/.test(parts[0])) return null
  const metrics: Record<string, string> = {}
  for (const part of parts.slice(1)) {
    const [k, v] = part.split(':')
    if (!k || !v || !(k in VALID)) return null
    metrics[k] = v
  }
  for (const key of Object.keys(VALID) as CvssMetricKey[]) {
    if (!VALID[key].has(metrics[key])) return null
  }
  return metrics as unknown as CvssMetrics
}

/** 由 8 指标构造向量字符串（要求全部有值）。 */
export function buildVector(metrics: CvssMetrics): string {
  const keys = Object.keys(VALID) as CvssMetricKey[]
  if (keys.some((k) => !VALID[k].has(metrics[k]))) return ''
  return 'CVSS:3.1/' + keys.map((k) => `${k}:${metrics[k]}`).join('/')
}

export interface CvssResult {
  score: number
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical'
  severityLabel: string
}

/** 计算基础评分与严重度；任一指标缺失返回 null。 */
export function computeBaseScore(metrics: CvssMetrics): CvssResult | null {
  if (!parseVector(buildVector(metrics))) return null
  const scopeChanged = metrics.S === 'C'
  const iss = 1 - (1 - CIA_WEIGHT[metrics.C]) * (1 - CIA_WEIGHT[metrics.I]) * (1 - CIA_WEIGHT[metrics.A])
  const impact = scopeChanged
    ? 7.52 * (iss - 0.029) - 3.25 * Math.pow(iss - 0.02, 15)
    : 6.42 * iss
  const exploitability =
    8.22 * AV_WEIGHT[metrics.AV] * AC_WEIGHT[metrics.AC] * prWeight(metrics.PR, scopeChanged) * UI_WEIGHT[metrics.UI]
  let score = 0
  if (impact > 0) {
    score = scopeChanged
      ? roundup(Math.min(1.08 * (impact + exploitability), 10))
      : roundup(Math.min(impact + exploitability, 10))
  }
  const severity =
    score === 0 ? 'none'
      : score < 4 ? 'low'
        : score < 7 ? 'medium'
          : score < 9 ? 'high'
            : 'critical'
  const severityLabel = { none: '无风险', low: '低危', medium: '中危', high: '高危', critical: '严重' }[severity]
  return { score, severity, severityLabel }
}

/** 便捷入口：直接由向量字符串计算。 */
export function scoreFromVector(vector: string): CvssResult | null {
  const metrics = parseVector(vector)
  return metrics ? computeBaseScore(metrics) : null
}

/** 评分 → 平台漏洞等级码（constants.VUL_LEVEL：10 严重 / 20 高危 / 30 中危 / 40 低危）。
 * 未评分（0）返回 null，不自动建议等级。 */
export function scoreToLevel(score: number): number | null {
  if (score >= 9) return 10
  if (score >= 7) return 20
  if (score >= 4) return 30
  if (score > 0) return 40
  return null
}
