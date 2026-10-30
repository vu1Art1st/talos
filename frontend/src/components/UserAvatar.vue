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

const palette = [
  'var(--jade-9)', 'var(--sky-9)', 'var(--violet-9)', 'var(--pink-9)',
  'var(--orange-9)', 'var(--teal-9)', 'var(--grass-9)', 'var(--sage-9)',
]
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
  border-radius: 8px;
  object-fit: cover;
  color: var(--tl-on-primary);
  font-weight: 600;
  line-height: 1;
}
.fallback { border-radius: 8px; }
</style>
