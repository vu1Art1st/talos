<template>
  <!-- 导入等级不一致提醒：导入预览页与批量确认对话框共用（单场景仅一层弹窗） -->
  <el-dialog
    :model-value="modelValue"
    :close-on-click-modal="false"
    title="风险汇总与风险详情等级不一致"
    width="720px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div class="text-sm text-gray-500 leading-6 mb-3">
      以下 <b>{{ items.length }}</b> 条漏洞的「风险问题汇总」与「风险问题详情」对不上
      （等级不一致，或汇总表中找不到对应漏洞）。系统将以<b>风险问题详情</b>的等级为准入库，
      请核对后再继续。
    </div>
    <el-table :data="items" size="small" max-height="320" border>
      <el-table-column v-if="showBatch" prop="filename" label="来源批次" min-width="170" show-overflow-tooltip />
      <el-table-column prop="title" label="漏洞名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="风险汇总" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.level_summary != null" class="dot-tag" :style="levelDotStyle(row.level_summary)">
            <i></i>{{ row.level_summary_text }}
          </span>
          <span v-else class="text-gray-400 text-xs">未匹配</span>
        </template>
      </el-table-column>
      <el-table-column label="风险详情（采用）" width="130" align="center">
        <template #default="{ row }">
          <span v-if="row.level != null" class="dot-tag" :style="levelDotStyle(row.level)">
            <i></i>{{ row.level_detail_text || '—' }}
          </span>
          <span v-else class="text-gray-400 text-xs">—</span>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button v-if="cancelText" :disabled="loading" @click="emit('update:modelValue', false)">
        {{ cancelText }}
      </el-button>
      <el-button type="primary" :loading="loading" @click="emit('confirm')">{{ confirmText }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { levelDotStyle } from '../utils/colors'

withDefaults(defineProps<{
  modelValue: boolean
  items: any[]
  showBatch?: boolean
  confirmText?: string
  cancelText?: string
  loading?: boolean
}>(), {
  showBatch: false,
  confirmText: '我知道了',
  cancelText: '',
  loading: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm'): void
}>()
</script>
