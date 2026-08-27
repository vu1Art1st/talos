<template>
  <el-dialog
    :model-value="modelValue"
    :close-on-click-modal="false"
    title="批量关联工单并确认"
    width="640px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div class="flex flex-wrap items-center gap-3">
      <el-select v-model="planId" filterable clearable placeholder="关联渗透测试工单（可选）"
                 class="flex-1 min-w-40" size="small">
        <el-option v-for="p in plans" :key="p.id" :label="planLabel(p)" :value="p.id" />
      </el-select>
      <el-select v-model="assetId" filterable clearable placeholder="入库到已有资产（可选）"
                 class="flex-1 min-w-40" size="small">
        <el-option v-for="a in filteredAssets" :key="a.id" :label="a.name" :value="a.id" />
      </el-select>
    </div>
    <div class="mt-3 text-xs text-gray-400 leading-5">
      将一次性确认所选 {{ batchIds.length }} 个批次并自动生成报告；所选批次的全部已解析记录将入库，
      同一工单下相同名称的漏洞自动去重合并。未选择工单时按系统名自动匹配/创建计划与资产。
    </div>
    <template #footer>
      <el-button :disabled="submitting" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">确认入库</el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts">
export interface BatchConfirmResult {
  confirmed: number
  skipped: number
  failed: number
  report_ids: number[]
  details: { batch_id: number; filename: string; status: string; detail: string }[]
}
</script>

<script setup lang="ts">
import { ref, watch } from 'vue'
import client from '../api/client'
import { usePlanAssetLink } from '../composables/usePlanAssetLink'

const props = defineProps<{
  modelValue: boolean
  batchIds: number[]
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'success', result: BatchConfirmResult): void
}>()

const plans = ref<any[]>([])
const assets = ref<any[]>([])
const submitting = ref(false)
const { planId, assetId, planLabel, filteredAssets } = usePlanAssetLink(
  () => plans.value,
  () => assets.value,
)

async function loadOptions() {
  const [{ data: assetPage }, { data: planPage }] = await Promise.all([
    client.get('/assets', { params: { size: 100 } }),
    // 无专项权限时静默降级为不可关联计划（与预览确认页行为一致）
    client.get('/testing-plans', { params: { size: 100 } }).catch(() => ({ data: { items: [] } })),
  ])
  assets.value = assetPage.items
  plans.value = planPage.items
}

async function submit() {
  if (!props.batchIds.length || submitting.value) return
  submitting.value = true
  try {
    const { data } = await client.post('/imports/batch-confirm', {
      batch_ids: props.batchIds,
      testing_plan_id: planId.value,
      asset_id: assetId.value,
    })
    emit('success', data as BatchConfirmResult)
  } finally {
    submitting.value = false
  }
}

watch(
  () => props.modelValue,
  async (v) => {
    if (!v) return
    if (!plans.value.length || !assets.value.length) await loadOptions()
  },
)
</script>
