<template>
  <div class="filter-builder">
    <FilterGroupEditor :group="tree" :fields="fields" :depth="1" root @change="onTreeChange" />

    <div class="filter-preview">
      <span class="filter-preview__label">实际生效条件</span>
      <code v-if="preview" class="filter-preview__text">{{ preview }}</code>
      <span v-else class="filter-preview__text filter-preview__text--empty">
        暂无有效条件（未填写完整的条件不会参与查询）
      </span>
      <span v-if="totalRules > effectiveRules" class="filter-preview__hint">
        另有 {{ totalRules - effectiveRules }} 条未填写完整，暂不生效
      </span>
    </div>

    <div class="filter-builder__foot">
      <span class="text-xs text-gray-400">
        分组内条件按「且 / 或」组合，分组可用「非」整体取反；分组可嵌套（最多 {{ MAX_FILTER_DEPTH }} 层），
        括号内的条件优先计算。
      </span>
      <el-button v-if="totalRules" size="small" text type="danger" @click="clearTree">清空全部</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { FilterFieldDef, FilterGroup } from '../types'
import {
  MAX_FILTER_DEPTH,
  cloneFilterNode,
  countFilterRules,
  createFilterGroup,
  describeFilterTree,
  filterTreeEquals,
  normalizeFilterTree,
  pruneFilterTree,
} from '../utils/filterTree'
import FilterGroupEditor from './FilterGroupEditor.vue'

/**
 * 聚合筛选条件树编辑器（v2：分组 + 嵌套 + 且/或/非）。
 *
 * 内部持有一份规范化副本，子树就地编辑后统一 emit `update:modelValue` + `change`（父级据此防抖查询）；
 * 外部回填值时按结构比较决定是否重建，避免输入过程中被无谓覆盖。
 */
const props = defineProps<{
  modelValue: FilterGroup
  fields: FilterFieldDef[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: FilterGroup): void
  (e: 'change'): void
}>()

const tree = ref<FilterGroup>(normalizeFilterTree(props.modelValue))
const totalRules = computed(() => countFilterRules(tree.value))
/** 实际参与查询的条件（剪枝后）与预览表达式同源，保证「所见即所查」 */
const pruned = computed(() => pruneFilterTree(tree.value))
const effectiveRules = computed(() => countFilterRules(pruned.value))
const preview = computed(() => describeFilterTree(pruned.value, props.fields))

watch(
  () => props.modelValue,
  (value) => {
    const next = normalizeFilterTree(value)
    if (!filterTreeEquals(next, tree.value)) tree.value = next
  },
  { deep: true },
)

function onTreeChange() {
  emit('update:modelValue', cloneFilterNode(tree.value))
  emit('change')
}

function clearTree() {
  tree.value = createFilterGroup()
  onTreeChange()
}
</script>

<style scoped>
.filter-preview {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 6px;
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid var(--tl-border, #e5e7eb);
  border-radius: 6px;
  background: var(--tl-fill, rgba(127, 127, 127, 0.06));
  font-size: 12px;
}
.filter-preview__label {
  color: var(--tl-text-3);
  white-space: nowrap;
}
.filter-preview__text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--tl-text-2);
  word-break: break-all;
}
.filter-preview__text--empty {
  color: var(--tl-text-3);
  font-family: inherit;
}
.filter-preview__hint {
  color: var(--tl-warning, #d97706);
}
.filter-builder__foot {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
}
</style>
