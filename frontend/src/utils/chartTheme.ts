import * as echarts from 'echarts'
import {
  amber,
  amberDark,
  blue,
  blueDark,
  cyan,
  cyanDark,
  grass,
  grassDark,
  jade,
  jadeDark,
  orange,
  orangeDark,
  pink,
  pinkDark,
  red,
  redDark,
  ruby,
  rubyDark,
  sage,
  sageDark,
  sky,
  skyDark,
  teal,
  tealDark,
  violet,
  violetDark,
} from '@radix-ui/colors'

// ECharts 明 / 暗双主题（唯一图表主题源），与 style.css 令牌层视觉对齐
// 图表系列色唯一色源：视图内自定义系列色时必须引用 chartPalette，禁止散落硬编码
export function chartPalette(dark: boolean): string[] {
  return dark
    ? [
        jadeDark.jade9, skyDark.sky9, amberDark.amber9, redDark.red9,
        cyanDark.cyan9, violetDark.violet9, pinkDark.pink9, grassDark.grass9,
      ]
    : [
        jade.jade9, sky.sky9, amber.amber9, red.red9,
        cyan.cyan9, violet.violet9, pink.pink9, grass.grass9,
      ]
}

export function chartNeutral(dark: boolean) {
  const scale = dark ? sageDark : sage
  return {
    text: scale.sage12,
    muted: scale.sage11,
    split: scale.sage6,
    surface: scale.sage2,
  }
}

const CHART_LIGHT_BY_FAMILY = {
  sage: sage.sage9,
  jade: jade.jade9,
  red: red.red9,
  orange: orange.orange9,
  amber: amber.amber9,
  sky: sky.sky9,
  blue: blue.blue9,
  ruby: ruby.ruby9,
  violet: violet.violet9,
  pink: pink.pink9,
  cyan: cyan.cyan9,
  teal: teal.teal9,
  grass: grass.grass9,
} as const

const CHART_DARK_BY_FAMILY = {
  sage: sageDark.sage9,
  jade: jadeDark.jade9,
  red: redDark.red9,
  orange: orangeDark.orange9,
  amber: amberDark.amber9,
  sky: skyDark.sky9,
  blue: blueDark.blue9,
  ruby: rubyDark.ruby9,
  violet: violetDark.violet9,
  pink: pinkDark.pink9,
  cyan: cyanDark.cyan9,
  teal: tealDark.teal9,
  grass: grassDark.grass9,
} as const

/** Canvas 无法解析 CSS 变量，ECharts 配置必须使用 Radix 运行时色值。 */
export function chartColorFor(color: string, dark: boolean): string {
  const family = (
    color.match(/--(sage|jade|red|orange|amber|sky|blue|ruby|violet|pink|cyan|teal|grass)-/)?.[1] ?? 'sage'
  ) as
    keyof typeof CHART_LIGHT_BY_FAMILY
  return dark ? CHART_DARK_BY_FAMILY[family] : CHART_LIGHT_BY_FAMILY[family]
}

export const PALETTE = chartPalette(false)

function makeTheme(dark: boolean) {
  const neutral = chartNeutral(dark)
  return {
    color: chartPalette(dark),
    textStyle: { color: neutral.muted, fontSize: 12 },
    legend: { textStyle: { color: neutral.muted, fontSize: 12 }, icon: 'circle', itemWidth: 8, itemHeight: 8 },
    tooltip: {
      backgroundColor: neutral.surface,
      borderColor: neutral.split,
      borderWidth: 0.5,
      padding: [10, 14],
      textStyle: { color: neutral.text, fontSize: 14 },
      extraCssText: 'box-shadow: 0 8px 24px var(--sage-a7); border-radius: 8px;',
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: neutral.split, width: 0.5 } },
      axisTick: { show: false },
      axisLabel: { color: neutral.muted, fontSize: 12 },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: neutral.muted, fontSize: 12 },
      splitLine: { lineStyle: { color: neutral.split, width: 0.5, type: 'dashed' } },
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
export function areaGradient(color: string) {
  return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: color + '40' },
    { offset: 1, color: color + '00' },
  ])
}
