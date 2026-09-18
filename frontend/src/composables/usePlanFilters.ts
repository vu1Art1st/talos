import { computed, ref } from 'vue'

import type { FilterRule } from '../components/FilterBuilder.vue'
import type { QueryParams } from '../types'
import { computeDateRange } from '../utils/dateRange'

/**
 * 工单列表的筛选状态与查询参数拼装（审计 E-2 从 views/TestingPlanList.vue 抽出）。
 *
 * 覆盖三类筛选：快捷筛选（多选下拉）、时间区间（按初测完成时间）、聚合筛选规则（可持久化）。
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

  // ---------- 时间范围筛选（按初测完成时间） ----------
  const rangeKind = ref<string>('')
  const customRange = ref<[string, string] | null>(null)

  function onRangeChange() {
    if (rangeKind.value !== 'custom') customRange.value = null
    onChange()
  }

  // ---------- 聚合筛选 ----------
  const filterVisible = ref(false)
  const RULES_KEY = 'testing_plan_filters'

  // 聚合筛选可选字段（与后端 _PLAN_FILTER_FIELDS 白名单保持一致）
  const FILTER_FIELDS = new Set([
    'system_name', 'test_type', 'department', 'receive_time',
    'status', 'first_test_done_time', 'retest_done_time', 'testers',
  ])

  /** localStorage 中的历史规则（不可信来源）：字段名按后端白名单、操作符按字符串校验后才使用 */
  type StoredRule = { field: string; op: string; value?: unknown; not?: unknown; connector?: unknown }
  const isStoredRule = (r: unknown): r is StoredRule => {
    if (!r || typeof r !== 'object') return false
    const o = r as Record<string, unknown>
    return typeof o.field === 'string' && o.field !== ''
      && FILTER_FIELDS.has(o.field) && typeof o.op === 'string'
  }

  function loadFilterRules(): FilterRule[] {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(RULES_KEY) || 'null')
      if (Array.isArray(saved)) {
        return saved
          .filter(isStoredRule)
          .map(({ field, op, value, not, connector }) => ({
            field,
            op,
            // value 形态由 FilterBuilder 写入；历史/手改数据不可信，非法值由 isRuleComplete 在使用处兜底
            value: (value ?? '') as FilterRule['value'],
            not: !!not,
            connector: connector === 'or' ? ('or' as const) : ('and' as const),
          }))
      }
    } catch { /* ignore */ }
    return []
  }

  const rules = ref<FilterRule[]>(loadFilterRules())

  function isRuleComplete(r: FilterRule): boolean {
    if (r.op === 'is_empty' || r.op === 'is_not_empty') return true
    if (r.op === 'between') {
      if (!Array.isArray(r.value) || r.value.length !== 2) return false
      const [lo, hi] = r.value as (string | number | null)[]
      return lo !== null && lo !== '' && hi !== null && hi !== ''
    }
    return r.value !== null && r.value !== ''
  }

  const filterCount = computed(() => rules.value.filter(isRuleComplete).length)
  let filterTimer: ReturnType<typeof setTimeout> | null = null

  // 规则变化：持久化 + 防抖刷新列表与统计
  function onFiltersChange() {
    localStorage.setItem(RULES_KEY, JSON.stringify(rules.value))
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
    const validRules = rules.value.filter(isRuleComplete)
    if (validRules.length) {
      params.filters = JSON.stringify({
        rules: validRules.map(({ field, op, value, not, connector }) => ({
          field, op, value, not, connector,
        })),
      })
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
    filterVisible,
    rules,
    isRuleComplete,
    filterCount,
    onFiltersChange,
    disposeFilters,
    buildParams,
  }
}
