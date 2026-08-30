<template>
  <!-- 独立编辑页（asideActions）：左侧内容滚动 + 右侧固定操作栏；弹窗/抽屉：保持底部操作栏 -->
  <div :class="asideActions ? 'flex h-full min-h-0 flex-col xl:flex-row gap-4' : ''">
    <div :class="asideActions ? 'flex-1 min-h-0 overflow-y-auto space-y-4 pr-1' : ''">
      <slot name="notice" />

      <el-card shadow="never" :class="asideActions ? '' : 'mb-4'">
        <el-form ref="targetFormRef" :model="targetForm" :rules="targetRules" label-width="90px">
          <el-form-item label="测试目标" prop="assetIds">
            <div class="w-full flex items-start gap-2">
              <el-select v-model="targetForm.assetIds" multiple filterable remote :remote-method="searchAssets"
                         :loading="assetLoading" placeholder="搜索并选择资产（系统）" class="flex-1"
                         @change="onAssetChange">
                <el-option v-for="a in assetOptions" :key="a.id" :value="a.id"
                           :label="a.sub_system ? `${a.name} / ${a.sub_system}` : a.name">
                  <div class="flex justify-between">
                    <span>{{ a.sub_system ? `${a.name} / ${a.sub_system}` : a.name }}</span>
                    <span class="text-xs text-gray-400">{{ a.department }}</span>
                  </div>
                </el-option>
                <template #empty>
                  <div class="p-3 text-center">
                    <p class="text-sm text-gray-400 mb-2">未找到匹配的资产</p>
                    <el-button size="small" type="primary" @click="openCreateAsset">
                      <el-icon class="mr-1"><Plus /></el-icon>新建资产{{ assetKeyword ? `「${assetKeyword}」` : '' }}
                    </el-button>
                  </div>
                </template>
              </el-select>
              <el-button type="primary" plain @click="openCreateAsset">
                <el-icon class="mr-1"><Plus /></el-icon>新增资产
              </el-button>
            </div>
          </el-form-item>
          <el-form-item v-if="selectedAssets.length" label=" ">
            <div class="text-xs text-gray-500 leading-6">
              <div v-for="a in selectedAssets" :key="a.id">
                {{ a.name }}：部门 {{ a.department || '-' }}；
                负责人 {{ (a.owners ?? []).map((o: any) => o.name).join('、') || '-' }}；
                URL {{ (a.public_urls ?? [])[0]?.url || (a.internal_urls ?? [])[0] || '-' }}
              </div>
            </div>
          </el-form-item>
          <el-form-item label="关联渗透测试工单">
            <el-select v-model="selectedPlanId" clearable filterable class="w-full"
                       :placeholder="editId ? '可选：调整关联的渗透测试工单' : '可选：关联到渗透测试工单'"
                       :loading="planLoading" @visible-change="(v: boolean) => v && loadPlans()">
              <el-option v-for="p in planOptions" :key="p.id" :value="p.id"
                         :label="`${p.system_name}${p.plan_name ? ' · ' + p.plan_name : ''}`">
                <div class="flex justify-between">
                  <span class="truncate">{{ p.system_name }}{{ p.plan_name ? ' · ' + p.plan_name : '' }}</span>
                  <span class="text-xs text-gray-400 shrink-0 ml-2">{{ p.status_name || '' }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card v-for="(vul, idx) in vulns" :key="idx" shadow="never"
               :class="asideActions ? '' : 'mb-4'">
        <template #header>
          <div class="flex items-center">
            <span class="font-medium">{{ editId ? '编辑漏洞' : `漏洞 #${idx + 1}` }}</span>
            <div class="flex-1" />
            <el-button v-if="!editId && vulns.length > 1" type="danger" link @click="vulns.splice(idx, 1)">
              删除此漏洞
            </el-button>
          </div>
        </template>
        <el-form :ref="(el: any) => setVulFormRef(idx, el)" :model="vul" :rules="vulRules" label-width="90px">
          <el-form-item label="漏洞名称" prop="title">
            <el-input v-model="vul.title" placeholder="例如：后台登录接口存在SQL注入" />
          </el-form-item>
          <div class="grid grid-cols-1 md:grid-cols-2">
            <el-form-item label="漏洞等级">
              <el-select v-model="vul.level" class="w-full">
                <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
            <el-form-item label="漏洞类型">
              <div class="w-full flex items-center gap-2">
                <el-select v-model="vul.vul_type" filterable class="flex-1">
                  <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
                  <template #footer>
                    <el-button v-if="auth.hasPerm('vuln:manage')" size="small" type="primary" link
                               @click="addVulnType(vul)">
                      <el-icon class="mr-1"><Plus /></el-icon>新增漏洞类型
                    </el-button>
                  </template>
                </el-select>
                <el-tooltip content="从漏洞模板库套用该类型的标准描述与修复建议" placement="top">
                  <el-button plain @click="applyTemplate(vul)">套用模板</el-button>
                </el-tooltip>
              </div>
            </el-form-item>
            <el-form-item label="所在层">
              <el-select v-model="vul.layer" class="w-full">
                <el-option v-for="(name, code) in meta?.vul_layer" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="editId" label="漏洞状态">
              <el-select v-model="vul.status" class="w-full" placeholder="选择漏洞状态">
                <el-option v-for="(name, code) in meta?.vul_status" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
            <el-form-item label="漏洞来源">
              <!-- 关联渗透测试工单：来源固定为「渗透测试工单」不可修改；单独提交时可选远程检测来源 -->
              <el-input v-if="selectedPlanId" :model-value="'渗透测试工单'" disabled class="w-full" />
              <el-select v-else v-model="vul.source" class="w-full" clearable placeholder="未选择（可选）">
                <el-option v-for="(name, code) in meta?.vul_source" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
            <el-form-item label="影响URL">
              <div class="w-full flex flex-col gap-2">
                <div v-for="(_, uidx) in vul.affected_urls" :key="uidx" class="flex items-center gap-2">
                  <el-input v-model="vul.affected_urls[uidx]" placeholder="https://..." class="flex-1" />
                  <el-button v-if="vul.affected_urls.length > 1" type="danger" link
                             @click="vul.affected_urls.splice(uidx, 1)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <div>
                  <el-button size="small" plain @click="vul.affected_urls.push('')">
                    <el-icon class="mr-1"><Plus /></el-icon>添加URL
                  </el-button>
                </div>
              </div>
            </el-form-item>
          </div>
          <el-form-item label="CVSS 3.1">
            <div class="w-full">
              <div class="mb-1 flex items-center justify-between">
                <span class="text-xs text-gray-400">按向量计算基础评分并写入漏洞评分</span>
                <el-checkbox v-model="vul.cvss_sync_level" size="small">按评分同步等级</el-checkbox>
              </div>
              <CvssCalculator v-model:vector="vul.cvss_vector" v-model:score="vul.score"
                              @level-suggest="(lv: number) => vul.cvss_sync_level && (vul.level = lv)" />
            </div>
          </el-form-item>
          <el-form-item label="漏洞描述">
            <RichEditor v-model="vul.description_html" class="w-full"
                        @update:json="(j: any) => (vul.description_json = j)" />
          </el-form-item>
          <el-form-item label="复现步骤">
            <RichEditor v-model="vul.reproduce_html" class="w-full"
                        @update:json="(j: any) => (vul.reproduce_json = j)" />
          </el-form-item>
          <el-form-item label="修复建议">
            <RichEditor v-model="vul.solution_html" class="w-full"
                        @update:json="(j: any) => (vul.solution_json = j)" />
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 操作栏：独立编辑页渲染为右侧固定卡片（与报告编辑页一致），弹窗/抽屉保持底部横排 -->
    <div v-if="asideActions" class="xl:w-[300px] xl:shrink-0 max-h-[45vh] xl:max-h-none xl:h-full xl:min-h-0 xl:overflow-y-auto">
      <el-card shadow="never">
        <template #header>操作</template>
        <div class="space-y-2">
          <el-button type="primary" class="w-full !ml-0" :loading="saving" @click="save">
            {{ editId ? '保存' : `提交 ${vulns.length} 个漏洞` }}
          </el-button>
          <el-button v-if="!editId" class="w-full !ml-0" @click="addVuln">
            <el-icon class="mr-1"><Plus /></el-icon>新增漏洞
          </el-button>
          <slot name="actions-left" />
          <el-divider class="!my-3" />
          <slot name="actions-right" />
        </div>
      </el-card>
    </div>
  </div>

  <!-- 底部操作栏：弹窗/抽屉（非 asideActions）场景保留横排 -->
  <div v-if="!asideActions" class="flex items-center gap-2 mb-2">
    <el-button v-if="!editId" @click="addVuln">
      <el-icon class="mr-1"><Plus /></el-icon>新增漏洞
    </el-button>
    <slot name="actions-left" />
    <div class="flex-1" />
    <slot name="actions-right" />
    <el-button type="primary" :loading="saving" @click="save">
      {{ editId ? '保存' : `提交 ${vulns.length} 个漏洞` }}
    </el-button>
  </div>

  <AssetFormDialog v-model:visible="assetDialogVisible" :asset="assetPrefill" @saved="onAssetCreated" />

  <!-- 知识库模板选择弹窗 -->
  <el-dialog
             :close-on-click-modal="false" v-model="templateVisible" title="选择知识库模板" width="640px" append-to-body>
    <el-input v-model="templateSearch" placeholder="搜索模板名称 / 标签 / 描述" clearable class="mb-3">
      <template #prefix><el-icon><Search /></el-icon></template>
    </el-input>
    <div v-if="!templateList.length" class="py-8 text-center text-gray-400">该漏洞类型暂无知识库模板</div>
    <div v-else-if="!filteredTemplateList.length" class="py-8 text-center text-gray-400">
      未找到匹配「{{ templateSearch }}」的模板
    </div>
    <div v-else class="flex flex-col gap-2 max-h-96 overflow-auto">
      <div v-for="(t, i) in filteredTemplateList" :key="t.id"
           class="rounded-lg border border-gray-200 hover:border-brand-400 cursor-pointer p-3 transition"
           @click="applyEntry(t)">
        <div class="flex items-center gap-2">
          <span class="tl-tag" :style="levelSoftStyle(t.severity_level)">{{ levelName(t.severity_level) }}</span>
          <span class="font-medium">{{ t.vulnerability_name }}</span>
          <span v-if="t.tags?.length" class="text-xs text-gray-400">{{ t.tags.join('、') }}</span>
        </div>
        <p class="text-xs text-gray-500 mt-1 line-clamp-2">{{ plainSummary(t) }}</p>
      </div>
    </div>
    <template #footer>
      <span class="text-xs text-gray-400 mr-auto">共 {{ filteredTemplateList.length }} / {{ templateList.length }} 条</span>
      <el-button @click="templateVisible = false">取消</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Delete, Search } from '@element-plus/icons-vue'
import client from '../api/client'
import RichEditor from './RichEditor.vue'
import AssetFormDialog from './AssetFormDialog.vue'
import CvssCalculator from './CvssCalculator.vue'
import { useAuthStore } from '../stores/auth'
import { levelName, levelSoftStyle } from '../utils/colors'

// 漏洞录入/编辑表单面板：供独立页（VulnEdit）与测试计划流程抽屉复用。
// 组件内不做路由跳转，保存成功后仅 emit saved，由宿主决定后续行为。
const props = defineProps<{
  planId?: number | null   // 新建时预关联的测试计划
  editId?: number | null   // 编辑态漏洞 ID
  asideActions?: boolean   // 独立编辑页：操作按钮渲染为右侧固定栏（与报告编辑页一致）
}>()
const emit = defineEmits<{ (e: 'saved', vulns: any[]): void }>()

const auth = useAuthStore()
const meta = ref<any>(null)
const saving = ref(false)
const editId = props.editId ?? null
const planId = props.planId ?? null

// ---------- 关联测试计划 ----------
const selectedPlanId = ref<number | null>(planId)
// 关联渗透测试工单后来源固定为「渗透测试工单」（展示层派生），不落库来源值
watch(selectedPlanId, (v) => {
  if (v != null) vulns.value.forEach((x: any) => (x.source = 0))
})
const planOptions = ref<any[]>([])
const planLoading = ref(false)
let plansLoaded = false
const statusMap = ref<Record<number, string>>({})

async function loadPlans() {
  if (plansLoaded) return
  plansLoaded = true
  planLoading.value = true
  try {
    const { data } = await client.get('/testing-plans', { params: { size: 100 } }).catch(() => null)
    if (data) {
      planOptions.value = data.items
      statusMap.value = (await auth.fetchMeta()).testing_plan_status ?? {}
      planOptions.value.forEach((p: any) => {
        p.status_name = statusMap.value[p.status] ?? ''
      })
    }
  } finally {
    planLoading.value = false
  }
}

// ---------- 资产选择 ----------
// assetIds 放入 reactive 表单模型，供外层 el-form 的 rules 校验（测试目标必选）
const targetForm = reactive({ assetIds: [] as number[] })
const targetFormRef = ref<FormInstance>()
const targetRules: FormRules = {
  assetIds: [{ required: true, type: 'array', message: '请选择测试目标资产', trigger: 'change' }],
}
const assetOptions = ref<any[]>([])
const assetCache = ref<Record<number, any>>({})
const assetLoading = ref(false)
const assetKeyword = ref('')
const assetDialogVisible = ref(false)
const assetPrefill = ref<any>(null)

const selectedAssets = computed(() => targetForm.assetIds.map((id) => assetCache.value[id]).filter(Boolean))

async function searchAssets(keyword = '') {
  assetKeyword.value = keyword
  assetLoading.value = true
  try {
    const { data } = await client.get('/assets', { params: { search: keyword, size: 50 } })
    assetOptions.value = data.items
    for (const a of data.items) assetCache.value[a.id] = a
  } finally {
    assetLoading.value = false
  }
}

function openCreateAsset() {
  assetPrefill.value = assetKeyword.value ? { name: assetKeyword.value } : null
  assetDialogVisible.value = true
}

function onAssetCreated(asset: any) {
  assetCache.value[asset.id] = asset
  assetOptions.value = [asset, ...assetOptions.value.filter((a) => a.id !== asset.id)]
  targetForm.assetIds = [...targetForm.assetIds, asset.id]
  onAssetChange()
}

function onAssetChange() {
  // 自动填充：影响URL 为空时，取首个选中资产的公网/内网URL
  const first = selectedAssets.value[0]
  if (!first) return
  const url = (first.public_urls ?? [])[0]?.url || (first.internal_urls ?? [])[0] || ''
  if (!url) return
  for (const vul of vulns.value) {
    if (!vul.affected_urls.some((u: string) => u.trim())) vul.affected_urls = [url]
  }
}

// ---------- 漏洞表单（新建支持多块，编辑单块） ----------
const emptyVul = () => ({
  title: '', level: 30, vul_type: 75, layer: 10, affected_urls: [''],
  description_html: '', description_json: null,
  reproduce_html: '', reproduce_json: null,
  solution_html: '', solution_json: null,
  source: 0, score: 0, risk_score: 0, left_risk_score: 0, asset_level: 0,
  cvss_vector: '', cvss_sync_level: true,
})
const vulns = ref<any[]>([emptyVul()])

// 每个漏洞卡片一张独立 el-form（动态多块），函数 ref 按下标收集，提交时逐一校验
const vulFormRefs: FormInstance[] = []

function setVulFormRef(idx: number, el: unknown) {
  if (el) vulFormRefs[idx] = el as FormInstance
  else vulFormRefs.splice(idx, 1)
}

const vulRules: FormRules = {
  title: [{ required: true, whitespace: true, message: '请填写漏洞名称', trigger: 'blur' }],
}

// 影响URL 多值与后端单字段（换行分隔）互转
const joinUrls = (urls: string[]) => (urls ?? []).map((u) => u.trim()).filter(Boolean).join('\n')
const splitUrls = (raw: string) => {
  const arr = (raw ?? '').split('\n').map((u) => u.trim()).filter(Boolean)
  return arr.length ? arr : ['']
}

function addVuln() {
  const block = emptyVul()
  const first = selectedAssets.value[0]
  const url = (first?.public_urls ?? [])[0]?.url || (first?.internal_urls ?? [])[0] || ''
  if (url) block.affected_urls = [url]
  vulns.value.push(block)
}

// ---------- 知识库模板套用 ----------
const templateVisible = ref(false)
const templateList = ref<any[]>([])
const templateSearch = ref('')
let templateTarget: any = null

const filteredTemplateList = computed(() => {
  const kw = templateSearch.value.trim().toLowerCase()
  if (!kw) return templateList.value
  return templateList.value.filter((t) =>
    (t.vulnerability_name || '').toLowerCase().includes(kw)
    || (t.tags ?? []).some((tag: string) => tag.toLowerCase().includes(kw))
    || plainSummary(t).toLowerCase().includes(kw),
  )
})

const plainSummary = (t: any) => {
  const html = t.description_html || ''
  return html.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').slice(0, 80) || '（无描述）'
}

async function applyTemplate(vul: any) {
  templateTarget = vul
  try {
    const { data } = await client.get(`/knowledge/by-type/${vul.vul_type}`)
    if (!data.length) return ElMessage.info('该漏洞类型暂无知识库模板')
    if (data.length === 1) return applyEntry(data[0])
    templateList.value = data
    templateVisible.value = true
  } catch {
    return // 404 提示由拦截器统一处理
  }
}

// 在漏洞类型下拉中直接新增类型（同步到全局 meta，无需跳转知识库）
async function addVulnType(vul: any) {
  const { value } = await ElMessageBox.prompt('请输入新的漏洞类型名称', '新增漏洞类型', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  const { data } = await client.post('/vuln-types', { name: value.trim() })
  if (meta.value?.vul_type) meta.value.vul_type[data.code] = data.name
  if (auth.meta?.vul_type) auth.meta.vul_type[data.code] = data.name
  ElMessage.success('漏洞类型已新增')
  vul.vul_type = data.code
}

async function applyEntry(entry: any) {
  const vul = templateTarget
  if (!vul) return
  if ((vul.description_html || '').trim() || (vul.solution_html || '').trim()) {
    try {
      await ElMessageBox.confirm('当前已填写漏洞描述或修复建议，套用模板将覆盖这些内容，是否继续？', '套用模板', { type: 'warning' })
    } catch {
      return
    }
  }
  let descHtml = entry.description_html || ''
  if (entry.harm_html) descHtml += `<p><strong>危害说明：</strong></p>${entry.harm_html}`
  vul.description_html = descHtml
  vul.description_json = entry.harm_html ? null : entry.description_json
  vul.solution_html = entry.solution_html || ''
  vul.solution_json = entry.solution_json
  if (entry.cvss_vector) vul.cvss_vector = entry.cvss_vector
  templateVisible.value = false
  ElMessage.success(`已套用模板「${entry.vulnerability_name}」`)
}

async function save() {
  // 先校验测试目标，再并行校验每个漏洞卡片，全部通过才提交（错误内联展示在对应字段）
  const targetValid = await targetFormRef.value.validate().catch(() => false)
  if (!targetValid) return
  const vulResults = await Promise.all(vulFormRefs.map((f) => f.validate().catch(() => false)))
  if (vulResults.some((ok) => !ok)) return
  saving.value = true
  try {
    // 影响URL 多值序列化为后端单字段（换行分隔），剔除前端临时字段
    const toPayload = (v: any) => {
      const { affected_urls, cvss_sync_level, ...rest } = v
      return { ...rest, affected_url: joinUrls(affected_urls) }
    }
    if (editId) {
      const { data } = await client.put(`/vulns/${editId}`, {
        ...toPayload(vulns.value[0]),
        asset_ids: targetForm.assetIds,
        testing_plan_id: selectedPlanId.value,
      })
      ElMessage.success('保存成功')
      emit('saved', [data])
    } else {
      const { data } = await client.post('/vulns/batch', {
        asset_ids: targetForm.assetIds,
        vulns: vulns.value.map((v) => {
          const payload = toPayload(v)
          const plan = selectedPlanId.value ?? planId
          return plan ? { ...payload, testing_plan_id: plan } : payload
        }),
      })
      ElMessage.success(`成功提交 ${data.length} 个漏洞`)
      emit('saved', data)
    }
  } finally {
    saving.value = false
  }
}

// 按资产ID加载并回显资产（供计划关联资产预填与编辑回显复用）
async function loadAssetsByIds(ids: number[]) {
  if (!ids.length) return
  const rows = await Promise.all(ids.map((id: number) => client.get(`/assets/${id}`).catch(() => null)))
  for (const r of rows) {
    const a = r?.data
    if (a && !assetCache.value[a.id]) {
      assetCache.value[a.id] = a
      assetOptions.value.push(a)
    }
  }
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await searchAssets()
  await loadPlans()
  if (editId) {
    const { data: vul } = await client.get(`/vulns/${editId}`)
    vulns.value = [{ ...emptyVul(), ...vul, affected_urls: splitUrls(vul.affected_url) }]
    targetForm.assetIds = vul.asset_ids ?? []
    selectedPlanId.value = vul.testing_plan_id ?? null
    await loadAssetsByIds(targetForm.assetIds)
  } else if (planId) {
    // 计划编制时已前置录入的关联资产，录入漏洞时自动带入（仍可调整）
    const { data: plan } = await client.get(`/testing-plans/${planId}`)
    const ids = plan.asset_ids ?? []
    if (ids.length) {
      targetForm.assetIds = ids
      await loadAssetsByIds(ids)
      onAssetChange()
    }
  }
})
</script>
