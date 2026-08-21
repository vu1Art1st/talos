import * as echarts from 'echarts'

// ECharts 明 / 暗双主题（唯一图表主题源），与 style.css 令牌层视觉对齐
// 图表系列色唯一色源：视图内自定义系列色时必须引用 PALETTE，禁止散落硬编码
export const PALETTE = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6', '#ec4899', '#84cc16']

function makeTheme(dark: boolean) {
  const axis = dark ? '#6e7681' : '#9ca3af'
  const split = dark ? '#262c33' : '#f0f1f3'
  const text = dark ? '#9da7b3' : '#4b5563'
  return {
    color: PALETTE,
    textStyle: { color: text },
    legend: { textStyle: { color: text }, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    tooltip: {
      backgroundColor: dark ? '#1c2128' : '#ffffff',
      borderWidth: 0,
      padding: [10, 14],
      textStyle: { color: dark ? '#e6edf3' : '#111827', fontSize: 13 },
      extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,.18); border-radius: 10px;',
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: split } },
      axisTick: { show: false },
      axisLabel: { color: axis },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: axis },
      splitLine: { lineStyle: { color: split, type: 'dashed' } },
    },
  }
}

let registered = false
export function registerChartThemes() {
  if (registered) return
  echarts.registerTheme('talos-light', makeTheme(false))
  echarts.registerTheme('talos-dark', makeTheme(true))
  registered = true
}

export const chartThemeName = (dark: boolean) => (dark ? 'talos-dark' : 'talos-light')

// 从主色到透明的纵向面积渐变
export function areaGradient(hex: string) {
  return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: hex + '40' },
    { offset: 1, color: hex + '00' },
  ])
}

// 横向柱状渐变（浅色到主色）
export function barGradient(from = '#818cf8', to = '#6366f1') {
  return new echarts.graphic.LinearGradient(0, 0, 1, 0, [
    { offset: 0, color: from },
    { offset: 1, color: to },
  ])
}
