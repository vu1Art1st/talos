<template>
  <el-drawer :model-value="visible" size="75%" direction="rtl" :destroy-on-close="true"
             @update:model-value="onVisibleChange" @closed="onClosed">
    <template #header>
      <div class="flex items-center gap-3">
        <span class="text-base font-semibold">测试流程 · {{ plan?.system_name || '' }}</span>
        <span v-if="plan" class="tl-tag" :style="planStatusSoftStyle(plan.status)">
          {{ statusMap[plan.status] ?? plan.status }}
        </span>
      </div>
    </template>

    <div v-if="plan" v-loading="loading" class="flex flex-col gap-4">
      <!-- 步骤条：按计划状态与数据推导当前阶段 -->
      <el-card shadow="never">
        <el-steps :active="stepActive" align-center finish-status="success" process-status="process">
          <el-step title="认领" />
          <el-step title="录入漏洞" />
          <el-step title="生成报告" />
          <el-step title="发起复测" />
          <el-step title="复测处理" />
          <el-step title="复测完成" />
        </el-steps>
      </el-card>

      <!-- 无漏洞闭环：已确认「测试通过」时展示结论横幅 -->
      <el-alert v-if="plan.status === 70" type="success" :closable="false" show-icon
                title="本计划已确认无漏洞（测试通过），测试流程已闭环">
        <template #default>
          <div>{{ plan.no_vul_conclusion || '测试完成且未发现安全漏洞，无漏洞报告见下方报告区，可导出 Word/PDF 归档。' }}</div>
          <div class="text-xs mt-1">若后续补录/关联新漏洞，计划将自动重开为「初测中」。</div>
        </template>
      </el-alert>

      <!-- 信息区 + 认领区 -->
      <el-card shadow="never">
        <div class="flex items-center flex-wrap gap-x-6 gap-y-2 text-sm">
          <span><span class="text-gray-400 mr-1">测试类型</span>{{ plan.test_type || '-' }}</span>
          <span><span class="text-gray-400 mr-1">所属部门</span>{{ plan.department || '-' }}</span>
          <span>
            <span class="text-gray-400 mr-1">测试人员</span>
            <span v-if="plan.testers?.length">
              {{ plan.testers.map((u) => u.realname || u.username).join('、') }}
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
      <el-card shadow="never">
        <template #header>
          <div class="flex items-center">
            <span class="font-medium">漏洞（{{ vulns.length }}）</span>
            <div class="flex-1" />
            <el-button v-if="canOperate && canCompleteNoVuln && !vulns.length" size="small"
                       type="success" plain class="!mr-2" @click="openNoVulnDialog">
              <el-icon class="mr-1"><CircleCheck /></el-icon>完成测试（无漏洞）
            </el-button>
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

        <el-empty v-if="!vulns.length" description="暂无漏洞，点击右上角「录入漏洞」或「从漏洞库选择」开始" :image-size="80" />
        <el-table v-else :data="vulns" size="small" row-key="id">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="px-6 py-3 bg-gray-50/60">
                <VulnRetestPanel :vul-id="row.id" @changed="onRetestChanged" />
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
              <el-button type="primary" link class="!p-0" @click="openVulnDetail(row.id)">
                {{ row.title }}
              </el-button>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <span class="tl-tag" :style="statusSoftStyleWithRetest(row.status, row.is_retest)">
                {{ statusLabel(row.status, row.is_retest, vulStatusMap) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170">
            <template #default="{ row }">
              <div class="flex items-center gap-2">
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
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="vulns.length" class="text-xs text-gray-400 mt-2">
          点击行首箭头展开复测记录；「流转」按状态机推进漏洞状态，闭环后报告与计划状态自动联动
        </div>
      </el-card>

      <!-- 漏洞详情弹窗：点击漏洞标题就地弹出（公共组件，与远程检测共用） -->
      <VulnDetailDialog v-model:visible="vulnDetailVisible" :vuln-id="detailVulnId" />

      <!-- 从漏洞库选择漏洞 -->
      <el-dialog
             :close-on-click-modal="false" v-model="vulnPickerVisible" title="从漏洞库选择" width="800px" append-to-body
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
                  max-height="380" @selection-change="(rows: Vuln[]) => pickerSelection = rows">
                    <el-table-column type="selection" :selectable="(r: Vuln) => !pickerLinkedIds.includes(r.id)" width="40" />
          <el-table-column label="等级" width="70">
            <template #default="{ row }">
              <span class="tl-tag" :style="levelSoftStyle(row.level)">{{ levelName(row.level) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="漏洞标题" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.title }}</span>
              <span v-if="pickerLinkedIds.includes(row.id)" class="tl-tag ml-2" :style="softStyle(STAT_CARD_COLORS.blue)">已在本计划</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <span class="tl-tag" :style="statusSoftStyleWithRetest(row.status, row.is_retest)">
                {{ statusLabel(row.status, row.is_retest, vulStatusMap) }}
              </span>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="没有可关联的漏洞，可调整筛选条件后重试" :image-size="80" />
          </template>
        </el-table>
        <div class="text-xs text-gray-400 mt-2">
          勾选漏洞后点击「添加」，将关联到当前渗透测试工单；已在本计划中的漏洞不可重复勾选
        </div>
        <template #footer>
          <el-button @click="vulnPickerVisible = false">取消</el-button>
          <el-button type="primary" :loading="pickerAttaching" :disabled="!pickerSelection.length"
                     @click="attachPickerVulns">添加（{{ pickerSelection.length }}）</el-button>
        </template>
      </el-dialog>

      <!-- 报告区 -->
      <el-card shadow="never">
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
          <el-form label-width="90px">
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

        <el-empty v-if="!plan.reports?.length" description="暂无报告，录入漏洞后可生成报告" :image-size="80" />
        <div v-for="r in plan.reports" :key="r.id" class="py-3 border-b border-gray-100 last:border-0">
          <div class="flex items-center gap-2">
            <span class="tl-tag" :style="reportStatusSoftStyle(r.status)">{{ reportStatusName(r.status) }}</span>
            <span class="text-sm font-medium">{{ r.title }}</span>
            <!-- 报告中漏洞已全部完成（已修复/已忽略）标注：便于与仍有未闭环漏洞的报告区分 -->
            <el-tooltip v-if="r.all_closed"
                        :content="`本报告所含漏洞均已修复/已忽略（${r.vul_closed}/${r.vul_total}）`">
              <span class="tl-tag" :style="statusSoftStyleWithRetest(60)">复测完成</span>
            </el-tooltip>
            <span class="text-xs text-gray-400">生成于 {{ fmtDateTime(r.create_time) }}</span>
            <div class="flex-1" />
            <el-popconfirm v-if="canOperate"
                           title="发起复测将通知整改并使漏洞进入复测中，系统将自动生成复测报告，确认？" width="280"
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
            <el-popconfirm v-if="canOperate" title="确认删除该报告？将一并移除其导出记录" width="240"
                           @confirm="removeReport(r)">
              <template #reference>
                <el-button size="small" type="danger" plain>删除</el-button>
              </template>
            </el-popconfirm>
          </div>
          <!-- 导出历史：点击箭头展开已导出的历史版本列表 -->
          <div class="mt-1">
            <el-button size="small" link type="primary" @click="toggleExportList(r)">
              <el-icon class="mr-0.5">
                <ArrowDown v-if="expandedExportId === r.id" /><ArrowRight v-else />
              </el-icon>
              {{ expandedExportId === r.id ? '收起导出历史' : `导出历史（${exportJobs[r.id]?.length ?? 0}）` }}
            </el-button>
            <div v-if="expandedExportId === r.id" class="mt-2 flex flex-col gap-1">
              <div v-if="!exportJobs[r.id]?.length" class="text-xs text-gray-400">
                暂无导出记录，点击「导出 Word / 导出 PDF」生成
              </div>
              <div v-for="job in exportJobs[r.id]" :key="job.id" class="flex items-center gap-2 text-xs">
                <span class="uppercase font-mono text-gray-400">{{ job.fmt }}</span>
                <span class="tl-tag" :style="exportJobSoftStyle(job.status)">{{ exportJobName(job.status) }}</span>
                <el-tooltip v-if="job.status === 'failed'" :content="job.error || '生成失败'">
                  <el-icon :color="exportJobColor('failed')"><WarningFilled /></el-icon>
                </el-tooltip>
                <span class="text-gray-400 truncate">{{ job.title || r.title }}</span>
                <span class="text-gray-300">{{ fmtDateTime(job.create_time) }}</span>
                <div class="flex-1" />
                <el-button v-if="job.status === 'done'" size="small" type="primary" link
                           @click="previewRef?.open(`/reports/exports/${job.id}/preview`, job.title || r.title)">
                  预览
                </el-button>
                <el-button v-if="job.status === 'done'" size="small" type="primary" link class="!ml-0"
                           @click="download(job)">下载</el-button>
                <el-popconfirm v-if="job.status !== 'pending' && job.status !== 'running'"
                               title="确认删除该导出记录？文件将一并移除" width="240"
                               @confirm="removeExportJob(r, job)">
                  <template #reference>
                    <el-button size="small" type="danger" link class="!ml-0">删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

      <!-- 无漏洞闭环完结：测试完成且未发现漏洞时确认「测试通过」，可选同步生成无漏洞报告 -->
      <el-dialog
             :close-on-click-modal="false" v-model="noVulnVisible" title="确认测试完成（无漏洞）" width="480px" append-to-body>
        <el-form label-width="90px">
          <el-form-item label="测试结论">
            <el-input v-model="noVulnConclusion" type="textarea" :rows="3"
                      placeholder="可填写测试范围与结论说明（选填），将记录到计划并写入无漏洞报告" />
          </el-form-item>
          <el-form-item label="生成报告">
            <el-switch v-model="noVulnGenReport" />
            <span class="ml-2 text-xs text-gray-400">同步生成「未发现安全漏洞」报告草稿，可导出归档</span>
          </el-form-item>
          <el-form-item v-if="noVulnGenReport" label="报告标题">
            <el-input v-model="noVulnTitle" placeholder="留空则自动生成" />
          </el-form-item>
        </el-form>
        <div class="text-xs text-gray-400">
          确认后计划状态流转为「测试通过」并记录初测完成时间，站内信通知测试人员；若后续补录漏洞，计划自动重开。
        </div>
        <template #footer>
          <el-button @click="noVulnVisible = false">取消</el-button>
          <el-button type="primary" :loading="noVulnSubmitting" @click="completeNoVuln">确认完结</el-button>
        </template>
      </el-dialog>

    <PdfPreviewDialog ref="previewRef" />
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, ArrowDown, ArrowRight, Document, FolderOpened, WarningFilled, CircleCheck } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import {
  exportJobColor,
  exportJobName,
  exportJobSoftStyle,
  levelName,
  levelSoftStyle,
  planStatusSoftStyle,
  reportStatusName,
  reportStatusSoftStyle,
  softStyle,
  STAT_CARD_COLORS,
  statusSoftStyleWithRetest,
  statusLabel,
} from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import type { Vuln } from '../types'
import { usePlanDetail } from '../composables/usePlanDetail'
import { usePlanReports } from '../composables/usePlanReports'
import { usePlanVulnFlow } from '../composables/usePlanVulnFlow'
import { usePlanVulnPicker } from '../composables/usePlanVulnPicker'
import { useReportExports } from '../composables/useReportExports'
import VulnFormPanel from './VulnFormPanel.vue'
import VulnRetestPanel from './VulnRetestPanel.vue'
import PdfPreviewDialog from './PdfPreviewDialog.vue'
import VulnDetailDialog from './VulnDetailDialog.vue'

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

// ---------- 数据与动作（审计 E-1：按职责下沉为 5 个 composable，此处仅组合） ----------
const {
  plan, vulns, loading, dirty, statusMap, vulStatusMap,
  refresh, ensureStatusDict, reloadAfterChange, claim, quit,
} = usePlanDetail(() => props.planId, prefetchReportExports)

const {
  exportJobs,
  exporting,
  expandedExportId,
  loadJobs,
  toggleExportList,
  stopPolling,
  doExport,
  download,
  removeExportJob,
  dropReport,
  resetExportState,
} = useReportExports(() => plan.value?.system_name ?? 'report')

// 函数声明提升：`loadJobs` 来自上方解构，仅在 refresh() 实际执行时被访问
function prefetchReportExports(reportId: number) {
  return loadJobs(reportId)
}

const {
  vulnPickerVisible, pickerLoading, pickerSearch, pickerLevel, pickerVulns,
  pickerSelection, pickerAttaching, pickerLinkedIds,
  openVulnPicker, loadPickerVulns, attachPickerVulns,
} = usePlanVulnPicker(
  () => props.planId,
  () => vulns.value.map((v) => v.id),
  reloadAfterChange,
)

const { transitionsMap, loadTransitions, transition } = usePlanVulnFlow(
  (status: number) => vulStatusMap.value[status] ?? String(status),
  reloadAfterChange,
)

const {
  genFormVisible, genTitle, genVulIds, generating,
  noVulnVisible, noVulnConclusion, noVulnGenReport, noVulnTitle, noVulnSubmitting,
  toggleGenForm, generateReport, removeReport, startRetest, openNoVulnDialog, completeNoVuln,
} = usePlanReports({
  getPlanId: () => props.planId,
  getSystemName: () => plan.value?.system_name ?? '',
  getNoVulConclusion: () => plan.value?.no_vul_conclusion || '',
  getVulnIds: () => vulns.value.map((v) => v.id),
  onChanged: reloadAfterChange,
  onReportRemoved: dropReport,
})

// ---------- 仅剩的组件内展示态 ----------
const vulnFormVisible = ref(false)

// ---------- 漏洞详情弹窗（公共组件 VulnDetailDialog） ----------
const vulnDetailVisible = ref(false)
const detailVulnId = ref<number | null>(null)

const previewRef = ref<InstanceType<typeof PdfPreviewDialog>>()

const isAdmin = computed(() => auth.user?.permissions?.includes('*') ?? false)
const isTester = computed(() => plan.value?.testers?.some((u) => u.id === auth.user?.id) ?? false)
// 需求：录入漏洞阶段仅认领该计划的账号可录入/编辑/流转漏洞；管理员未认领也不放行
const canManageVulns = computed(() => isTester.value)
// 计划级操作（生成报告、发起复测等）：认领者或管理员
const canOperate = computed(() => isAdmin.value || isTester.value)
// 无漏洞完结仅允许在测试开始前/初测中两个状态发起（后端同步校验无关联漏洞）
const canCompleteNoVuln = computed(() => {
  const s = plan.value?.status
  return s === 10 || s === 20
})

// 步骤条 active 推导：10 未认领→0，已认领→1；20 无漏洞→1、有漏洞→2；30/40→3；50→4；60/70→全部完成（含无漏洞闭环）
const stepActive = computed(() => {
  const s = plan.value?.status
  if (s === 60 || s === 70) return 6
  if (s === 50) return 4
  if (s === 30 || s === 40) return 3
  if (s === 20) return vulns.value.length ? 2 : 1
  return plan.value?.testers?.length ? 1 : 0
})

// 数据加载（refresh）与漏洞选择器（openVulnPicker / loadPickerVulns / attachPickerVulns）
// 已下沉至 composables/usePlanDetail.ts 与 composables/usePlanVulnPicker.ts（审计 E-1）

watch(
  () => [props.visible, props.planId] as const,
  async ([visible]) => {
    if (!visible || !props.planId) return
    // 打开时重置临时态并加载数据
    dirty.value = false
    vulnFormVisible.value = false
    genFormVisible.value = false
    noVulnVisible.value = false
    transitionsMap.value = {}
    resetExportState()
    await ensureStatusDict()
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

// ---------- 漏洞 ----------
// 录入漏洞保存 / 复测记录增删改后重载：选择复测结论（已修复/复测未修复）会同步流转漏洞状态，
// 刷新计划与漏洞列表保证状态列、复测轮数实时联动（与「流转」行为一致）
async function onVulnSaved() {
  vulnFormVisible.value = false
  await reloadAfterChange()
}

async function onRetestChanged() {
  await reloadAfterChange()
}

// ---------- 漏洞详情弹窗 ----------
function openVulnDetail(id: number) {
  detailVulnId.value = id
  vulnDetailVisible.value = true
}

// ---------- 认领 / 漏洞流转 / 报告 / 无漏洞闭环 / 导出 ----------
// 认领与退出认领、漏洞状态流转、报告动作（生成含相似性检查、删除、发起复测、无漏洞闭环完结）、
// 导出历史列表与轮询均已下沉至 composables/（审计 E-1）：
//   usePlanDetail.ts · usePlanVulnFlow.ts · usePlanReports.ts · useReportExports.ts
</script>
