<template>
  <div class="filter-builder">
    <div v-if="!rules.length" class="py-6 text-center text-sm text-gray-400">
      暂无筛选条件，点击下方「添加条件」开始构建
    </div>

    <div v-for="(rule, i) in rules" :key="rule._uid" class="filter-row">
      <div class="connector-col">
        <span v-if="i === 0" class="connector-label">全部满足</span>
        <el-button
          v-else
          size="small"
          round
          :type="rule.connector === 'or' ? 'warning' : 'primary'"
          @click="toggleConnector(rule)"
        >
          {{ rule.connector === 'or' ? '或' : '且' }}
        </el-button>
      </div>

      <el-select
        v-model="rule.field"
        filterable
        class="filter-field"
        placeholder="选择字段"
        @change="onFieldChange(rule)"
      >
        <el-option v-for="f in fields" :key="f.key" :label="f.label" :value="f.key" />
      </el-select>

      <el-select
        v-model="rule.op"
        class="filter-op"
        placeholder="操作符"
        @change="onOpChange(rule)"
      >
        <el-option v-for="o in opOptions(rule)" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>

      <div class="filter-value">
        <template v-if="needsValue(rule)">
          <template v-if="rule.op === 'between'">
            <template v-if="fieldOf(rule)?.type === 'number'">
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
            v-else-if="fieldOf(rule)?.type === 'enum'"
            v-model="rule.value"
            filterable
            clearable
            placeholder="选择值"
            class="w-full"
          >
            <el-option
              v-for="o in fieldOf(rule)?.options ?? []"
              :key="String(o.value)"
              :label="o.label"
              :value="o.value"
            />
          </el-select>

          <el-select
            v-else-if="fieldOf(rule)?.options?.length"
            v-model="rule.value"
            filterable
            allow-create
            clearable
            default-first-option
            placeholder="输入或选择"
            class="w-full"
          >
            <el-option
              v-for="o in fieldOf(rule)!.options!"
              :key="String(o.value)"
              :label="o.label"
              :value="o.value"
            />
          </el-select>

          <el-input-number
            v-else-if="fieldOf(rule)?.type === 'number'"
            v-model="rule.value"
            :precision="2"
            :controls="false"
            placeholder="数值"
            class="w-full"
          />

          <el-date-picker
            v-else-if="fieldOf(rule)?.type === 'date'"
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

      <el-button size="small" text type="danger" @click="removeRule(i)">
        <el-icon><Close /></el-icon>
      </el-button>
    </div>

    <div class="flex items-center gap-2 mt-3">
      <el-button size="small" type="primary" plain @click="addRule">
        <el-icon class="mr-1"><Plus /></el-icon>添加条件
      </el-button>
      <el-button v-if="rules.length" size="small" text type="danger" @click="clearRules">
        清空
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Close, Plus } from '@element-plus/icons-vue'

export interface FilterFieldOption {
  label: string
  value: string | number
}

export interface FilterFieldDef {
  key: string
  label: string
  type: 'text' | 'number' | 'date' | 'enum'
  options?: FilterFieldOption[]
}

export interface FilterRule {
  field: string
  op: string
  value: string | number | (string | number | null)[] | null
  not: boolean
  connector: 'and' | 'or'
  _uid?: number
}

interface OpOption {
  value: string
  label: string
}

const OP_BY_TYPE: Record<FilterFieldDef['type'], OpOption[]> = {
  text: [
    { value: 'contains', label: '包含' },
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'starts_with', label: '开头为' },
    { value: 'ends_with', label: '结尾为' },
    { value: 'is_empty', label: '为空' },
  ],
  enum: [
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'is_empty', label: '为空' },
  ],
  number: [
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'gt', label: '大于' },
    { value: 'gte', label: '大于等于' },
    { value: 'lt', label: '小于' },
    { value: 'lte', label: '小于等于' },
    { value: 'between', label: '区间' },
    { value: 'is_empty', label: '为空' },
  ],
  date: [
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'gt', label: '晚于' },
    { value: 'gte', label: '不早于' },
    { value: 'lt', label: '早于' },
    { value: 'lte', label: '不晚于' },
    { value: 'between', label: '区间' },
    { value: 'is_empty', label: '为空' },
  ],
}

const DEFAULT_OP: Record<FilterFieldDef['type'], string> = {
  text: 'contains',
  enum: 'eq',
  number: 'eq',
  date: 'eq',
}

const props = defineProps<{
  modelValue: FilterRule[]
  fields: FilterFieldDef[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: FilterRule[]): void
  (e: 'change'): void
}>()

let uid = 1
function ensureUid(r: FilterRule): FilterRule {
  if (r._uid == null) r._uid = uid++
  return r
}
const rules = ref<FilterRule[]>(cloneRules(props.modelValue).map(ensureUid))

function cloneRules(list: FilterRule[]): FilterRule[] {
  return (list ?? []).map((r) => ({ ...r, value: cloneValue(r.value) }))
}

function cloneValue(v: FilterRule['value']): FilterRule['value'] {
  return Array.isArray(v) ? [...v] : v
}

function sameRules(a: FilterRule[] | undefined, b: FilterRule[]): boolean {
  if ((a?.length ?? 0) !== b.length) return false
  for (let i = 0; i < b.length; i++) {
    const x = a?.[i]
    const y = b[i]
    if (!x || x.field !== y.field || x.op !== y.op || x.not !== y.not ||
        x.connector !== y.connector || JSON.stringify(x.value) !== JSON.stringify(y.value)) {
      return false
    }
  }
  return true
}

watch(
  () => props.modelValue,
  (v) => {
    if (!sameRules(v, rules.value)) {
      rules.value = cloneRules(v ?? []).map(ensureUid)
    }
  },
  { deep: true },
)

watch(rules, () => {
  emit('update:modelValue', [...rules.value])
  emit('change')
}, { deep: true })

function fieldOf(rule: FilterRule): FilterFieldDef | undefined {
  return props.fields.find((f) => f.key === rule.field)
}

function opOptions(rule: FilterRule): OpOption[] {
  return OP_BY_TYPE[fieldOf(rule)?.type ?? 'text']
}

function needsValue(rule: FilterRule): boolean {
  return !['is_empty', 'is_not_empty'].includes(rule.op)
}

function betweenValue(rule: FilterRule): (string | number | null)[] {
  if (!Array.isArray(rule.value) || rule.value.length !== 2) rule.value = [null, null]
  return rule.value as (string | number | null)[]
}

function defaultRuleValue(field: FilterFieldDef | undefined, op: string): FilterRule['value'] {
  if (op === 'between') return [null, null]
  if (!needsValue({ field: '', op, value: null, not: false, connector: 'and' })) return null
  return field?.type === 'number' ? null : ''
}

function addRule() {
  const field = props.fields[0]
  if (!field) return
  const op = DEFAULT_OP[field.type]
  rules.value.push({
    _uid: uid++,
    field: field.key,
    op,
    value: defaultRuleValue(field, op),
    not: false,
    connector: 'and',
  })
}

function removeRule(index: number) {
  rules.value.splice(index, 1)
}

function clearRules() {
  rules.value = []
}

function onFieldChange(rule: FilterRule) {
  const field = fieldOf(rule)
  rule.op = DEFAULT_OP[field?.type ?? 'text']
  rule.value = defaultRuleValue(field, rule.op)
}

function onOpChange(rule: FilterRule) {
  rule.value = defaultRuleValue(fieldOf(rule), rule.op)
}

function toggleConnector(rule: FilterRule) {
  rule.connector = rule.connector === 'or' ? 'and' : 'or'
}
</script>

<style scoped>
.filter-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.connector-col {
  width: 64px;
  flex: none;
  display: flex;
  justify-content: center;
}
.connector-label {
  font-size: 12px;
  color: var(--tl-text-3);
  white-space: nowrap;
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
