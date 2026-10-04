<template>
  <svg class="preset-avatar" :width="size" :height="size" viewBox="0 0 64 64" role="img" :aria-label="`预置头像 ${presetId}`">
    <rect width="64" height="64" rx="14" :fill="theme.bg" />
    <circle v-if="shape === 0" cx="32" cy="25" r="13" :fill="theme.fg" />
    <path v-else-if="shape === 1" d="M16 50c2-15 9-23 16-23s14 8 16 23z" :fill="theme.fg" />
    <path v-else-if="shape === 2" d="M32 12l18 11v22L32 56 14 45V23z" :fill="theme.fg" />
    <path v-else d="M15 42c7-2 12-5 17-13 5 8 10 11 17 13-2 9-8 14-17 14s-15-5-17-14z" :fill="theme.fg" />
    <circle cx="32" cy="32" r="22" fill="none" :stroke="theme.fg" stroke-opacity=".28" stroke-width="2" />
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ presetId?: string; size?: number }>(), {
  presetId: '01',
  size: 36,
})

const themes = [
  { bg: '#047857', fg: '#D1FAE5' },
  { bg: '#0E7490', fg: '#CFFAFE' },
  { bg: '#0369A1', fg: '#E0F2FE' },
  { bg: '#4338CA', fg: '#E0E7FF' },
  { bg: '#7E22CE', fg: '#F3E8FF' },
  { bg: '#BE185D', fg: '#FCE7F3' },
  { bg: '#C2410C', fg: '#FFEDD5' },
  { bg: '#B45309', fg: '#FEF3C7' },
  { bg: '#4D7C0F', fg: '#ECFCCB' },
  { bg: '#166534', fg: '#DCFCE7' },
  { bg: '#334155', fg: '#E2E8F0' },
  { bg: '#475569', fg: '#F1F5F9' },
]

const index = computed(() => {
  const value = Number.parseInt(props.presetId, 10)
  return Number.isFinite(value) && value >= 1 && value <= themes.length ? value - 1 : 0
})
const theme = computed(() => themes[index.value])
const shape = computed(() => index.value % 4)
</script>

<style scoped>
.preset-avatar { display: block; border-radius: 14px; }
</style>
