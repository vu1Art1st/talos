<template>
  <div class="filter-row">
    <el-select
      v-model="rule.field"
      filterable
      class="filter-field"
      placeholder="选择字段"
      @change="onFieldChange"
    >
      <el-option v-for="f in fields" :key="f.key" :label="f.label" :value="f.key" />
    </el-select>

    <el-select v-model="rule.op" class="filter-op" placeholder="操作符" @change="onOpChange">
      <el-option v-for="o in opOptionsOf(rule, fields)" :key="o.value" :label="o.label" :value="o.value" />
    </el-select>

    <div class="filter-value">
      <template v-if="filterOpNeedsValue(rule.op)">
        <template v-if="rule.op === 'between'">
          <template v-if="fieldOf(fields, rule.field)?.type === 'number'">
            <el-input-number
              v-model="betweenValue(rule)[0]"
              :precision="2"
              :controls="false"
              class="w-24"
              placeholder="最小"
            />
            <span class="px-1 text-gray-400">~</span>
            <el-input-number
              v-model="betweenValue(rule)[1]"
              :precision="2"
              :controls="false"
              class="w-24"
              placeholder="最大"
            />
          </template>
          <el-date-picker
            v-else
            v-model="rule.value"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始"
            end-placeholder="结束"
            class="w-full"
          />
        </template>

        <el-select
          v-else-if="fieldOf(fields, rule.field)?.type === 'enum'"
          v-model="rule.value"
          filterable
          clearable
          placeholder="选择值"
          class="w-full"
        >
          <el-option
            v-for="o in fieldOf(fields, rule.field)?.options ?? []"
            :key="String(o.value)"
            :label="o.label"
            :value="o.value"
          />
        </el-select>

        <el-select
          v-else-if="fieldOf(fields, rule.field)?.options?.length"
          v-model="rule.value"
          filterable
          allow-create
          clearable
          default-first-option
          placeholder="输入或选择"
          class="w-full"
        >
          <el-option
            v-for="o in fieldOf(fields, rule.field)!.options!"
            :key="String(o.value)"
            :label="o.label"
            :value="o.value"
          />
        </el-select>

        <el-input-number
          v-else-if="fieldOf(fields, rule.field)?.type === 'number'"
          v-model="rule.value"
          :precision="2"
          :controls="false"
          placeholder="数值"
          class="w-full"
        />

        <el-date-picker
          v-else-if="fieldOf(fields, rule.field)?.type === 'date'"
          v-model="rule.value"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          class="w-full"
        />

        <el-input
          v-else
          v-model="rule.value"
          placeholder="输入筛选值"
          clearable
          class="w-full"
        />
      </template>
      <span v-else class="text-xs text-gray-400">（取值为空的记录）</span>
    </div>

    <el-tooltip content="取反（NOT）：排除满足该条件的记录">
      <el-button
        size="small"
        :type="rule.not ? 'danger' : 'default'"
        :plain="!rule.not"
        @click="rule.not = !rule.not"
      >
        非
      </el-button>
    </el-tooltip>

    <el-button size="small" text type="danger" @click="emit('remove')">
      <el-icon><Close /></el-icon>
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { Close } from '@element-plus/icons-vue'

import type { FilterFieldDef, FilterRule } from '../types'
import { applyFilterRuleField, applyFilterRuleOp, fieldOf, filterOpNeedsValue, opOptionsOf } from '../utils/filterTree'

// 单条筛选条件的行内编辑器：直接就地修改传入的 rule 对象（树由上层持有），
// 任何字段变化经 deep watch 统一冒泡 change，避免在每个控件上重复挂事件。
const props = defineProps<{
  rule: FilterRule
  fields: FilterFieldDef[]
}>()

const emit = defineEmits<{
  (e: 'change'): void
  (e: 'remove'): void
}>()

watch(() => props.rule, () => emit('change'), { deep: true })

/** 区间取值的两个输入框：形态非法时补成 [null, null]（历史/手改数据兜底） */
function betweenValue(rule: FilterRule): (string | number | null)[] {
  if (!Array.isArray(rule.value) || rule.value.length !== 2) rule.value = [null, null]
  return rule.value as (string | number | null)[]
}

function onFieldChange() {
  applyFilterRuleField(props.rule, props.fields)
}

function onOpChange() {
  applyFilterRuleOp(props.rule, props.fields)
}
</script>

<style scoped>
.filter-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.filter-field {
  width: 150px;
  flex: none;
}
.filter-op {
  width: 110px;
  flex: none;
}
.filter-value {
  flex: 1;
  min-width: 0;
}
/* el-date-editor 默认固定宽度（date 220px / daterange 350px）CSS 优先级高于 w-full，
   会撑破筛选值列覆盖右侧「非」按钮、或越出筛选气泡，强制按列宽自适应并允许收缩 */
.filter-value :deep(.el-date-editor) {
  width: 100% !important;
  min-width: 0 !important;
}
.filter-value :deep(.el-range-input) {
  min-width: 0 !important;
}
/* 区间选择器：容器 width 100% 与 input/select 外框宽度一致，内部 justify-content center 让
   日历图标+input×2+分隔符+× 居中显示；两个时间输入框固定 130px 避免均分大空间，padding 0 收紧 */
.filter-value :deep(.el-range-editor) {
  width: 100% !important;
  padding: 0;
  justify-content: center;
}
.filter-value :deep(.el-range-editor .el-range-input) {
  flex: none;
  width: 130px;
}
.filter-value :deep(.el-range-editor .el-range-separator) {
  flex: none;
  width: auto;
  padding: 0 4px;
}
.filter-value :deep(.el-range-editor .el-range__icon) {
  font-size: 13px;
  margin-right: 2px;
}
.filter-value :deep(.el-range-editor .el-range__close-icon) {
  margin-left: 2px;
}
</style>
