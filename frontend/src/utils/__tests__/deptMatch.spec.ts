import { describe, expect, it } from 'vitest'
import { deptSimilarity, findSimilarDepartments, normalizeDeptName } from '../deptMatch'
import type { Group } from '../../types'

function group(id: number, name: string): Group {
  return { id, name, remark: '' }
}

describe('部门名称相似度', () => {
  it('归一化全半角、空白与标点', () => {
    expect(normalizeDeptName(' ＡＩ业务部 ')).toBe('ai业务部')
    expect(normalizeDeptName('集成（服务）部')).toBe('集成服务部')
  })

  it('识别共用核心词的相似部门', () => {
    expect(deptSimilarity('集成部', '集成服务部')).toBeGreaterThanOrEqual(0.62)
    expect(deptSimilarity('产品部', '产品事业部')).toBeGreaterThanOrEqual(0.62)
  })

  it('无关部门不判相似', () => {
    expect(deptSimilarity('财务部', '综合部')).toBeLessThan(0.62)
  })

  it('精确同名不进入相似候选', () => {
    const groups = [group(1, '集成服务部'), group(2, '集成部')]
    expect(findSimilarDepartments('集成服务部', groups).map((g) => g.id)).toEqual([2])
  })

  it('全半角/标点差异视为相似候选，便于自动更正', () => {
    const groups = [group(1, 'ＡＩ业务部')]
    expect(findSimilarDepartments('AI业务部', groups).map((g) => g.id)).toEqual([1])
  })

  it('相似候选按分数倒序返回', () => {
    const groups = [group(1, '集成服务部'), group(2, '集成部'), group(3, '财务部')]
    expect(findSimilarDepartments('集成服务部x', groups).map((g) => g.id)).toEqual([1, 2])
  })
})
