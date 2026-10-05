<template>
  <div>
    <!-- 只读模式：工单信息展示（默认入口，避免每次打开都进入编辑态） -->
    <div v-if="mode === 'view'">
      <div class="flex items-center mb-3">
        <span class="text-sm font-medium">工单信息</span>
        <div class="flex-1" />
        <el-button v-if="canOperate && plan" size="small" type="primary" plain
                   data-test="plan-info-edit" @click="emit('request-edit')">
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
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">测试状态</div>
          <div>
            <span v-if="plan" class="tl-tag" :style="planStatusSoftStyle(plan.status)">
              {{ statusMap?.[plan.status] ?? plan.status }}
            </span>
          </div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">工单提起</div>
          <div>{{ plan?.ticket_time || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">需求接收</div>
          <div>{{ plan?.receive_time || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">初测完成</div>
          <div>{{ plan?.first_test_done_time || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">复测通知</div>
          <div>{{ plan?.retest_notice_time || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">复测完成</div>
          <div>{{ plan?.retest_done_time || '-' }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">测试人员</div>
          <div>
            <span v-if="plan?.testers?.length">
              {{ plan.testers.map((u) => u.realname || u.username).join('、') }}
            </span>
            <span v-else class="text-gray-400">未认领</span>
          </div>
        </div>
        <div v-if="plan?.asset_ids?.length" class="col-span-3">
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">关联资产</div>
          <div>{{ assetLabels.length ? assetLabels.join('、') : plan.asset_ids.join('、') }}</div>
        </div>
        <div class="col-span-3">
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">漏洞统计</div>
          <div class="flex flex-wrap gap-2">
            <span class="tl-tag" :style="levelSoftStyle(10)">超危 {{ plan?.stat_critical ?? 0 }}</span>
            <span class="tl-tag" :style="levelSoftStyle(20)">高危 {{ plan?.stat_high ?? 0 }}</span>
            <span class="tl-tag" :style="levelSoftStyle(30)">中危 {{ plan?.stat_medium ?? 0 }}</span>
            <span class="tl-tag" :style="levelSoftStyle(40)">低危 {{ plan?.stat_low ?? 0 }}</span>
          </div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">预估人天</div>
          <div>{{ plan?.est_mandays ?? 0 }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">实际人天</div>
          <div>{{ plan?.actual_mandays ?? 0 }}</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">复测轮数</div>
          <div>{{ plan?.retest_round_count ?? 0 }} 轮</div>
        </div>
        <div>
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">漏洞 / 报告</div>
          <div>{{ plan?.vuls?.length ?? 0 }} / {{ plan?.reports?.length ?? 0 }}</div>
        </div>
        <div v-if="plan?.target_urls?.length" class="col-span-3">
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">被测系统URL</div>
          <div class="break-all">{{ plan.target_urls.join('、') }}</div>
        </div>
        <div v-if="plan?.detail" class="col-span-3">
          <div class="text-xs mb-1" style="color: var(--tl-text-3)">详细描述</div>
          <div class="whitespace-pre-wrap">{{ plan.detail }}</div>
        </div>
      </div>
    </div>

    <!-- 表单模式：新增（create）/ 抽屉内编辑（edit） -->
    <div v-else>
      <el-form ref="formRef" :model="form" :rules="planRules" label-width="90px">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-x-4">
          <el-form-item label="计划名称">
            <el-input v-model="form.plan_name" placeholder="与测试系统区分的渗透测试工单名称" />
          </el-form-item>
          <el-form-item label="关联资产">
            <div class="w-full flex gap-2">
              <el-select v-model="form.asset_ids" multiple filterable remote clearable
                         :remote-method="searchAssets" :loading="assetLoading"
                         placeholder="输入资产名称搜索并选择，漏洞录入时将自动带入" class="flex-1"
                         @change="onAssetsChange">
                <el-option v-for="a in assetOptions" :key="a.id" :label="a.label" :value="a.id" />
              </el-select>
              <el-button v-if="!form.id" @click="openCreateAsset">
                <el-icon class="mr-1"><Plus /></el-icon>新增资产
              </el-button>
            </div>
          </el-form-item>
          <el-form-item label="测试系统" prop="system_name">
            <el-input v-model="form.system_name" placeholder="影响报告首页名称" />
          </el-form-item>
          <el-form-item label="工单ID">
            <div class="w-full">
              <el-input v-model="form.ticket_id_manual" placeholder="留空则按需求接收日期自动生成（如 20260727-1）"
                        clearable />
              <div v-if="form.id && !form.ticket_id_manual && form.ticket_id"
                   class="text-xs text-gray-400 mt-1">当前自动生成：{{ form.ticket_id }}，留空保存即保持该值</div>
            </div>
          </el-form-item>
          <el-form-item label="测试类型">
            <el-select v-model="form.test_type" filterable clearable placeholder="请选择测试类型" class="w-full">
              <el-option v-for="t in testTypeOptions" :key="t" :label="t" :value="t" />
              <template #footer>
                <el-button size="small" type="primary" link @click="addTestType">
                  <el-icon class="mr-1"><Plus /></el-icon>新增测试类型
                </el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="所属部门">
            <el-select v-model="form.department" filterable clearable placeholder="请选择部门" class="w-full">
              <el-option v-for="d in departmentOptions" :key="d" :label="d" :value="d" />
              <template #footer>
                <el-button size="small" type="primary" link @click="addDepartment">
                  <el-icon class="mr-1"><Plus /></el-icon>新增部门
                </el-button>
              </template>
            </el-select>
          </el-form-item>
          <el-form-item label="测试状态">
            <el-select v-model="form.status" class="w-full" :disabled="!statusEditable">
              <el-option v-for="(name, code) in statusMap" :key="code" :label="name" :value="Number(code)"
                         :disabled="statusOptionDisabled(Number(code))" />
            </el-select>
          </el-form-item>
          <el-form-item label="工单提起">
            <el-date-picker v-model="form.ticket_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
          </el-form-item>
          <el-form-item label="需求接收" prop="receive_time">
            <el-date-picker v-model="form.receive_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
          </el-form-item>
          <el-form-item label="初测完成">
            <el-date-picker v-model="form.first_test_done_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
          </el-form-item>
          <el-form-item label="复测通知">
            <el-date-picker v-model="form.retest_notice_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
          </el-form-item>
          <el-form-item label="复测完成">
            <el-date-picker v-model="form.retest_done_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
          </el-form-item>
          <el-form-item label="超危数">
            <el-input-number v-model="form.stat_critical" :min="0" class="!w-full" :disabled="statsAuto" />
          </el-form-item>
          <el-form-item label="高危数">
            <el-input-number v-model="form.stat_high" :min="0" class="!w-full" :disabled="statsAuto" />
          </el-form-item>
          <el-form-item label="中危数">
            <el-input-number v-model="form.stat_medium" :min="0" class="!w-full" :disabled="statsAuto" />
          </el-form-item>
          <el-form-item label="低危数">
            <el-input-number v-model="form.stat_low" :min="0" class="!w-full" :disabled="statsAuto" />
          </el-form-item>
          <el-form-item label="预估人天">
            <el-input-number v-model="form.est_mandays" :min="0" :precision="1" :step="0.5" class="!w-full" />
          </el-form-item>
          <el-form-item label="实际人天">
            <div class="w-full flex gap-2">
              <el-input-number v-model="form.actual_mandays" :min="0" :precision="1" :step="0.5" class="flex-1"
                               :disabled="mandaysAuto && !form.actual_mandays_override" />
              <el-button v-if="mandaysAuto && !form.actual_mandays_override" @click="onCorrectMandays">修正</el-button>
              <el-button v-if="mandaysAuto && form.actual_mandays_override" type="warning" plain
                         @click="onCancelMandays">取消修正</el-button>
            </div>
          </el-form-item>
        </div>
        <div v-if="mandaysAuto && !form.actual_mandays_override" class="text-xs text-gray-400 mb-2 pl-[100px]">
          有关联初测报告，实际人天由系统按初测报告测试周期自动计算（复测报告不计入）
        </div>
        <div v-else-if="mandaysAuto && form.actual_mandays_override"
             class="text-xs text-gray-400 mb-2 pl-[100px]">
          已手动修正实际人天，不再随初测报告自动更新；点击「取消修正」恢复系统自动计算
        </div>
        <div v-if="statsAuto" class="text-xs text-gray-400 mb-2 pl-[100px]">
          已有关联漏洞，统计由系统按漏洞等级自动重算
        </div>
        <div v-if="form.id && !statusEditable" class="text-xs text-gray-400 mb-2 pl-[100px]">
          认领该计划后才可修改测试状态
        </div>
        <!-- 创建漏扫基线工单：勾选后展开测试项；保存时自动同步新增漏扫基线工单 -->
        <el-form-item v-if="mode === 'create'" label=" " prop="nonpen_test_items" class="!mb-4">
          <div class="w-full">
            <div class="tp-create-head" :class="{ on: form.create_nonpen }" @click="toggleCreateNonpen">
              <div class="tp-create-check">
                <el-icon v-if="form.create_nonpen" :size="14"><Check /></el-icon>
              </div>
              <span class="tp-create-title">创建漏扫基线工单</span>
              <span class="tp-create-desc">勾选后展开测试项；保存时自动同步漏扫基线工单</span>
            </div>
            <div v-if="form.create_nonpen" class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
              <div v-for="t in nonpenItems()" :key="t.key" class="test-item-check"
                   :class="{ checked: form.nonpen_test_items.includes(t.key) }" @click="toggleNonpenItem(t.key)">
                <div class="tick"><el-icon v-if="form.nonpen_test_items.includes(t.key)" :size="13"><Check /></el-icon></div>
                <div>
                  <div class="ti-name">{{ t.name }}</div>
                  <div class="ti-desc">{{ t.desc }}</div>
                </div>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="被测系统URL">
          <div class="w-full">
            <el-select v-model="form.target_urls" multiple filterable allow-create default-first-option
                       :reserve-keyword="false" placeholder="选择关联资产后自动带出，也可输入URL回车添加"
                       class="w-full" />
            <div class="text-xs text-gray-400 mt-1">用于报告「测试目标」的被测系统URL/域名；自动带出后可删除，保存后以本列表为准</div>
          </div>
        </el-form-item>
        <el-form-item label="详细描述">
          <el-input v-model="form.detail" type="textarea" :rows="4" placeholder="数据来源等详细信息" />
        </el-form-item>
      </el-form>

      <div class="flex items-center gap-2 mt-2">
        <span v-if="saveState !== 'saved'" class="text-xs"
              :style="{ color: saveState === 'failed' ? 'var(--el-color-danger)' : 'var(--tl-text-3)' }">
          {{ AUTOSAVE_STATE_LABEL[saveState] }}
        </span>
        <div class="flex-1" />
        <el-button data-test="plan-info-cancel" @click="onCancel">取消</el-button>
        <el-button type="primary" :loading="saving" data-test="plan-info-save" @click="onSave">
          {{ mode === 'create' ? '创建' : '保存' }}
        </el-button>
      </div>

      <AssetFormDialog v-model:visible="assetDialogVisible" :asset="assetPrefill" @saved="onAssetCreated" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormItemRule, FormRules } from 'element-plus'
import { Check, Edit, Plus } from '@element-plus/icons-vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { AUTOSAVE_STATE_LABEL, useAutosave } from '../composables/useAutosave'
import { useAssetSelect } from '../composables/useAssetSelect'
import { useDictOptions } from '../composables/useDictOptions'
import { levelSoftStyle, nonpenItems, planStatusSoftStyle } from '../utils/colors'
import { assetUrls, cleanUrls, mergeUrls } from '../utils/urls'
import { registerUnsavedGuard } from '../utils/unsavedGuard'
import type { Asset, TestingPlan } from '../types'
import AssetFormDialog from './AssetFormDialog.vue'

const props = withDefaults(defineProps<{
  plan?: TestingPlan | null
  mode: 'view' | 'create' | 'edit'
  statusMap?: Record<number, string>
}>(), { plan: null, statusMap: () => ({}) })

const emit = defineEmits<{
  (e: 'request-edit'): void
  (e: 'saved', plan: TestingPlan): void
  (e: 'cancel'): void
}>()

const auth = useAuthStore()
const { testTypes, departments, loadTestTypes, loadDepartments } = useDictOptions()
const {
  assetOptions, assetLoading, assetCache,
  searchAssets, loadAssetLabels: loadAssetLabelsUncached, cacheAsset, diffIds, resetBaseline, lastKeyword,
} = useAssetSelect()
const assetDialogVisible = ref(false)
const assetPrefill = ref<Partial<Asset> | null>(null)

const emptyForm = (): TestingPlan => ({
  id: null as number | null,
  plan_name: '',
  system_name: '',
  test_type: '',
  department: '',
  receive_time: '',
  ticket_time: '',
  ticket_id_manual: '',
  first_test_done_time: '',
  retest_notice_time: '',
  retest_done_time: '',
  status: 10,
  asset_ids: [] as number[],
  stat_critical: 0,
  stat_high: 0,
  stat_medium: 0,
  stat_low: 0,
  est_mandays: 0,
  actual_mandays: 0,
  actual_mandays_override: false,
  create_nonpen: false,
  nonpen_test_items: [] as string[],
  target_urls: [] as string[],
  detail: '',
})

const form = ref<TestingPlan>(emptyForm())
const formRef = ref<FormInstance>()
let hydrating = false
let savedPlan: TestingPlan | null = null

const isAdmin = computed(() => auth.user?.permissions?.includes('*') ?? false)
const isTester = computed(() => props.plan?.testers?.some((u) => u.id === auth.user?.id) ?? false)
const canOperate = computed(() => isAdmin.value || isTester.value)
const statusEditable = computed(() => (form.value.id ? canOperate.value : isAdmin.value))

const canResetToUntested = computed(() => Boolean(
  props.plan
  && isAdmin.value
  && form.value.status === 20
  && !(props.plan.testers?.length)
  && !(props.plan.vuls?.length)
  && !(props.plan.reports?.length)
  && !(props.plan.retest_rounds?.length),
))

function statusOptionDisabled(code: number) {
  if (code !== 10 || !form.value.id || form.value.status === 10) return false
  return !canResetToUntested.value
}

const statsAuto = computed(() => (props.plan?.vuls?.length ?? 0) > 0)
const mandaysAuto = computed(() =>
  (props.plan?.reports ?? []).some((r) => !(r.title || '').includes('复测')))
const autoMandays = computed(() =>
  (props.plan?.reports ?? [])
    .filter((r) => !(r.title || '').includes('复测'))
    .reduce((s, r) => s + (r.actual_mandays ?? 0), 0))

function onCorrectMandays() {
  form.value.actual_mandays_override = true
}

function onCancelMandays() {
  form.value.actual_mandays_override = false
  form.value.actual_mandays = autoMandays.value
}

const requireNonpenItems: FormItemRule['validator'] = (_rule, value, callback) => {
  if (!form.value.id && form.value.create_nonpen && !(value ?? []).length) {
    callback(new Error('已勾选「创建漏扫基线工单」，请至少选择一个非渗透测试项'))
  } else {
    callback()
  }
}
const requireTicketSource: FormItemRule['validator'] = (_rule, _value, callback) => {
  if (!form.value.id && form.value.create_nonpen && !form.value.ticket_id_manual && !form.value.receive_time) {
    callback(new Error('已勾选「创建漏扫基线工单」，请填写「需求接收日期」（用于生成共享工单ID）或手动指定工单ID'))
  } else {
    callback()
  }
}
const planRules: FormRules = {
  system_name: [{ required: true, whitespace: true, message: '请填写测试系统', trigger: 'blur' }],
  nonpen_test_items: [{ validator: requireNonpenItems }],
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
const assetLabels = computed(() => assetOptions.value.map((o) => o.label))

function toggleCreateNonpen() {
  form.value.create_nonpen = !form.value.create_nonpen
  if (!form.value.create_nonpen) form.value.nonpen_test_items = []
}

function toggleNonpenItem(key: string) {
  const i = form.value.nonpen_test_items.indexOf(key)
  if (i >= 0) form.value.nonpen_test_items.splice(i, 1)
  else form.value.nonpen_test_items.push(key)
}

function loadAssetLabels(ids: number[]) {
  return loadAssetLabelsUncached([...ids])
}

function openCreateAsset() {
  assetPrefill.value = lastKeyword() ? { name: lastKeyword() } : null
  assetDialogVisible.value = true
}

function onAssetCreated(asset: Asset) {
  if (!asset?.id) return
  cacheAsset(asset)
  if (!form.value.asset_ids.includes(asset.id)) form.value.asset_ids.push(asset.id)
  form.value.system_name = asset.name
  form.value.department = asset.department || ''
  form.value.target_urls = mergeUrls(form.value.target_urls, assetUrls(asset))
  resetBaseline([...form.value.asset_ids])
}

// 点选资产自动带出被测系统URL；新建模式另带出测试系统/部门
function onAssetsChange(ids: number[]) {
  const added = diffIds(ids)
  if (added.length) {
    form.value.target_urls = mergeUrls(
      form.value.target_urls,
      added.flatMap((id) => assetUrls(assetCache.value[id])),
    )
  }
  if (form.value.id || !added.length) return
  const asset = assetCache.value[added[added.length - 1]]
  if (!asset) return
  form.value.system_name = asset.name
  form.value.department = asset.department || ''
}

async function addTestType() {
  const { value } = await ElMessageBox.prompt('请输入新的测试类型名称', '新增测试类型', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/dict/test_type', { name: value.trim() })
  ElMessage.success('新增测试类型成功')
  await loadTestTypes()
  form.value.test_type = value.trim()
}

async function addDepartment() {
  const { value } = await ElMessageBox.prompt('请输入新的部门（组织）名称', '新增部门', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/groups', { name: value.trim(), remark: '' })
  ElMessage.success('新增部门成功')
  await loadDepartments()
  form.value.department = value.trim()
}

async function doSave() {
  const body: Record<string, unknown> = { ...form.value }
  delete body.testers
  delete body.vuls
  delete body.reports
  delete body.retest_round_count
  delete body.ticket_id
  delete body.ticket_seq
  body.target_urls = cleanUrls(form.value.target_urls)
  if (form.value.id) {
    delete body.create_nonpen
    delete body.nonpen_test_items
    const { data } = await client.put<TestingPlan>(`/testing-plans/${form.value.id}`, body)
    savedPlan = data
  } else {
    const { data } = await client.post<TestingPlan>('/testing-plans', body)
    savedPlan = data
  }
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

function hydrate(plan?: TestingPlan | null) {
  hydrating = true
  form.value = plan ? { ...emptyForm(), ...plan } : emptyForm()
  form.value.asset_ids = Array.isArray(form.value.asset_ids) ? [...form.value.asset_ids] : []
  form.value.target_urls = Array.isArray(form.value.target_urls) ? [...form.value.target_urls] : []
  assetOptions.value = []
  resetBaseline([...form.value.asset_ids])
  if (form.value.asset_ids.length) {
    void loadAssetLabels(form.value.asset_ids).then(() => {
      if (!form.value.target_urls.length) {
        form.value.target_urls = mergeUrls(
          form.value.target_urls,
          form.value.asset_ids.flatMap((id) => assetUrls(assetCache.value[id])),
        )
      }
    })
  }
  markSaved()
  void nextTick(() => { hydrating = false })
}

watch(form, () => {
  if (!hydrating && props.mode !== 'view') markDirty()
}, { deep: true })

watch(
  () => [props.mode, props.plan?.id ?? null] as const,
  ([mode]) => {
    if (mode === 'view') {
      markSaved()
      if (props.plan?.asset_ids?.length) void loadAssetLabels(props.plan.asset_ids)
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
