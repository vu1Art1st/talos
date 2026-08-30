<template>
  <!-- 轻量 SVG 迷你趋势线（demo-2 同款）：平滑曲线 + 纵向渐变面积 + 末端点，
       替代 Dashboard 曾用的 ECharts sparkline 实例（9 个 init/dispose → 纯 SVG 零开销） -->
  <svg :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" :stop-color="color" stop-opacity=".28" />
        <stop offset="1" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path :d="areaPath" :fill="`url(#${gid})`" />
    <path :d="linePath" fill="none" :stroke="color" stroke-width="2" stroke-linecap="round" />
    <circle v-if="lastPt" :cx="lastPt[0]" :cy="lastPt[1]" r="2.5" :fill="color" />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  points: number[]
  color?: string
}>(), { color: '#10b981' })

const W = 320
const H = 38
const P = 4

let seq = 0
const gid = `spark-${Math.random().toString(36).slice(2)}-${++seq}`

const pts = computed(() => {
  const data = props.points
  if (!data.length) return []
  const mn = Math.min(...data)
  const mx = Math.max(...data)
  return data.map((v, i) => [
    P + (W - 2 * P) * (i / (data.length - 1 || 1)),
    H - P - (H - 2 * P) * ((v - mn) / ((mx - mn) || 1)),
  ])
})
const lastPt = computed(() => pts.value.at(-1))

// Catmull-Rom → 三次贝塞尔平滑
const smooth = (list: number[][]) => {
  if (list.length < 2) return ''
  let d = `M ${list[0][0]},${list[0][1]}`
  for (let i = 0; i < list.length - 1; i++) {
    const p0 = list[Math.max(0, i - 1)], p1 = list[i], p2 = list[i + 1], p3 = list[Math.min(list.length - 1, i + 2)]
    const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6
    const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6
    d += ` C ${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`
  }
  return d
}

const linePath = computed(() => smooth(pts.value))
const areaPath = computed(() =>
  pts.value.length ? `${linePath.value} L ${W - P},${H} L ${P},${H} Z` : '',
)
</script>
