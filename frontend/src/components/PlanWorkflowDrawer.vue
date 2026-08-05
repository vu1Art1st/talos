<template>
  <el-drawer :model-value="visible" size="75%" direction="rtl" :destroy-on-close="true"
             @update:model-value="onVisibleChange" @closed="onClosed">
    <template #header>
      <div class="flex items-center gap-3">
        <span class="text-base font-semibold">测试流程 · {{ plan?.system_name || '' }}</span>
        <el-tag v-if="plan" :type="statusTag(plan.status)" size="small">
          {{ statusMap[plan.status] ?? plan.status }}
        </el-tag>
      </div>
    </template>

    <div v-if="plan" v-loading="loading" class="flex flex-col gap-4">
      <!-- 步骤条：按计划状态与数据推导当前阶段 -->
      <el-card shadow="never" class="!rounded-lg">
        <el-steps :active="stepActive" align-center finish-status="success" process-status="process">
          <el-step title="认领" />
          <el-step title="录入漏洞" />
          <el-step title="生成报告" />
          <el-step title="发起复测" />
          <el-step title="复测处理" />
          <el-step title="复测完成" />
        </el-steps>
      </el-card>

      <!-- 信息区 + 认领区 -->
      <el-card shadow="never" class="!rounded-lg">
        <div class="flex items-center flex-wrap gap-x-6 gap-y-2 text-sm">
          <span><span class="text-gray-400 mr-1">测试类型</span>{{ plan.test_type || '-' }}</span>
          <span><span class="text-gray-400 mr-1">所属部门</span>{{ plan.department || '-' }}</span>
          <span>
            <span class="text-gray-400 mr-1">测试人员</span>
            <span v-if="plan.testers?.length">
              {{ plan.testers.map((u: any) => u.realname || u.username).join('、') }}
            </span>
            <span v-else class="text-gray-400">未认领</span>
          </span>
          <span><span class="text-gray-400 mr-1">复测轮数</span>{{ plan.retest_round_count ?? 0 }} 轮</span>
          <div class="flex-1" />
          <el-button v-if="!isTester" size="small" type="success" @click="claim">认领</el-button>
          <el-popconfirm v-else title="确认退出该计划的认领？" @confirm="quit">
            <template #reference>
              <el-button size="small" type="info" plain>退出认领</el-button>
            </template>
          </el-popconfirm>
        </div>
        <div v-if="!isTester" class="text-xs text-gray-400 mt-2">
          仅已认领该计划的账号可录入/编辑/流转漏洞；认领后可执行生成报告、发起复测等流程操作
        </div>
      </el-card>

      <!-- 漏洞区 -->
      <el-card shadow="never" class="!rounded-lg">
        <template #header>
          <div class="flex items-center">
            <span class="font-medium">漏洞（{{ vulns.length }}）</span>
            <div class="flex-1" />
            <el-button v-if="canManageVulns" size="small" type="primary" plain class="!mr-2"
                       @click="openVulnPicker">
              <el-icon class="mr-1"><FolderOpened /></el-icon>从漏洞库选择
            </el-button>
            <el-button v-if="canManageVulns" size="small" type="warning" plain
                       @click="vulnFormVisible = !vulnFormVisible">
              <el-icon class="mr-1"><Plus /></el-icon>{{ vulnFormVisible ? '收起录入' : '录入漏洞' }}
            </el-button>
          </div>
        </template>

        <div v-if="vulnFormVisible" class="mb-4 rounded-lg border border-dashed border-gray-300 p-3 bg-gray-50/50">
          <VulnFormPanel :plan-id="planId" @saved="onVulnSaved">
            <template #actions-right>
              <el-button @click="vulnFormVisible = false">收起</el-button>
            </template>
          </VulnFormPanel>
        </div>

        <el-empty v-if="!vulns.length" description="暂无漏洞，点击右上角「录入漏洞」或「从漏洞库选择」开始" :image-size="60" />
        <el-table v-else :data="vulns" size="small" row-key="id">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="px-6 py-3 bg-gray-50/60">
                <VulnRetestPanel :vul-id="row.id" @changed="dirty = true" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="等级" width="70">
            <template #default="{ row }">
              <span class="tl-tag" :style="levelSoftStyle(row.level)">{{ levelName(row.level) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="漏洞标题" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <el-button type="primary" link class="!p-0" @click="router.push(`/vulns/${row.id}`)">
                {{ row.title }}
              </el-button>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <span class="tl-tag" :style="statusSoftStyleEx(row.status, row.is_retest)">
                {{ statusLabel(row.status, row.is_retest, vulStatusMap) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170">
            <template #default="{ row }">
              <el-dropdown v-if="canManageVulns" trigger="click"
                           @visible-change="(v: boolean) => v && loadTransitions(row)"
                           @command="(s: number) => transition(row, s)">
                <el-button size="small" type="primary" link>
                  流转<el-icon class="ml-0.5"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <template v-if="transitionsMap[row.id]?.length">
                      <el-dropdown-item v-for="t in transitionsMap[row.id]" :key="t.status" :command="t.status">
                        {{ t.name }}
                      </el-dropdown-item>
                    </template>
                    <el-dropdown-item v-else disabled>无可流转状态</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button v-if="canManageVulns" size="small" type="warning" link
                         @click="router.push(`/vulns/${row.id}/edit`)">
                编辑
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="vulns.length" class="text-xs text-gray-400 mt-2">
          点击行首箭头展开复测记录；「流转」按状态机推进漏洞状态，闭环后报告与计划状态自动联动
        </div>
      </el-card>

      <!-- 从漏洞库选择漏洞 -->
      <el-dialog v-model="vulnPickerVisible" title="从漏洞库选择" width="720px" append-to-body
                 @closed="pickerSelection = []">
        <div class="mb-3 flex items-center gap-3">
          <el-input v-model="pickerSearch" placeholder="搜索漏洞标题 / 等级 / 状态" clearable class="flex-1"
                    @input="loadPickerVulns" />
          <el-select v-model="pickerLevel" placeholder="按等级筛选" clearable class="w-32"
                     @change="loadPickerVulns">
            <el-option v-for="lv in [10, 20, 30, 40]" :key="lv" :value="lv"
                       :label="levelName(lv)" />
          </el-select>
        </div>
        <el-table v-loading="pickerLoading" :data="pickerVulns" size="small" row-key="id"
                  max-height="380" @selection-change="(rows: any[]) => pickerSelection = rows">
          <el-table-column type="selection" :selectable="(r: any) => !pickerLinkedIds.includes(r.id)" width="40" />
          <el-table-column label="等级" width="70">
            <template #default="{ row }">
              <span class="tl-tag" :style="levelSoftStyle(row.level)">{{ levelName(row.level) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="漏洞标题" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.title }}</span>
              <el-tag v-if="pickerLinkedIds.includes(row.id)" size="small" type="info" class="ml-2">已在本计划</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <span class="tl-tag" :style="statusSoftStyleEx(row.status, row.is_retest)">
                {{ statusLabel(row.status, row.is_retest, vulStatusMap) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <div class="text-xs text-gray-400 mt-2">
          勾选漏洞后点击「添加」，将关联到当前测试计划；已在本计划中的漏洞不可重复勾选
        </div>
        <template #footer>
          <el-button @click="vulnPickerVisible = false">取消</el-button>
          <el-button type="primary" :loading="pickerAttaching" :disabled="!pickerSelection.length"
                     @click="attachPickerVulns">添加（{{ pickerSelection.length }}）</el-button>
        </template>
      </el-dialog>

      <!-- 报告区 -->
      <el-card shadow="never" class="!rounded-lg">
        <template #header>
          <div class="flex items-center">
            <span class="font-medium">报告（{{ plan.reports?.length ?? 0 }}）</span>
            <div class="flex-1" />
            <el-button v-if="canOperate" size="small" type="success" plain :disabled="!vulns.length"
                       @click="toggleGenForm">
              <el-icon class="mr-1"><Document /></el-icon>{{ genFormVisible ? '收起' : '生成报告' }}
            </el-button>
          </div>
        </template>

        <div v-if="genFormVisible" class="mb-4 rounded-lg border border-dashed border-gray-300 p-3 bg-gray-50/50">
          <el-form label-width="80px">
            <el-form-item label="报告标题" required>
              <el-input v-model="genTitle" placeholder="报告标题" />
            </el-form-item>
            <el-form-item label="包含漏洞" required>
              <el-select v-model="genVulIds" multiple class="w-full" placeholder="选择纳入报告的漏洞">
                <el-option v-for="v in vulns" :key="v.id" :value="v.id" :label="v.title" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="generating" :disabled="!genTitle.trim() || !genVulIds.length"
                         @click="generateReport">生成报告</el-button>
              <el-button @click="genFormVisible = false">取消</el-button>
            </el-form-item>
          </el-form>
        </div>

        <el-empty v-if="!plan.reports?.length" description="暂无报告，录入漏洞后可生成报告" :image-size="60" />
        <div v-for="r in plan.reports" :key="r.id" class="py-3 border-b border-gray-100 last:border-0">
          <div class="flex items-center gap-2">
            <el-tag size="small" :type="r.status === 'completed' ? 'success' : 'info'">
              {{ reportStatusName(r.status) }}
            </el-tag>
            <span class="text-sm font-medium">{{ r.title }}</span>
            <div class="flex-1" />
            <el-popconfirm v-if="canOperate && r.status !== 'completed'"
                           title="发起复测将通知整改并使漏洞进入复测中，确认？" width="260"
                           @confirm="startRetest(r)">
              <template #reference>
                <el-button size="small" type="danger" plain>发起复测</el-button>
              </template>
            </el-popconfirm>
            <el-button size="small" type="primary" plain @click="router.push(`/reports/${r.id}`)">
              编辑内容
            </el-button>
            <el-button size="small" plain :loading="exporting[r.id] === 'docx'" @click="doExport(r, 'docx')">
              导出 Word
            </el-button>
            <el-button size="small" plain :loading="exporting[r.id] === 'pdf'" @click="doExport(r, 'pdf')">
              导出 PDF
            </el-button>
          </div>
          <!-- 导出记录（提交导出后自动轮询至完成） -->
          <div v-if="exportJobs[r.id]?.length" class="mt-2 flex flex-col gap-1">
            <div v-for="job in exportJobs[r.id]" :key="job.id" class="flex items-center gap-2 text-xs">
              <span class="uppercase font-mono text-gray-400">{{ job.fmt }}</span>
              <el-tag size="small"
                      :type="job.status === 'done' ? 'success' : job.status === 'failed' ? 'danger' : 'warning'">
                {{ job.status === 'done' ? '已完成' : job.status === 'failed' ? '失败' : '生成中' }}
              </el-tag>
              <el-tooltip v-if="job.status === 'failed'" :content="job.error || '生成失败'">
                <el-icon color="#F56C6C"><WarningFilled /></el-icon>
              </el-tooltip>
              <span class="text-gray-400 truncate">{{ job.title || r.title }}</span>
              <div class="flex-1" />
              <el-button v-if="job.status === 'done'" size="small" type="primary" link
                         @click="previewRef?.open(`/reports/exports/${job.id}/preview`, job.title || r.title)">
                预览
              </el-button>
              <el-button v-if="job.status === 'done'" size="small" type="primary" link class="!ml-0"
                         @click="download(job)">下载</el-button>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <PdfPreviewDialog ref="previewRef" />
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, ArrowDown, Document, FolderOpened, WarningFilled } from '@element-plus/icons-vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle, statusSoftStyleEx, statusLabel } from '../utils/colors'
import VulnFormPanel from './VulnFormPanel.vue'
import VulnRetestPanel from './VulnRetestPanel.vue'
import PdfPreviewDialog from './PdfPreviewDialog.vue'

// 测试计划统一流程抽屉：认领 → 录入漏洞 → 生成报告 → 发起复测 → 复测处理 → 复测完成，
// 全部流程动作在抽屉内完成（仅报告章节深度编辑跳转报告编辑页）。
const props = defineProps<{
  planId: number | null
  visible: boolean
}>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'changed'): void
}>()

const auth = useAuthStore()
const router = useRouter()

const plan = ref<any>(null)
const vulns = ref<any[]>([])
const loading = ref(false)
const dirty = ref(false)
const statusMap = ref<Record<number, string>>({})
const vulStatusMap = ref<Record<number, string>>({})

const vulnFormVisible = ref(false)
const transitionsMap = ref<Record<number, { status: number; name: string }[]>>({})

const genFormVisible = ref(false)
const genTitle = ref('')
const genVulIds = ref<number[]>([])
const generating = ref(false)

const vulnPickerVisible = ref(false)
const pickerLoading = ref(false)
const pickerSearch = ref('')
const pickerLevel = ref<number | ''>('')
const pickerVulns = ref<any[]>([])
const pickerSelection = ref<any[]>([])
const pickerAttaching = ref(false)
// 已关联当前计划的漏洞 ID，用于选择器禁用与标记
const pickerLinkedIds = computed(() => vulns.value.map((v: any) => v.id))

const exportJobs = ref<Record<number, any[]>>({})
const exporting = ref<Record<number, string>>({})
const previewRef = ref<InstanceType<typeof PdfPreviewDialog>>()
let pollTimer: number | undefined

const statusTag = (s: number) =>
  ({ 10: 'info', 20: 'warning', 30: 'primary', 40: 'danger', 50: 'warning', 60: 'success' } as Record<number, string>)[s] ?? 'info'

const levelName = (lv: number) =>
  ({ 10: '严重', 20: '高危', 30: '中危', 40: '低危', 50: '安全' } as Record<number, string>)[lv] ?? lv

const reportStatusName = (s: string) =>
  ({ draft: '草稿', final: '定稿', completed: '已完成' } as Record<string, string>)[s] ?? s

const isAdmin = computed(() => auth.user?.permissions?.includes('*') ?? false)
const isTester = computed(() => plan.value?.testers?.some((u: any) => u.id === auth.user?.id) ?? false)
// 需求：录入漏洞阶段仅认领该计划的账号可录入/编辑/流转漏洞；管理员未认领也不放行
const canManageVulns = computed(() => isTester.value)
// 计划级操作（生成报告、发起复测等）：认领者或管理员
const canOperate = computed(() => isAdmin.value || isTester.value)

// 步骤条 active 推导：10 未认领→0，已认领→1；20 无漏洞→1、有漏洞→2；30/40→3；50→4；60→全部完成
const stepActive = computed(() => {
  const s = plan.value?.status
  if (s === 60) return 6
  if (s === 50) return 4
  if (s === 30 || s === 40) return 3
  if (s === 20) return vulns.value.length ? 2 : 1
  return plan.value?.testers?.length ? 1 : 0
})

async function refresh() {
  if (!props.planId) return
  loading.value = true
  try {
    const [planResp, vulResp] = await Promise.all([
      client.get(`/testing-plans/${props.planId}`),
      // 需求5：漏洞默认按危害等级降序（level 升序）展示
      client.get('/vulns', { params: { testing_plan_id: props.planId, size: 100, sort: 'level', order: 'asc' } }),
    ])
    plan.value = planResp.data
    vulns.value = sortVulns(vulResp.data.items)
  } finally {
    loading.value = false
  }
}

// 需求5：按危害等级降序（level 小=超危/高危）排序，保持后端兜底
function sortVulns(items: any[]) {
  return [...items].sort((a, b) => (a.level ?? 99) - (b.level ?? 99))
}

// ---------- 从漏洞库选择 ----------
async function openVulnPicker() {
  vulnPickerVisible.value = true
  pickerSearch.value = ''
  pickerLevel.value = ''
  await loadPickerVulns()
}

async function loadPickerVulns() {
  if (!vulnPickerVisible.value) return
  pickerLoading.value = true
  try {
    // 注意：后端 /vulns 的 size 上限为 100，超出会返回 422
    const params: Record<string, any> = { size: 100, sort: 'level', order: 'asc' }
    if (pickerSearch.value.trim()) params.search = pickerSearch.value.trim()
    if (pickerLevel.value) params.level = pickerLevel.value
    const { data } = await client.get('/vulns', { params })
    pickerVulns.value = sortVulns(data.items)
  } finally {
    pickerLoading.value = false
  }
}

async function attachPickerVulns() {
  pickerAttaching.value = true
  try {
    await client.post(`/testing-plans/${props.planId}/attach-vulns`, {
      vul_ids: pickerSelection.value.map((v: any) => v.id),
    })
    ElMessage.success(`已添加 ${pickerSelection.value.length} 个漏洞到当前计划`)
    vulnPickerVisible.value = false
    dirty.value = true
    await refresh()
  } finally {
    pickerAttaching.value = false
  }
}

watch(
  () => [props.visible, props.planId] as const,
  async ([visible]) => {
    if (!visible || !props.planId) return
    // 打开时重置临时态并加载数据
    dirty.value = false
    vulnFormVisible.value = false
    genFormVisible.value = false
    transitionsMap.value = {}
    exportJobs.value = {}
    if (!Object.keys(statusMap.value).length) {
      const meta = await auth.fetchMeta()
      statusMap.value = meta?.testing_plan_status ?? {}
      vulStatusMap.value = meta?.vul_status ?? {}
    }
    await refresh()
  },
  { immediate: true },
)

function onVisibleChange(v: boolean) {
  emit('update:visible', v)
}

function onClosed() {
  stopPolling()
  if (dirty.value) emit('changed')
}

// ---------- 认领 ----------
async function claim() {
  await client.post(`/testing-plans/${props.planId}/claim`)
  ElMessage.success('认领成功，已加入测试人员')
  dirty.value = true
  await refresh()
}

async function quit() {
  await client.post(`/testing-plans/${props.planId}/quit`)
  ElMessage.success('已退出该计划')
  dirty.value = true
  await refresh()
}

// ---------- 漏洞 ----------
async function onVulnSaved() {
  vulnFormVisible.value = false
  dirty.value = true
  await refresh()
}

async function loadTransitions(row: any) {
  // 后端返回 [{status, name}]，直接作为下拉候选
  const { data } = await client.get(`/vulns/${row.id}/transitions`)
  transitionsMap.value[row.id] = data
}

async function transition(row: any, status: number) {
  await client.post(`/vulns/${row.id}/transition`, { status })
  ElMessage.success(`已流转为「${vulStatusMap.value[status] ?? status}」`)
  dirty.value = true
  await refresh()
}

// ---------- 报告 ----------
function toggleGenForm() {
  genFormVisible.value = !genFormVisible.value
  if (genFormVisible.value) {
    genTitle.value = `${plan.value?.system_name ?? ''}渗透测试报告`
    genVulIds.value = vulns.value.map((v) => v.id)
  }
}

async function generateReport() {
  generating.value = true
  try {
    await client.post('/reports/from-vulns', {
      title: genTitle.value.trim(),
      vul_ids: genVulIds.value,
      testing_plan_id: props.planId,
    })
    ElMessage.success('报告已生成，计划进入等待复测')
    genFormVisible.value = false
    dirty.value = true
    await refresh()
  } finally {
    generating.value = false
  }
}

async function startRetest(r: any) {
  await client.post(`/reports/${r.id}/retest`)
  ElMessage.success('已发起复测，漏洞进入复测中')
  dirty.value = true
  await refresh()
}

// ---------- 导出（提交后轮询任务列表至完成） ----------
async function loadJobs(reportId: number) {
  const { data } = await client.get(`/reports/${reportId}/exports`)
  exportJobs.value[reportId] = data
  return data as any[]
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

function pollJobs(reportId: number) {
  stopPolling()
  let ticks = 0
  pollTimer = window.setInterval(async () => {
    ticks += 1
    const jobs = await loadJobs(reportId)
    const pending = jobs.some((j) => j.status !== 'done' && j.status !== 'failed')
    if (!pending || ticks >= 30) stopPolling()
  }, 2000)
}

async function doExport(r: any, fmt: string) {
  exporting.value[r.id] = fmt
  try {
    await client.post(`/reports/${r.id}/export`, { fmt })
    ElMessage.success('导出任务已提交，生成完成后可在下方下载')
    await loadJobs(r.id)
    pollJobs(r.id)
  } finally {
    delete exporting.value[r.id]
  }
}

function download(job: any) {
  client.get(`/reports/exports/${job.id}/download`, { responseType: 'blob' }).then((resp) => {
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${job.title || plan.value?.system_name || 'report'}.${job.fmt}`
    a.click()
    URL.revokeObjectURL(url)
  })
}

onBeforeUnmount(stopPolling)
</script>
