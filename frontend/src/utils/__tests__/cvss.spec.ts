import { describe, expect, it } from 'vitest'
import {
  buildVector,
  computeBaseScore,
  parseVector,
  roundup,
  scoreFromVector,
  scoreToLevel,
  type CvssMetrics,
} from '../cvss'

const m = (partial: Partial<CvssMetrics>): CvssMetrics => ({
  AV: 'N', AC: 'L', PR: 'N', UI: 'N', S: 'U', C: 'N', I: 'N', A: 'N',
  ...partial,
})

// 官方/公认向量 → 基础评分样例（FIRST v3.1 规范示例与常见 CVE 口径）
const CASES: [string, number, string][] = [
  ['CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H', 9.8, 'critical'],
  ['CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H', 10.0, 'critical'],
  ['CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:H/I:H/A:H', 7.2, 'high'],
  ['CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:N', 6.4, 'medium'],
  ['CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N', 5.9, 'medium'],
  ['CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N', 6.1, 'medium'],
  ['CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N', 5.3, 'medium'],
  ['CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N', 0.0, 'none'],
  ['CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N', 1.8, 'low'],
]

describe('cvss base score', () => {
  it.each(CASES)('%s = %s (%s)', (vector, score, severity) => {
    const result = scoreFromVector(vector)
    expect(result).not.toBeNull()
    expect(result!.score).toBe(score)
    expect(result!.severity).toBe(severity)
  })

  it('缺任一指标返回 null', () => {
    expect(computeBaseScore(m({ C: '' }))).toBeNull()
    expect(computeBaseScore(m({ AV: 'X' }))).toBeNull()
  })
})

describe('parseVector / buildVector', () => {
  it('合法向量解析并还原', () => {
    const vector = 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'
    const metrics = parseVector(vector)
    expect(metrics).toEqual(m({ C: 'H', I: 'H', A: 'H' }))
    expect(buildVector(metrics!)).toBe(vector)
  })

  it('非法向量返回 null', () => {
    expect(parseVector('')).toBeNull()
    expect(parseVector('CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H')).toBeNull()
    expect(parseVector('AVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H')).toBeNull()
    expect(parseVector('CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:X/C:H/I:H/A:H')).toBeNull()
  })
})

describe('roundup / scoreToLevel', () => {
  it('roundup 向上取一位小数', () => {
    expect(roundup(5.29944)).toBe(5.3)
    expect(roundup(9.8)).toBe(9.8)
    expect(roundup(0)).toBe(0)
  })

  it('评分映射平台等级码', () => {
    expect(scoreToLevel(9.8)).toBe(10)
    expect(scoreToLevel(9.0)).toBe(10)
    expect(scoreToLevel(7.2)).toBe(20)
    expect(scoreToLevel(6.4)).toBe(30)
    expect(scoreToLevel(4.0)).toBe(30)
    expect(scoreToLevel(1.8)).toBe(40)
    expect(scoreToLevel(0)).toBeNull()
  })
})
