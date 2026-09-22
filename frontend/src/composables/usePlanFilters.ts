import { computed, ref } from 'vue'

import type { FilterGroup, QueryParams } from '../types'
import { DATE_RANGE_OPTIONS, computeDateRange } from '../utils/dateRange'
import {
  cloneFilterNode,
  countFilterRules,
  createFilterGroup,
  filterTreeToPayload,
  normalizeFilterTree,
  pruneFilterTree,
} from '../utils/filterTree'

/**
 * 工单列表的筛选状态与查询参数拼装（审计 E-2 从 views/TestingPlanList.vue 抽出）。
 *
 * 覆盖三类筛选：快捷筛选（多选下拉）、统计周期（初测完成 / 复测发起 / 复测完成 / 复测报告生成）、
 * 聚合筛选条件树（分组嵌套，可持久化）。
 * `buildParams()` 是**列表 / 统计 / 结论 / 导出四处唯一的参数口径**，避免各调用点各拼一份导致筛选不一致。
 *
 * @param onChange 任一筛选条件变化时的回调（由调用方落到列表回到首页 + 刷新统计）
 */
export function usePlanFilters(onChange: () => void) {
  // ---------- 快捷筛选：三项布尔筛选收敛为单个下拉多选，myTests/unclaimed/pending 由勾选项派生 ----------
  const quickFilters = ref<string[]>([])
  const myTests = computed(() => quickFilters.value.includes('my_tests'))
  const unclaimed = computed(() => quickFilters.value.includes('unclaimed'))
  const pending = computed(() => quickFilters.value.includes('pending'))
  const quickFilterCount = computed(() => quickFilters.value.length)

  function onQuickFilterChange() {
    onChange()
  }

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

  // 聚合筛选可选字段（与后端 _PLAN_FILTER_FIELDS 白名单保持一致）
  const FILTER_FIELDS = new Set([
    'system_name', 'test_type', 'department', 'receive_time',
    'status', 'first_test_done_time', 'retest_done_time', 'est_mandays',
    'actual_mandays', 'testers',
  ])

  /**
   * localStorage 中的历史条件（不可信来源）：字段名按白名单过滤后才进入条件树。
   * 兼容两种历史形态 —— 旧扁平规则数组（按 connector 左结合折叠）与新版分组树。
   */
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

  // 条件变化：持久化 + 防抖刷新列表与统计
  function onFiltersChange() {
    localStorage.setItem(RULES_KEY, JSON.stringify(cloneFilterNode(filterTree.value)))
    if (filterTimer) clearTimeout(filterTimer)
    filterTimer = setTimeout(() => onChange(), 250)
  }

  /** 组件卸载时清理防抖计时器 */
  function disposeFilters() {
    if (filterTimer) clearTimeout(filterTimer)
  }

  /**
   * 查询参数拼装（列表 / 统计 / 结论 / 导出共用）。
   * @param search 关键词（来自 useListPage）
   * @param sort   排序（来自 useListPage）
   */
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
    if (myTests.value) params.my_tests = true
    if (unclaimed.value) params.unclaimed = true
    if (pending.value) params.pending = true
    if (sort.prop) {
      params.sort = sort.prop
      params.order = sort.order
    }
    return params
  }

  return {
    quickFilters,
    myTests,
    unclaimed,
    pending,
    quickFilterCount,
    onQuickFilterChange,
    rangeKind,
    customRange,
    onRangeChange,
    periodLabel,
    filterVisible,
    filterTree,
    filterCount,
    onFiltersChange,
    disposeFilters,
    buildParams,
  }
}
