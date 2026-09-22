<template>
  <div class="w-full flex flex-col gap-2">
    <div v-for="(_, uidx) in rows" :key="uidx"
         class="tl-url-row flex items-center gap-2" :class="{ 'is-invalid': invalidIndexes.includes(uidx) }"
         @paste="onPaste($event, uidx)">
      <el-input v-model="rows[uidx]" data-test="affected-url-input" :placeholder="placeholder"
                class="flex-1" :disabled="disabled" @input="onInput" />
      <el-button v-if="rows.length > 1" type="danger" link :disabled="disabled"
                 @click="removeRow(uidx)">
        <el-icon><Delete /></el-icon>
      </el-button>
    </div>
    <div class="flex items-center gap-2 min-w-0">
      <el-button size="small" plain :disabled="disabled" @click="addRow">
        <el-icon class="mr-1"><Plus /></el-icon>添加URL
      </el-button>
      <span v-if="hint" data-test="affected-url-hint" class="text-xs text-gray-400 truncate">{{ hint }}</span>
    </div>
    <div v-if="error" class="text-xs" style="color: var(--el-color-danger)">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
/**
 * 影响URL 多值编辑器（漏洞录入/编辑页与报告导入修正页共用）。
 *
 * v-model 始终是后端的「换行分隔单字段」口径字符串，调用方无需做数组与字符串互转。
 * 交互：每行一个输入框、行尾删除、底部「添加URL」；在任意行粘贴含换行或分号的文本时，
 * 自动按分隔符切分、去重后插入该行位置——单行 input 会丢弃换行，故必须在 paste 事件
 * 读取剪贴板原文，input 事件拿不到完整多行内容。
 * 校验（条数/单条长度/非法字符）与后端 `normalize_affected_url` 同一口径，行内展示不阻断输入。
 */
import { ref, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import {
  AFFECTED_URL_MAX_COUNT,
  cleanUrls,
  parseAffectedUrl,
  validateAffectedUrls,
} from '../utils/urls'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  disabled?: boolean
}>(), {
  placeholder: 'https://...',
  disabled: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

/** 行内容（保留空格与空行，避免输入过程中结构被规范化打乱） */
const rows = ref<string[]>(rowsFrom(props.modelValue))
const error = ref('')
const hint = ref('')
const invalidIndexes = ref<number[]>([])

/** 后端存储值 → 行数组：按换行切分（不做分号切分，避免破坏存量 URL 中合法的分号参数） */
function rowsFrom(raw: string | null | undefined): string[] {
  const arr = (raw ?? '').split('\n')
  return arr.length ? arr : ['']
}

/** 行数组 → 后端存储值：保持原始行结构（清洗交给提交前的 joinAffectedUrl 与后端校验） */
const rawJoin = (list: string[]) => list.join('\n')

function refreshValidation() {
  const result = validateAffectedUrls(cleanUrls(rows.value))
  error.value = result.ok ? '' : result.message
  invalidIndexes.value = result.invalidIndexes
}

function emitValue() {
  emit('update:modelValue', rawJoin(rows.value))
}

function onInput() {
  hint.value = ''
  refreshValidation()
  emitValue()
}

function addRow() {
  rows.value.push('')
  hint.value = ''
  refreshValidation()
  emitValue()
}

function removeRow(idx: number) {
  rows.value.splice(idx, 1)
  if (!rows.value.length) rows.value = ['']
  hint.value = ''
  refreshValidation()
  emitValue()
}

/**
 * 粘贴：含换行/分号时接管默认行为，按分隔符切分、去重后插入当前行位置。
 * - 当前行内容被整段选中视为「覆盖」，否则保留当前行内容并追加（避免误删已填数据）；
 * - 单值粘贴（无分隔符）交回浏览器默认行为，保留光标位置；
 * - 结果超过条数上限时整批拒绝（不静默丢弃），提示分批粘贴。
 */
function onPaste(event: ClipboardEvent, idx: number) {
  const text = event.clipboardData?.getData('text/plain') ?? ''
  if (!/[\r\n;；]/.test(text)) return
  event.preventDefault()

  const items = parseAffectedUrl(text)
  if (!items.length) return

  // 事件目标通常是 input 本身；行容器上触发时（如程序化派发）回退到行内 input
  const target = event.target as HTMLElement | null
  const input = (target?.tagName === 'INPUT' ? target : target?.querySelector?.('input') ?? null) as
    HTMLInputElement | null
  const selectsAll =
    !!input && input.value.length > 0
    && input.selectionStart === 0 && input.selectionEnd === input.value.length
  const head = rows.value.slice(0, idx)
  const tail = rows.value.slice(idx + 1)
  const current = selectsAll ? [] : [rows.value[idx] ?? '']

  const merged = cleanUrls([...head, ...current, ...items, ...tail])
  const addedCount = merged.length - cleanUrls([...head, ...current, ...tail]).length

  if (merged.length > AFFECTED_URL_MAX_COUNT) {
    refreshValidation()
    error.value = `本次粘贴识别出 ${items.length} 条，累计将超过 ${AFFECTED_URL_MAX_COUNT} 条上限，请分批粘贴`
    hint.value = ''
    return
  }

  rows.value = merged.length ? merged : ['']
  const dedup = items.length - addedCount
  hint.value = `已识别 ${items.length} 条${dedup > 0 ? `，已去重 ${dedup} 条` : ''}`
  refreshValidation()
  emitValue()
}

// 外部（表单回显/重置）改动时重建行结构；与本地未提交内容等价则不打断编辑
watch(() => props.modelValue, (value) => {
  if (rawJoin(rows.value) !== (value ?? '')) {
    rows.value = rowsFrom(value)
    hint.value = ''
    refreshValidation()
  }
})

refreshValidation()
</script>

<style scoped>
/* 不合规条目标红：与 el-form-item 的错误态视觉一致 */
.is-invalid :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px var(--el-color-danger) inset;
}
</style>
