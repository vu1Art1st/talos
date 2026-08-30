<template>
  <!-- 品牌标志：主六边形轮廓 + 下方错位回声线（参考品牌图片重绘），颜色随 currentColor 自适应明暗 -->
  <svg :width="size" :height="size" viewBox="0 0 44 44" fill="none" aria-hidden="true">
    <path :d="echo" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity=".55" />
    <path :d="main" stroke="currentColor" stroke-width="3" stroke-linejoin="round" />
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 28 })

// 尖顶正六边形路径
function hexPath(cx: number, cy: number, r: number): string {
  const h = r * Math.sin(Math.PI / 3)
  const pts = [
    [cx, cy - r], [cx + h, cy - r / 2], [cx + h, cy + r / 2],
    [cx, cy + r], [cx - h, cy + r / 2], [cx - h, cy - r / 2],
  ]
  return 'M ' + pts.map((p) => p.map((n) => n.toFixed(2)).join(',')).join(' L ') + ' Z'
}

const main = hexPath(22, 18, 13)
// 回声线：下移错位六边形的下半段轮廓（左下棱 → 底边 → 右下棱）
const echo = (() => {
  const h = 13 * Math.sin(Math.PI / 3), d = 8, cy = 18, r = 13
  const pts = [
    [22 - h, cy + d - r / 2], [22 - h, cy + d + r / 2], [22, cy + d + r], [22 + h, cy + d + r / 2], [22 + h, cy + d - r / 2],
  ]
  return 'M ' + pts.map((p) => p.map((n) => n.toFixed(2)).join(',')).join(' L ')
})()
</script>
