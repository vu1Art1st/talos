<template>
  <div>
    <!-- 只读模式：工单信息展示（默认入口，避免每次打开都进入编辑态） -->
    <div v-if="mode === 'view'">
      <div class="flex items-center mb-3">
        <span class="text-sm font-medium">工单信息</span>
        <div class="flex-1" />
        <el-button v-if="canEdit && plan" size="small" type="primary" plain
                   data-test="nonpen-info-edit" @click="emit('request-edit')">
          <el-icon class="mr-1"><Edit /></el-icon>编辑
        </el-button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-3 text-sm">
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">计划名称</div>
          <div>{{ plan?.plan_name || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">测试系统</div>
          <div>{{ plan?.system_name || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">测试类型</div>
          <div>{{ plan?.test_type || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">所属部门</div>
          <div>{{ plan?.department || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">工单ID</div>
          <div class="font-mono">{{ plan?.ticket_id || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">工单提起</div>
          <div>{{ plan?.ticket_time || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">需求接收</div>
          <div>{{ plan?.receive_time || '-' }}</div>
        </div>
        <div v-if="plan?.asset_names?.length" class="col-span-3">
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">关联资产</div>
          <div>{{ plan.asset_names.join('、') }}</div>
        </div>
        <div class="col-span-3">
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">测试项</div>
          <div class="flex flex-wrap gap-2">
            <span v-for="t in nonpenItems()" :key="t.key" class="inline-flex items-center gap-1">
              <span class="text-xs" style="color: var(--tl-text-3)">{{ t.name }}</span>
              <span class="tl-tag" :style="softStyle(nonpenItemMeta(statusOf(t.key)).color)">
                {{ nonpenItemMeta(statusOf(t.key)).label }}
              </span>
            </span>
          </div>
        </div>
        <div v-if="plan?.detail" class="col-span-3">
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">详细描述</div>
          <div class="whitespace-pre-wrap">{{ plan.detail }}</div>
        </div>
      </div>
    </div>

    <!-- 表单模式：新增（create）/ 抽屉内编辑（edit） -->
    <div v-else>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6">
          <el-form-item label="计划名称">
            <el-input v-model="form.plan_name" placeholder="与测试系统区分的漏扫基线工单名称" />
          </el-form-item>
          <el-form-item label="关联资产">
            <div class="w-full flex gap-2">
              <el-select v-model="form.asset_ids" multiple filterable remote clearable
                         :remote-method="searchAssets" :loading="assetLoading"
                         placeholder="输入资产名称搜索并选择，选择后自动带出测试系统与所属部门" class="flex-1"
                         @change="onAssetsChange">
                <el-option v-for="a in assetOptions" :key="a.id" :label="a.label" :value="a.id" />
              </el-select>
            </div>
          </el-form-item>
          <el-form-item label="测试系统" prop="system_name">
            <el-input v-model="form.system_name" placeholder="被测系统名称" />
          </el-form-item>
          <el-form-item label="测试类型">
            <el-select v-model="form.test_type" filterable clearable placeholder="请选择测试类型" class="w-full">
              <el-option v-for="t in testTypeOptions" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属部门">
            <el-select v-model="form.department" filterable clearable placeholder="请选择部门" class="w-full">
              <el-option v-for="d in departmentOptions" :key="d" :label="d" :value="d" />
            </el-select>
          </el-form-item>
          <el-form-item label="工单ID">
            <div class="w-full">
              <el-input v-model="form.ticket_id_manual"
                        placeholder="留空则按需求接收日期自动生成（如 20260810-1）" clearable />
              <div v-if="form.id && !form.ticket_id_manual && autoTicketId"
                   class="text-xs mt-1" style="color: var(--tl-text-3)">
                当前自动生成：{{ autoTicketId }}，留空保存即保持该值
              </div>
            </div>
          </el-form-item>
          <el-form-item label="工单提起">
            <el-date-picker v-model="form.ticket_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
          </el-form-item>
          <el-form-item label="需求接收" prop="receive_time">
            <el-date-picker v-model="form.receive_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
          </el-form-item>
        </div>
        <el-form-item label="测试项">
          <div class="w-full grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div v-for="t in nonpenItems()" :key="t.key" class="test-item-check"
                 :class="{ checked: form.test_items.includes(t.key) }" @click="toggleTestItem(t.key)">
              <div class="tick"><el-icon v-if="form.test_items.includes(t.key)" :size="13"><Check /></el-icon></div>
              <div>
                <div class="ti-name">{{ t.name }}</div>
                <div class="ti-desc">{{ t.desc }}</div>
              </div>
            </div>
          </div>
          <div class="text-xs mt-1" style="color: var(--tl-text-3)">未勾选的测试项将标记为「忽略」，不参与统计</div>
        </el-form-item>
        <el-form-item label="详细描述">
          <el-input v-model="form.detail" type="textarea" :rows="4" placeholder="扫描范围、数据来源等详细信息" />
        </el-form-item>
      </el-form>

      <div class="flex items-center gap-2 mt-2">
        <span v-if="saveState !== 'saved'" class="text-xs"
              :style="{ color: saveState === 'failed' ? 'var(--el-color-danger)' : 'var(--tl-text-3)' }">
          {{ AUTOSAVE_STATE_LABEL[saveState] }}
        </span>
        <div class="flex-1" />
        <el-button data-test="nonpen-info-cancel" @click="onCancel">取消</el-button>
        <el-button type="primary" :loading="saving" data-test="nonpen-info-save" @click="onSave">
          {{ mode === 'create' ? '创建' : '保存' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormItemRule, FormRules } from 'element-plus'
import { Check, Edit } from '@element-plus/icons-vue'
import client from '../api/client'
import { AUTOSAVE_STATE_LABEL, useAutosave } from '../composables/useAutosave'
import { useAssetSelect } from '../composables/useAssetSelect'
import { useDictOptions } from '../composables/useDictOptions'
import { nonpenItemMeta, nonpenItems, softStyle } from '../utils/colors'
import { registerUnsavedGuard } from '../utils/unsavedGuard'
import type { NonpenPlan, NonpenPlanForm } from '../types'

const props = withDefaults(defineProps<{
  plan?: NonpenPlan | null
  mode: 'view' | 'create' | 'edit'
  canEdit?: boolean
}>(), { plan: null, canEdit: true })

const emit = defineEmits<{
  (e: 'request-edit'): void
  (e: 'saved', plan: NonpenPlan): void
  (e: 'cancel'): void
}>()

const { testTypes, departments, loadTestTypes, loadDepartments } = useDictOptions()
const {
  assetOptions, assetLoading, assetCache, searchAssets,
  loadAssetLabels: loadAssetLabelsUncached, diffIds, resetBaseline,
} = useAssetSelect()

const emptyForm = (): NonpenPlanForm => ({
  id: null as number | null,
  plan_name: '',
  system_name: '',
  test_type: '',
  department: '',
  receive_time: '',
  ticket_time: '',
  ticket_id_manual: '',
  asset_ids: [] as number[],
  test_items: [] as string[],
  detail: '',
})

const form = ref<NonpenPlanForm>(emptyForm())
const formRef = ref<FormInstance>()
let hydrating = false
let savedPlan: NonpenPlan | null = null

const autoTicketId = computed(() => (form.value as { ticket_id?: string }).ticket_id ?? '')
const itemOf = (key: string) => props.plan?.items?.[key]
const statusOf = (key: string) => itemOf(key)?.status || 'not_started'

const requireTicketSource: FormItemRule['validator'] = (_rule, _value, callback) => {
  if (!form.value.ticket_id_manual && !form.value.receive_time) {
    callback(new Error('请填写「需求接收日期」（用于自动生成工单ID），或手动指定工单ID'))
  } else {
    callback()
  }
}
const formRules: FormRules = {
  system_name: [{ required: true, whitespace: true, message: '请填写测试系统', trigger: 'blur' }],
  receive_time: [{ validator: requireTicketSource }],
}

// 旧数据的值可能不在字典/组织列表中，临时追加以正常回显
const testTypeOptions = computed(() =>
  form.value.test_type && !testTypes.value.includes(form.value.test_type)
    ? [...testTypes.value, form.value.test_type]
    : testTypes.value)
const departmentOptions = computed(() =>
  form.value.department && !departments.value.includes(form.value.department)
    ? [...departments.value, form.value.department]
    : departments.value)

function selectedItems(row: NonpenPlan): string[] {
  const itemsMap = row.items ?? {}
  return nonpenItems()
    .filter((t) => itemsMap[t.key] && itemsMap[t.key].status !== 'ignored')
    .map((t) => t.key)
}

function toggleTestItem(key: string) {
  const i = form.value.test_items.indexOf(key)
  if (i >= 0) form.value.test_items.splice(i, 1)
  else form.value.test_items.push(key)
}

function loadAssetLabels() {
  return loadAssetLabelsUncached([...(form.value.asset_ids ?? [])])
}

// 点选关联资产后自动带出测试系统/所属部门（仅新增模式），仍可手动修改
function onAssetsChange(ids: number[]) {
  if (form.value.id) return
  const added = diffIds(ids)
  if (!added.length) return
  const asset = assetCache.value[added[added.length - 1]]
  if (!asset) return
  if (asset.name) form.value.system_name = asset.name
  if (asset.department) form.value.department = asset.department
}

async function doSave() {
  const body: Partial<NonpenPlanForm> = { ...form.value }
  delete body.id
  delete body.ticket_id
  delete body.ticket_seq
  delete body.items
  delete body.linked
  delete body.actionable
  delete body.testing_plan_id
  delete body.create_time
  delete body.update_time
  delete body.asset_names
  const { data } = form.value.id
    ? await client.put<NonpenPlan>(`/nonpen-plans/${form.value.id}`, body)
    : await client.post<NonpenPlan>('/nonpen-plans', body)
  savedPlan = data
}

const {
  state: saveState, saving, hasUnsaved, markDirty, saveNow, markSaved, confirmLeave, dispose: disposeAutosave,
} = useAutosave({ save: doSave, autoSave: false })

const unregisterGuard = registerUnsavedGuard(confirmLeave)

async function onSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const ok = await saveNow()
  if (!ok || !savedPlan) return
  ElMessage.success('保存成功')
  emit('saved', savedPlan)
  savedPlan = null
}

async function onCancel() {
  if (await confirmLeave()) emit('cancel')
}

function hydrate(plan?: NonpenPlan | null) {
  hydrating = true
  form.value = plan
    ? { ...emptyForm(), ...plan, test_items: selectedItems(plan) }
    : emptyForm()
  form.value.asset_ids = Array.isArray(form.value.asset_ids) ? [...form.value.asset_ids] : []
  assetOptions.value = []
  resetBaseline([...form.value.asset_ids])
  if (form.value.asset_ids.length) void loadAssetLabels()
  markSaved()
  void nextTick(() => { hydrating = false })
}

// 用户改动 → 进入 dirty（显式保存模式，不排自动保存）
watch(form, () => {
  if (!hydrating && props.mode !== 'view') markDirty()
}, { deep: true })

watch(
  () => [props.mode, props.plan?.id ?? null] as const,
  ([mode]) => {
    if (mode === 'view') {
      markSaved()
      return
    }
    hydrate(props.plan)
  },
  { immediate: true },
)

onMounted(async () => {
  await Promise.all([loadTestTypes(), loadDepartments()])
})

onBeforeUnmount(() => {
  unregisterGuard()
  disposeAutosave()
})

defineExpose({ confirmLeave, hasUnsaved })
</script>
