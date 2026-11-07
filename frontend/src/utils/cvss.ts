/** CVSS 基础评分适配层。
 *
 * 新建与重新计算统一使用 CVSS 4.0 Base（11 项指标）；存量 CVSS 3.1 向量继续
 * 支持只读解析，避免历史漏洞与知识库模板在编辑时丢失评分。
 * CVSS 4.0 的 MacroVector 计算由 @pandatix/js-cvss 提供。
 */

import { CVSS40 } from '@pandatix/js-cvss'

export type CvssVersion = '3.1' | '4.0'

/** CVSS 4.0 基础指标。 */
export interface CvssMetrics {
  AV: string // 攻击途径：N 网络 / A 相邻 / L 本地 / P 物理
  AC: string // 攻击复杂度：L 低 / H 高
  AT: string // 攻击条件：N 无 / P 存在
  PR: string // 所需权限：N 无 / L 低 / H 高
  UI: string // 用户交互：N 无 / P 被动 / A 主动
  VC: string // 易受影响系统机密性：H 高 / L 低 / N 无
  VI: string // 易受影响系统完整性：H 高 / L 低 / N 无
  VA: string // 易受影响系统可用性：H 高 / L 低 / N 无
  SC: string // 后续系统机密性：H 高 / L 低 / N 无
  SI: string // 后续系统完整性：H 高 / L 低 / N 无
  SA: string // 后续系统可用性：H 高 / L 低 / N 无
}

export type CvssMetricKey = keyof CvssMetrics

/** CVSS 3.1 基础指标（仅用于存量向量评分）。 */
export interface Cvss31Metrics {
  AV: string
  AC: string
  PR: string
  UI: string
  S: string
  C: string
  I: string
  A: string
}

export type Cvss31MetricKey = keyof Cvss31Metrics

const IMPACT_OPTIONS = [
  { value: 'H', label: '高' },
  { value: 'L', label: '低' },
  { value: 'N', label: '无' },
]

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
    key: 'AT', label: '攻击条件',
    options: [
      { value: 'N', label: '无' },
      { value: 'P', label: '存在' },
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
      { value: 'N', label: '无' },
      { value: 'P', label: '被动' },
      { value: 'A', label: '主动' },
    ],
  },
  { key: 'VC', label: '系统机密性', options: IMPACT_OPTIONS },
  { key: 'VI', label: '系统完整性', options: IMPACT_OPTIONS },
  { key: 'VA', label: '系统可用性', options: IMPACT_OPTIONS },
  { key: 'SC', label: '后续系统机密性', options: IMPACT_OPTIONS },
  { key: 'SI', label: '后续系统完整性', options: IMPACT_OPTIONS },
  { key: 'SA', label: '后续系统可用性', options: IMPACT_OPTIONS },
]

const VALID: Record<CvssMetricKey, Set<string>> = {
  AV: new Set(['N', 'A', 'L', 'P']),
  AC: new Set(['L', 'H']),
  AT: new Set(['N', 'P']),
  PR: new Set(['N', 'L', 'H']),
  UI: new Set(['N', 'P', 'A']),
  VC: new Set(['H', 'L', 'N']),
  VI: new Set(['H', 'L', 'N']),
  VA: new Set(['H', 'L', 'N']),
  SC: new Set(['H', 'L', 'N']),
  SI: new Set(['H', 'L', 'N']),
  SA: new Set(['H', 'L', 'N']),
}

const VALID_31: Record<Cvss31MetricKey, Set<string>> = {
  AV: new Set(['N', 'A', 'L', 'P']),
  AC: new Set(['L', 'H']),
  PR: new Set(['N', 'L', 'H']),
  UI: new Set(['N', 'R']),
  S: new Set(['U', 'C']),
  C: new Set(['H', 'L', 'N']),
  I: new Set(['H', 'L', 'N']),
  A: new Set(['H', 'L', 'N']),
}

const METRIC_KEYS = Object.keys(VALID) as CvssMetricKey[]
const METRIC_KEYS_31 = Object.keys(VALID_31) as Cvss31MetricKey[]

const AV_WEIGHT: Record<string, number> = { N: 0.85, A: 0.62, L: 0.55, P: 0.2 }
const AC_WEIGHT: Record<string, number> = { L: 0.77, H: 0.44 }
const UI_WEIGHT: Record<string, number> = { N: 0.85, R: 0.62 }
const CIA_WEIGHT: Record<string, number> = { H: 0.56, L: 0.22, N: 0 }

export function emptyCvssMetrics(): CvssMetrics {
  return { AV: '', AC: '', AT: '', PR: '', UI: '', VC: '', VI: '', VA: '', SC: '', SI: '', SA: '' }
}

function prWeight(pr: string, scopeChanged: boolean): number {
  if (pr === 'N') return 0.85
  if (pr === 'L') return scopeChanged ? 0.68 : 0.62
  return scopeChanged ? 0.5 : 0.27
}

/** 官方 Roundup（v3.1 规范伪代码）：向上取到一位小数。 */
export function roundup(value: number): number {
  const intInput = Math.round(value * 100000)
  if (intInput % 10000 === 0) return intInput / 100000
  return (Math.floor(intInput / 10000) + 1) / 10
}

/** 解析 CVSS 4.0 Base 向量；带可选指标或结构不完整时返回 null。 */
export function parseVector(vector: string): CvssMetrics | null {
  if (!vector.trim().startsWith('CVSS:4.0/')) return null
  try {
    const parsed = new CVSS40(vector.trim())
    if (parsed.Nomenclature() !== 'CVSS-B') return null
    const metrics = Object.fromEntries(
      METRIC_KEYS.map((key) => [key, parsed.Get(key)]),
    ) as unknown as CvssMetrics
    return METRIC_KEYS.every((key) => VALID[key].has(metrics[key])) ? metrics : null
  } catch {
    return null
  }
}

/** 解析 CVSS 3.1 Base 向量（仅用于存量数据展示）。 */
export function parseVector31(vector: string): Cvss31Metrics | null {
  if (!vector) return null
  const parts = vector.trim().split('/').map((s) => s.trim())
  if (parts.length !== 9 || !/^CVSS:3\.[01]$/.test(parts[0])) return null
  const metrics: Record<string, string> = {}
  for (const part of parts.slice(1)) {
    const [key, value] = part.split(':')
    if (!key || !value || !(key in VALID_31)) return null
    metrics[key] = value
  }
  for (const key of METRIC_KEYS_31) {
    if (!VALID_31[key].has(metrics[key])) return null
  }
  return metrics as unknown as Cvss31Metrics
}

export type ParsedCvssVector =
  | { version: '4.0'; metrics: CvssMetrics }
  | { version: '3.1'; metrics: Cvss31Metrics }

/** 按向量版本返回基础指标；用于表单回显旧版 3.1 或新版 4.0。 */
export function parseAnyVector(vector: string): ParsedCvssVector | null {
  if (vector.trim().startsWith('CVSS:4.0/')) {
    const metrics = parseVector(vector)
    return metrics ? { version: '4.0', metrics } : null
  }
  const metrics = parseVector31(vector)
  return metrics ? { version: '3.1', metrics } : null
}

/** 由 11 项基础指标构造 CVSS 4.0 向量（要求全部有值）。 */
export function buildVector(metrics: CvssMetrics): string {
  if (METRIC_KEYS.some((key) => !VALID[key].has(metrics[key]))) return ''
  return 'CVSS:4.0/' + METRIC_KEYS.map((key) => `${key}:${metrics[key]}`).join('/')
}

export interface CvssResult {
  score: number
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical'
  severityLabel: string
  version: CvssVersion
}

function resultForScore(score: number, version: CvssVersion): CvssResult {
  const severity =
    score === 0 ? 'none'
      : score < 4 ? 'low'
        : score < 7 ? 'medium'
          : score < 9 ? 'high'
            : 'critical'
  const severityLabel = { none: '无风险', low: '低危', medium: '中危', high: '高危', critical: '严重' }[severity]
  return { score, severity, severityLabel, version }
}

function computeBaseScore31(metrics: Cvss31Metrics): CvssResult | null {
  if (METRIC_KEYS_31.some((key) => !VALID_31[key].has(metrics[key]))) return null
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
  return resultForScore(score, '3.1')
}

/** 计算 CVSS 4.0 基础评分与严重度；任一指标缺失返回 null。 */
export function computeBaseScore(metrics: CvssMetrics): CvssResult | null {
  const vector = buildVector(metrics)
  if (!vector) return null
  try {
    return resultForScore(new CVSS40(vector).Score(), '4.0')
  } catch {
    return null
  }
}

/** 便捷入口：按向量声明版本计算评分；3.1 与 4.0 均支持。 */
export function scoreFromVector(vector: string): CvssResult | null {
  const value = vector.trim()
  if (value.startsWith('CVSS:4.0/')) {
    try {
      return resultForScore(new CVSS40(value).Score(), '4.0')
    } catch {
      return null
    }
  }
  const metrics = parseVector31(value)
  return metrics ? computeBaseScore31(metrics) : null
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
