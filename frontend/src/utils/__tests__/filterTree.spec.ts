import { describe, expect, it } from 'vitest'

import type { FilterFieldDef, FilterGroup, FilterRule } from '../../types'
import {
  MAX_FILTER_DEPTH,
  applyFilterRuleField,
  applyFilterRuleOp,
  cloneFilterNode,
  countFilterRules,
  createFilterGroup,
  createFilterRule,
  describeFilterTree,
  filterTreeEquals,
  filterTreeToPayload,
  isFilterRuleComplete,
  normalizeFilterTree,
  pruneFilterTree,
} from '../filterTree'

const FIELDS: FilterFieldDef[] = [
  { key: 'system_name', label: '测试系统', type: 'text' },
  { key: 'status', label: '状态', type: 'enum', options: [{ label: '初测完成', value: 30 }] },
]

const rule = (field: string, op: string, value: unknown, extra: Record<string, unknown> = {}) => ({
  field, op, value, ...extra,
})

/** 取条件树的节点投影（忽略 _uid，仅比较结构与取值） */
const shape = (node: unknown): unknown => {
  if (Array.isArray(node)) return node.map(shape)
  if (node && typeof node === 'object') {
    const o = node as Record<string, unknown>
    if (o.kind === 'rule') return { rule: [o.field, o.op, o.value, o.not] }
    return { logic: o.logic, not: o.not, children: (o.children as unknown[]).map(shape) }
  }
  return node
}

describe('filterTree 条件树工具', () => {
  it('历史扁平规则按 connector 左结合折叠：a AND b OR c ≡ (a AND b) OR c', () => {
    const tree = normalizeFilterTree([
      rule('a', 'eq', 1),
      rule('b', 'eq', 2, { connector: 'or' }),
      rule('c', 'eq', 3),
    ])
    expect(shape(tree)).toEqual({
      logic: 'and',
      not: false,
      children: [
        { logic: 'or', not: false, children: [{ rule: ['a', 'eq', 1, false] }, { rule: ['b', 'eq', 2, false] }] },
        { rule: ['c', 'eq', 3, false] },
      ],
    })
  })

  it('同逻辑连续规则平铺在同一层，不做无谓加深', () => {
    const tree = normalizeFilterTree([rule('a', 'eq', 1), rule('b', 'eq', 2), rule('c', 'eq', 3)])
    expect(tree.logic).toBe('and')
    expect(tree.children).toHaveLength(3)
  })

  it('兼容 {rules} 包装、v2 分组对象与显式 kind=group；非法条目被丢弃', () => {
    const wrapped = normalizeFilterTree({ rules: [rule('a', 'eq', 1)] })
    expect(countFilterRules(wrapped)).toBe(1)

    const v2 = normalizeFilterTree({
      logic: 'or',
      not: true,
      children: [{ kind: 'group', logic: 'and', children: [rule('status', 'eq', 30)] }],
    })
    expect(v2.logic).toBe('or')
    expect(v2.not).toBe(true)
    expect(countFilterRules(v2)).toBe(1)

    const dirty = normalizeFilterTree([rule('a', 'eq', 1), { op: 'eq' }, 'x', { field: 'b' }])
    expect(countFilterRules(dirty)).toBe(1)
  })

  it('不可信来源（localStorage）按字段白名单过滤，未知字段不下发', () => {
    const tree = normalizeFilterTree(
      [rule('system_name', 'contains', '商城'), rule('secret_field', 'eq', 'x')],
      new Set(['system_name']),
    )
    expect(countFilterRules(tree)).toBe(1)
    expect((tree.children[0] as FilterRule).field).toBe('system_name')
  })

  it('超过嵌套上限的层级被截断为空分组（而非抛错）', () => {
    let node: unknown = { logic: 'and', children: [rule('a', 'eq', 1)] }
    for (let i = 0; i < MAX_FILTER_DEPTH + 1; i++) node = { logic: 'and', children: [node] }
    expect(countFilterRules(normalizeFilterTree(node))).toBe(0)
  })

  it('剪枝：剔除未填完整的条件与随之变空的分组，计数与请求同源', () => {
    const tree = normalizeFilterTree({
      logic: 'and',
      children: [
        rule('system_name', 'contains', '商城'),
        rule('status', 'eq', ''),
        { logic: 'or', children: [rule('status', 'eq', '')] },
      ],
    })
    expect(countFilterRules(tree)).toBe(3)
    const pruned = pruneFilterTree(tree)
    expect(countFilterRules(pruned)).toBe(1)
    expect(pruned.children).toHaveLength(1)
  })

  it('完整性判定覆盖空值类与区间操作符', () => {
    expect(isFilterRuleComplete(createFilterRule(FIELDS))).toBe(false)
    expect(isFilterRuleComplete({ kind: 'rule', field: 'x', op: 'is_empty', value: null, not: false })).toBe(true)
    expect(isFilterRuleComplete({ kind: 'rule', field: 'x', op: 'between', value: [1, 2], not: false })).toBe(true)
    expect(isFilterRuleComplete({ kind: 'rule', field: 'x', op: 'between', value: [1, null], not: false })).toBe(false)
  })

  it('请求载荷剥离 _uid 并保留嵌套结构与组级 非', () => {
    const tree = normalizeFilterTree({
      logic: 'and',
      children: [
        rule('system_name', 'contains', '商城'),
        { logic: 'or', not: true, children: [rule('status', 'eq', 30)] },
      ],
    })
    expect(filterTreeToPayload(tree)).toEqual({
      logic: 'and',
      not: false,
      children: [
        { kind: 'rule', field: 'system_name', op: 'contains', value: '商城', not: false },
        { logic: 'or', not: true, children: [{ kind: 'rule', field: 'status', op: 'eq', value: 30, not: false }] },
      ],
    })
  })

  it('结构比较忽略 _uid，深拷贝不共享取值数组', () => {
    const a = normalizeFilterTree({ logic: 'and', children: [rule('x', 'between', [1, 2])] })
    const b = normalizeFilterTree({ logic: 'and', children: [rule('x', 'between', [1, 2])] })
    expect(a._uid).not.toBe(b._uid)
    expect(filterTreeEquals(a, b)).toBe(true)
    expect(filterTreeEquals(a, normalizeFilterTree({ logic: 'or', children: [rule('x', 'between', [1, 2])] }))).toBe(false)

    const copy = cloneFilterNode(a)
    expect(filterTreeEquals(copy, a)).toBe(true)
    expect((copy.children[0] as FilterRule).value).not.toBe((a.children[0] as FilterRule).value)
  })

  it('表达式预览呈现括号与 且/或/非，空树返回空串', () => {
    const tree = normalizeFilterTree({
      logic: 'and',
      children: [
        rule('system_name', 'eq', '商城'),
        { logic: 'or', not: true, children: [rule('status', 'eq', 30), rule('status', 'eq', 40)] },
      ],
    })
    expect(describeFilterTree(tree, FIELDS)).toBe('(测试系统 等于 商城 且 非((状态 等于 初测完成 或 状态 等于 40)))')
    expect(describeFilterTree(createFilterGroup(), FIELDS)).toBe('')
  })

  it('切换字段/操作符时重置取值形态', () => {
    const node = createFilterRule(FIELDS)
    node.op = 'between'
    applyFilterRuleOp(node, FIELDS)
    expect(node.value).toEqual([null, null])

    node.field = 'status'
    applyFilterRuleField(node, FIELDS)
    expect(node.op).toBe('eq')
    expect(node.value).toBe('')
  })

  it('空分组可安全序列化（后端会忽略）', () => {
    const empty: FilterGroup = createFilterGroup()
    expect(filterTreeToPayload(empty)).toEqual({ logic: 'and', not: false, children: [] })
    expect(countFilterRules(empty)).toBe(0)
  })
})
