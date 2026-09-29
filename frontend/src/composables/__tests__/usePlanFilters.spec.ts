// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { FilterGroup, QueryParams } from '../../types'
import { usePlanFilters } from '../usePlanFilters'

function filtersParam(params: QueryParams): FilterGroup {
  return JSON.parse(String(params.filters)) as FilterGroup
}

describe('usePlanFilters', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('快捷预设写入统一 filters，重复点击不重复添加', () => {
    const filters = usePlanFilters(vi.fn(), { getCurrentUserId: () => 7 })

    filters.applyPreset('pending')
    filters.applyPreset('pending')
    expect(filters.filterTree.value.children).toHaveLength(1)
    expect(filtersParam(filters.buildParams('', {}))).toMatchObject({
      children: [{ kind: 'rule', field: 'status', op: 'eq', value: [10, 20, 50] }],
    })

    filters.applyPreset('unclaimed')
    expect(filters.filterTree.value.children).toHaveLength(2)
    filters.disposeFilters()
  })

  it('当前可测试预设使用 AND 分组，避免根节点 OR 改变语义', () => {
    const filters = usePlanFilters(vi.fn(), { getCurrentUserId: () => 7 })
    filters.filterTree.value.logic = 'or'
    filters.applyPreset('my_tests')

    const preset = filters.filterTree.value.children[0] as FilterGroup
    expect(preset).toMatchObject({
      kind: 'group',
      logic: 'and',
      children: [
        { field: 'testers', op: 'eq', value: [7] },
        { field: 'status', op: 'eq', value: [20, 40, 50] },
      ],
    })
    filters.disposeFilters()
  })

  it('已删除的日期字段从历史 localStorage 中剪枝，且不再发送独立快捷参数', () => {
    localStorage.setItem('testing_plan_filters', JSON.stringify({
      logic: 'and',
      children: [
        { kind: 'rule', field: 'first_test_done_time', op: 'eq', value: '2026-01-01' },
        { kind: 'rule', field: 'system_name', op: 'eq', value: ['商城'] },
      ],
    }))
    const filters = usePlanFilters(vi.fn(), { getCurrentUserId: () => 7 })

    expect(filters.filterTree.value.children).toHaveLength(1)
    const params = filters.buildParams('', {})
    expect(params).not.toHaveProperty('pending')
    expect(params).not.toHaveProperty('unclaimed')
    expect(params).not.toHaveProperty('my_tests')
    filters.disposeFilters()
  })
})
