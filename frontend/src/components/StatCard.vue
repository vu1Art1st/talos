<template>
  <!-- 全站统一统计卡：容器/文字色走 --tl-* 令牌（自动适配暗黑），数值色走 colors.ts 唯一色源 -->
  <div class="tl-stat-card rounded-lg border" style="border-color: var(--tl-border); background: var(--tl-surface-2)">
    <div class="text-xs" style="color: var(--tl-text-3)">{{ label }}</div>
    <div class="text-2xl font-semibold" :style="{ color }">
      <slot>{{ value ?? 0 }}</slot>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  /** 数值颜色（取 utils/colors.ts 的 STAT_CARD_COLORS 等既有色板，禁止散落硬编码） */
  color?: string
  value?: number | string
}>()
</script>
