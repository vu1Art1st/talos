import { describe, expect, it } from 'vitest'
import {
  buildVector,
  computeBaseScore,
  parseAnyVector,
  parseVector,
  parseVector31,
  roundup,
  scoreFromVector,
  scoreToLevel,
  type CvssMetrics,
} from '../cvss'

const m = (partial: Partial<CvssMetrics>): CvssMetrics => ({
  AV: 'N', AC: 'L', AT: 'N', PR: 'N', UI: 'N',
  VC: 'N', VI: 'N', VA: 'N', SC: 'N', SI: 'N', SA: 'N',
  ...partial,
})

// FIRST CVSS 4.0 Section 7 与参考实现官方样例 → 基础评分。
const CASES: [string, number, string][] = [
  ['CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H', 10.0, 'critical'],
  ['CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:N/SA:N', 0.0, 'none'],
  ['CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N', 9.3, 'critical'],
  ['CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:H/SI:H/SA:H', 7.9, 'high'],
  ['CVSS:4.0/AV:P/AC:H/AT:P/PR:H/UI:A/VC:L/VI:N/VA:N/SC:N/SI:N/SA:N', 1.0, 'low'],
  ['CVSS:4.0/AV:L/AC:L/AT:N/PR:L/UI:P/VC:N/VI:H/VA:H/SC:N/SI:L/SA:L', 5.2, 'medium'],
]

describe('CVSS 4.0 base score', () => {
  it.each(CASES)('%s = %s (%s)', (vector, score, severity) => {
    const result = scoreFromVector(vector)
    expect(result).not.toBeNull()
    expect(result!.score).toBe(score)
    expect(result!.severity).toBe(severity)
    expect(result!.version).toBe('4.0')
  })

  it('缺任一指标返回 null', () => {
    expect(computeBaseScore(m({ VC: '' }))).toBeNull()
    expect(computeBaseScore(m({ AV: 'X' }))).toBeNull()
  })

  it('扩展指标仍可按完整 CVSS 4.0 向量获得评分', () => {
    const result = scoreFromVector(
      'CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H/E:U',
    )
    expect(result?.score).toBe(9.1)
    expect(result?.version).toBe('4.0')
  })
})

describe('parseVector / buildVector', () => {
  it('解析并还原 CVSS 4.0 Base 向量', () => {
    const vector = 'CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N'
    const metrics = parseVector(vector)
    expect(metrics).toEqual(m({ VC: 'H', VI: 'H', VA: 'H' }))
    expect(buildVector(metrics!)).toBe(vector)
  })

  it('Base 解析拒绝扩展指标与非法结构', () => {
    expect(parseVector(
      'CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H/E:U',
    )).toBeNull()
    expect(parseVector('CVSS:4.0/AV:N/AC:L/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N')).toBeNull()
    expect(parseVector('CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:X/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N')).toBeNull()
  })
})

describe('存量 CVSS 3.1 兼容', () => {
  const vector = 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'

  it('继续解析并按 3.1 公式评分', () => {
    expect(parseVector31(vector)).toEqual({
      AV: 'N', AC: 'L', PR: 'N', UI: 'N', S: 'U', C: 'H', I: 'H', A: 'H',
    })
    const result = scoreFromVector(vector)
    expect(result?.score).toBe(9.8)
    expect(result?.severity).toBe('critical')
    expect(result?.version).toBe('3.1')
  })

  it('按版本标记表单回显数据', () => {
    expect(parseAnyVector(vector)?.version).toBe('3.1')
    expect(parseAnyVector(
      'CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N',
    )?.version).toBe('4.0')
  })
})

describe('roundup / scoreToLevel', () => {
  it('3.1 roundup 向上取一位小数', () => {
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
