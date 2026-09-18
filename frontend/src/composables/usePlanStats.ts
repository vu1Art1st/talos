import { computed, nextTick, ref, watch } from 'vue'
import * as echarts from 'echarts'

import client from '../api/client'
import { useThemeStore } from '../stores/theme'
import type { PlanStats, QueryParams } from '../types'
import { chartThemeName } from '../utils/chartTheme'
import { STAT_CARD_COLORS } from '../utils/colors'

/** 统计面板可选维度（与后端 `GET /testing-plans/stats` 返回字段一致） */
export const DIMENSIONS = [
  { key: 'total_plans', label: '工单总数', color: STAT_CARD_COLORS.blue },
  { key: 'retest_done_plans', label: '复测完成数', color: STAT_CARD_COLORS.green },
  { key: 'first_test_count', label: '初测次数', color: STAT_CARD_COLORS.orange },
  { key: 'retest_count', label: '复测次数', color: STAT_CARD_COLORS.red },
  { key: 'total_test_count', label: '总测试次数', color: STAT_CARD_COLORS.gray },
  { key: 'est_mandays_total', label: '预估人天总计', color: STAT_CARD_COLORS.blue },
  { key: 'actual_mandays_total', label: '实际人天总计', color: STAT_CARD_COLORS.green },
  { key: 'remaining_est_mandays', label: '剩余预估人天', color: STAT_CARD_COLORS.orange },
  { key: 'vulns_by_month', label: '按月漏洞数', color: STAT_CARD_COLORS.blue },
] as const

const STATS_DIMS_KEY = 'testing_plan_stats_dims'

/**
 * 工单列表「统计概览」面板（审计 E-2 从 views/TestingPlanList.vue 抽出）。
 *
 * 职责：维度勾选（localStorage 持久化）、统计取数、按月漏洞数图表（echarts）的
 * 创建/主题重建/尺寸自适应/销毁。
 *
 * @param getFilterParams 取当前筛选参数（与列表/结论共用同一份口径）
 */
export function usePlanStats(getFilterParams: () => QueryParams) {
  const theme = useThemeStore()

  const statsPanel = ref<string[]>([])
  const dims = ref<string[]>(loadDims())
  const stats = ref<PlanStats>({})
  const statsLoading = ref(false)
  const monthChartRef = ref<HTMLElement>()
  let monthChart: echarts.ECharts | null = null
  let monthChartTheme = ''

  function loadDims(): string[] {
    try {
      const saved = JSON.parse(localStorage.getItem(STATS_DIMS_KEY) || 'null')
      if (Array.isArray(saved) && saved.length) return saved
    } catch { /* ignore */ }
    return DIMENSIONS.map((d) => d.key)
  }

  // 勾选的计数类维度（排除图表维度）以数字卡片展示
  const cardDims = computed(() =>
    DIMENSIONS.filter((d) => d.key !== 'vulns_by_month' && dims.value.includes(d.key)))

  watch(dims, (v) => {
    localStorage.setItem(STATS_DIMS_KEY, JSON.stringify(v))
    if (v.includes('vulns_by_month')) nextTick(renderMonthChart)
  })

  // 折叠面板展开 / 明暗切换时，按新主题重建月度图表（隐藏态 init 会得到 0 尺寸，需在可见后渲染；
  // 展开动画约 300ms，动画结束后再 resize 一次兜底）
  watch([statsPanel, () => theme.dark], async ([panel]) => {
    if (panel.includes('stats') && dims.value.includes('vulns_by_month')) {
      await nextTick()
      renderMonthChart()
      setTimeout(() => monthChart?.resize(), 320)
    }
  })

  async function loadStats() {
    statsLoading.value = true
    try {
      const { data } = await client.get('/testing-plans/stats', { params: getFilterParams() })
      stats.value = data
      if (dims.value.includes('vulns_by_month')) nextTick(renderMonthChart)
    } finally {
      statsLoading.value = false
    }
  }

  function renderMonthChart() {
    if (!monthChartRef.value) return
    const themeName = chartThemeName(theme.dark)
    if (monthChart && monthChartTheme !== themeName) {
      monthChart.dispose()
      monthChart = null
    }
    if (!monthChart) {
      monthChart = echarts.init(monthChartRef.value, themeName)
      monthChartTheme = themeName
    }
    const rows = stats.value.vulns_by_month ?? []
    monthChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 30, bottom: 72 },
      title: { text: '按月漏洞数', textStyle: { fontSize: 12.5, fontWeight: 'normal', color: STAT_CARD_COLORS.gray } },
      xAxis: {
        type: 'category', data: rows.map((r) => r.month),
        axisLabel: { rotate: 45, fontSize: 10.5, hideOverlap: true },
      },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{ type: 'bar', data: rows.map((r) => r.count), itemStyle: { color: STAT_CARD_COLORS.blue }, barMaxWidth: 32 }],
    })
    monthChart.resize()
  }

  /** 窗口尺寸变化时自适应（由调用方绑定 resize 事件） */
  function resizeChart() {
    monthChart?.resize()
  }

  /** 组件卸载时销毁实例，避免 canvas 泄漏 */
  function disposeChart() {
    monthChart?.dispose()
    monthChart = null
  }

  return {
    statsPanel,
    dims,
    stats,
    statsLoading,
    monthChartRef,
    cardDims,
    loadStats,
    renderMonthChart,
    resizeChart,
    disposeChart,
  }
}
