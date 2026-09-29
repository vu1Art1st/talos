import { computed, ref } from 'vue'

import type { FilterGroup, FilterRule, QueryParams } from '../types'
import { DATE_RANGE_OPTIONS, computeDateRange } from '../utils/dateRange'
import {
  cloneFilterNode,
  countFilterRules,
  createFilterGroup,
  filterTreeEquals,
  filterTreeToPayload,
  normalizeFilterTree,
  pruneFilterTree,
} from '../utils/filterTree'

export type PlanFilterPreset = 'my_tests' | 'unclaimed' | 'pending'

interface PlanFilterOptions {
  getCurrentUserId: () => number | null | undefined
}

const UNCLAIMED_TESTER = '__unclaimed__'
const PENDING_STATUSES = [10, 20, 50]
const ACTIVE_TESTER_STATUSES = [20, 40, 50]
let presetUid = 1_000_000

function presetRule(field: string, value: string[] | number[]): FilterRule {
  return {
    kind: 'rule', field, op: 'eq', value, not: false, _uid: presetUid++,
  }
}

function presetNode(preset: PlanFilterPreset, userId?: number | null) {
  if (preset === 'pending') return presetRule('status', PENDING_STATUSES)
  if (preset === 'unclaimed') return presetRule('testers', [UNCLAIMED_TESTER])
  if (!userId) return null
  return {
    kind: 'group' as const,
    logic: 'and' as const,
    not: false,
    children: [
      presetRule('testers', [userId]),
      presetRule('status', ACTIVE_TESTER_STATUSES),
    ],
    _uid: presetUid++,
  }
}

/**
 * 工单列表的筛选状态与查询参数拼装。
 *
 * 顶部只保留关键词与统计周期；快捷筛选作为预设写入统一条件树，确保列表 / 统计 /
 * 结论 / 导出共用同一 `filters` 参数。
 */
export function usePlanFilters(onChange: () => void, options: PlanFilterOptions) {
  // ---------- 统计周期筛选（初测完成 / 复测发起 / 复测完成 / 复测报告生成） ----------
  const rangeKind = ref<string>('')
  const customRange = ref<[string, string] | null>(null)

  function onRangeChange() {
    if (rangeKind.value !== 'custom') customRange.value = null
    onChange()
  }

  /**
   * 当前周期名称（仅快捷项有值；自定义区间留空，由后端按起止日期输出）。
   * 供结论文字括注「（本周）」/「（2026-09-11 - 2026-09-17）」，不参与列表查询参数。
   */
  const periodLabel = computed(() => (
    rangeKind.value && rangeKind.value !== 'custom'
      ? DATE_RANGE_OPTIONS.find((o) => o.value === rangeKind.value)?.label ?? ''
      : ''
  ))

  // ---------- 聚合筛选（条件树：分组 + 嵌套 + 组内/组间 且或非） ----------
  const filterVisible = ref(false)
  const RULES_KEY = 'testing_plan_filters'

  // 已从界面删除的初测/复测完成字段由白名单自动剪枝，不污染新条件树。
  const FILTER_FIELDS = new Set([
    'system_name', 'test_type', 'department', 'receive_time',
    'status', 'est_mandays', 'actual_mandays', 'testers',
  ])

  /** localStorage 中的历史条件：字段名按白名单过滤后才进入条件树。 */
  function loadFilterTree(): FilterGroup {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(RULES_KEY) || 'null')
      return normalizeFilterTree(saved, FILTER_FIELDS)
    } catch {
      return createFilterGroup()
    }
  }

  const filterTree = ref<FilterGroup>(loadFilterTree())

  /** 实际参与查询的条件条数（未填完整的条件与随之变空的分组不计入） */
  const filterCount = computed(() => countFilterRules(pruneFilterTree(filterTree.value)))
  let filterTimer: ReturnType<typeof setTimeout> | null = null

  function persistFilters() {
    localStorage.setItem(RULES_KEY, JSON.stringify(cloneFilterNode(filterTree.value)))
    if (filterTimer) clearTimeout(filterTimer)
    filterTimer = setTimeout(() => onChange(), 250)
  }

  function onFiltersChange() {
    persistFilters()
  }

  function hasPreset(preset: PlanFilterPreset): boolean {
    const node = presetNode(preset, options.getCurrentUserId())
    return node !== null && filterTree.value.children.some((child) => filterTreeEquals(child, node))
  }

  function applyPreset(preset: PlanFilterPreset) {
    const node = presetNode(preset, options.getCurrentUserId())
    if (!node || hasPreset(preset)) return
    filterTree.value.children.push(node)
    persistFilters()
  }

  /** 组件卸载时清理防抖计时器 */
  function disposeFilters() {
    if (filterTimer) clearTimeout(filterTimer)
  }

  /** 查询参数拼装：列表 / 统计 / 结论 / 导出共用。 */
  function buildParams(
    search: string, sort: { prop?: string; order?: string },
  ): QueryParams {
    const params: QueryParams = { search }
    const range = computeDateRange(rangeKind.value, customRange.value)
    if (range) {
      params.first_test_from = range[0]
      params.first_test_to = range[1]
    }
    const pruned = pruneFilterTree(filterTree.value)
    if (countFilterRules(pruned)) {
      params.filters = JSON.stringify(filterTreeToPayload(pruned))
    }
    if (sort.prop) {
      params.sort = sort.prop
      params.order = sort.order
    }
    return params
  }

  return {
    rangeKind,
    customRange,
    onRangeChange,
    periodLabel,
    filterVisible,
    filterTree,
    filterCount,
    hasPreset,
    applyPreset,
    onFiltersChange,
    disposeFilters,
    buildParams,
  }
}
