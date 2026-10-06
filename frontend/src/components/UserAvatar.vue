<template>
  <img v-if="avatarUrl" class="user-avatar" :src="avatarUrl" :width="size" :height="size" alt="" />
  <span v-else class="user-avatar fallback" :style="fallbackStyle" :title="name">{{ initial }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  avatar?: string
  avatarUrl?: string
  name?: string
  size?: number
}>(), {
  avatar: '',
  avatarUrl: '',
  name: '',
  size: 36,
})

const palette = ['#047857', '#0E7490', '#4338CA', '#7E22CE', '#BE185D', '#B45309', '#166534', '#334155']
const initial = computed(() => (props.name.trim()[0] || '?').toUpperCase())
const fallbackStyle = computed(() => {
  const hash = [...props.name].reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return { background: palette[hash % palette.length], width: `${props.size}px`, height: `${props.size}px` }
})
</script>

<style scoped>
.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  border-radius: 12px;
  object-fit: cover;
  color: #fff;
  font-weight: 700;
  line-height: 1;
}
.fallback { border-radius: 12px; }
</style>
