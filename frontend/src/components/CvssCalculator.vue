<template>
  <div class="cvss-calculator">
    <div v-if="legacyVector" class="flex flex-wrap items-center gap-2">
      <span class="tl-tag" :style="softStyle(STAT_CARD_COLORS.gray)">存量 CVSS 3.1</span>
      <template v-if="result">
        <span class="text-2xl font-semibold tabular-nums" :style="{ color: severityColor }">
          {{ result.score.toFixed(1) }}
        </span>
        <span class="tl-tag" :style="softStyle(severityColor)">{{ result.severityLabel }}</span>
      </template>
      <el-button link type="primary" @click="startCvss40">按 CVSS 4.0 重新评分</el-button>
    </div>
    <div v-if="legacyVector" class="mt-1 truncate font-mono text-xs text-gray-500" :title="legacyVector">
      {{ legacyVector }}
    </div>

    <template v-else>
      <div class="grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-2 xl:grid-cols-3">
        <label v-for="def in CVSS_METRIC_DEFS" :key="def.key" class="flex min-w-0 items-center gap-2">
          <span class="w-[104px] shrink-0 text-xs text-gray-500">{{ def.label }}</span>
          <el-select v-model="metrics[def.key]" size="small" placeholder="未选" class="min-w-0 flex-1">
            <el-option v-for="opt in def.options" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </label>
      </div>
      <div class="mt-2 flex flex-wrap items-center gap-3">
        <span class="text-xs text-gray-500">CVSS 4.0</span>
        <span v-if="result" class="flex items-center gap-2">
          <span class="text-2xl font-semibold tabular-nums" :style="{ color: severityColor }">
            {{ result.score.toFixed(1) }}
          </span>
          <span class="tl-tag" :style="softStyle(severityColor)">{{ result.severityLabel }}</span>
        </span>
        <span v-else class="text-xs text-gray-400">请完整选择 11 项指标后计算评分</span>
        <span v-if="vectorText" class="min-w-0 flex-1 truncate font-mono text-xs text-gray-500" :title="vectorText">
          {{ vectorText }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { softStyle, levelColor, STAT_CARD_COLORS } from '../utils/colors'
import {
  CVSS_METRIC_DEFS,
  buildVector,
  computeBaseScore,
  emptyCvssMetrics,
  parseAnyVector,
  scoreFromVector,
  scoreToLevel,
  type CvssMetrics,
  type CvssResult,
} from '../utils/cvss'

const props = defineProps<{ vector: string; score: number }>()
const emit = defineEmits<{
  (e: 'update:vector', v: string): void
  (e: 'update:score', v: number): void
  (e: 'level-suggest', level: number): void
}>()

const metrics = reactive<CvssMetrics>(emptyCvssMetrics())
const legacy = ref<{ vector: string; result: CvssResult | null } | null>(null)

const vectorText = computed(() => buildVector(metrics))
const legacyVector = computed(() => legacy.value?.vector ?? '')
const result = computed(() => legacy.value?.result ?? (vectorText.value ? computeBaseScore(metrics) : null))

// 外部向量变化（编辑回显 / 套用知识库模板）时按版本回填。
watch(
  () => props.vector,
  (value) => {
    if (!legacy.value && value === vectorText.value) return
    const parsed = parseAnyVector(value)
    if (parsed?.version === '4.0') {
      legacy.value = null
      Object.assign(metrics, parsed.metrics)
      return
    }
    if (parsed?.version === '3.1') {
      Object.assign(metrics, emptyCvssMetrics())
      legacy.value = { vector: value.trim(), result: scoreFromVector(value) }
      return
    }
    Object.assign(metrics, emptyCvssMetrics())
    legacy.value = null
  },
  { immediate: true },
)

// 严重度色：复用平台等级色板（严重/高危/中危/低危），无风险用灰
const severityColor = computed(() => {
  if (!result.value) return 'var(--sage-11)'
  const level = scoreToLevel(result.value.score)
  return level !== null ? levelColor(level) : 'var(--sage-11)'
})

watch([result, vectorText], ([current, vector]) => {
  if (legacy.value) return
  const nextScore = current?.score ?? 0
  if (nextScore !== props.score) emit('update:score', nextScore)
  if (vector !== props.vector) emit('update:vector', vector)
  const level = scoreToLevel(nextScore)
  if (level !== null && current) emit('level-suggest', level)
})

function startCvss40() {
  legacy.value = null
  Object.assign(metrics, emptyCvssMetrics())
  emit('update:score', 0)
  emit('update:vector', '')
}
</script>
