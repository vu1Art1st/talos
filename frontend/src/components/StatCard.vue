<template>
  <!-- 全站统一统计卡（demo-2 紧凑密度）：容器/文字走 --tl-* 令牌，数值等宽字体，
       color 仅作标签前的语义点标（色值取 colors.ts，暗色自动降饱和） -->
  <div class="tl-stat-card border rounded-[10px]" style="border-color: var(--tl-border); background: var(--tl-surface)">
    <div class="flex items-center gap-1.5 text-xs text-gray-400">
      <i v-if="color" class="stat-dot" :style="{ '--c': color }"></i>
      <span>{{ label }}</span>
      <span v-if="$slots.extra" class="ml-auto"><slot name="extra" /></span>
    </div>
    <div class="num text-2xl font-bold mt-1.5" style="color: var(--tl-text-1)">
      <slot>{{ value ?? 0 }}</slot>
    </div>
    <div v-if="$slots.meta" class="mt-0.5 text-2xs text-gray-400 leading-4">
      <slot name="meta" />
    </div>
    <div v-if="$slots.spark" class="stat-spark">
      <slot name="spark" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  /** 标签前语义点标色（取 utils/colors.ts 的 STAT_CARD_COLORS 等既有色板，禁止散落硬编码） */
  color?: string
  value?: number | string
}>()
</script>

<style scoped>
.stat-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
  background: var(--c, var(--tl-text-3));
}
.stat-spark {
  margin: 8px -16px -14px;
  height: 38px;
  overflow: hidden;
  border-radius: 0 0 10px 10px;
}
.stat-spark :deep(svg) { width: 100%; height: 38px; display: block; }
</style>
