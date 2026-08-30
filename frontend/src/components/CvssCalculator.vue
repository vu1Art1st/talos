<template>
  <div class="cvss-calculator">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-2">
      <label v-for="def in CVSS_METRIC_DEFS" :key="def.key" class="flex items-center gap-1">
        <span class="w-[72px] shrink-0 text-xs text-gray-500">{{ def.label }}</span>
        <el-select v-model="metrics[def.key]" size="small" :placeholder="'未选'">
          <el-option v-for="opt in def.options" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </label>
    </div>
    <div class="mt-2 flex flex-wrap items-center gap-3">
      <span v-if="result" class="flex items-center gap-2">
        <span class="text-2xl font-semibold tabular-nums" :style="{ color: severityColor }">
          {{ result.score.toFixed(1) }}
        </span>
        <span class="tl-tag" :style="softStyle(severityColor)">{{ result.severityLabel }}</span>
      </span>
      <span v-else class="text-xs text-gray-400">请完整选择 8 项指标后计算评分</span>
      <span v-if="vectorText" class="min-w-0 flex-1 truncate font-mono text-xs text-gray-500" :title="vectorText">
        {{ vectorText }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { softStyle, levelColor } from '../utils/colors'
import {
  CVSS_METRIC_DEFS,
  buildVector,
  computeBaseScore,
  parseVector,
  scoreToLevel,
  type CvssMetrics,
} from '../utils/cvss'

const props = defineProps<{ vector: string; score: number }>()
const emit = defineEmits<{
  (e: 'update:vector', v: string): void
  (e: 'update:score', v: number): void
  (e: 'level-suggest', level: number): void
}>()

const metrics = reactive<CvssMetrics>({
  AV: '', AC: '', PR: '', UI: '', S: '', C: '', I: '', A: '',
})

// 外部向量变化（编辑回显 / 套用知识库模板）时回填指标
watch(
  () => props.vector,
  (v) => {
    if (v === buildVector(metrics)) return
    const parsed = parseVector(v)
    Object.assign(metrics, parsed ?? { AV: '', AC: '', PR: '', UI: '', S: '', C: '', I: '', A: '' })
  },
  { immediate: true },
)

const vectorText = computed(() => buildVector(metrics))
const result = computed(() => {
  if (!vectorText.value) return null
  return computeBaseScore(metrics)
})

// 严重度色：复用平台等级色板（严重/高危/中危/低危），无风险用灰
const severityColor = computed(() => {
  if (!result.value) return '#8a968f'
  const lv = scoreToLevel(result.value.score)
  return lv !== null ? levelColor(lv) : '#8a968f'
})

watch(result, (r) => {
  const score = r?.score ?? 0
  if (score !== props.score) emit('update:score', score)
  const vector = vectorText.value
  if (vector !== props.vector) emit('update:vector', vector)
  const level = scoreToLevel(score)
  if (level !== null && r) emit('level-suggest', level)
})
</script>
