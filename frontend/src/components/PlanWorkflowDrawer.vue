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

      <!-- 无漏洞闭环：已确认「测试通过」时展示结论横幅 -->
      <el-alert v-if="plan.status === 70" type="success" :closable="false" show-icon
                title="本计划已确认无漏洞（测试通过），测试流程已闭环">
        <template #default>
          <div>{{ plan.no_vul_conclusion || '测试完成且未发现安全漏洞，无漏洞报告见下方报告区，可导出 Word/PDF 归档。' }}</div>
          <div class="text-xs mt-1">若后续补录/关联新漏洞，计划将自动重开为「初测中」。</div>
        </template>
      </el-alert>

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
              <el-button type="primary" link class="!p-0" @click="openVulnDetail(row.id)">
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

      <!-- 漏洞详情弹窗：点击漏洞标题在当前抽屉内弹出展示，不再跳转历史漏洞库页面 -->
      <el-dialog
             :close-on-click-modal="false" v-model="vulnDetailVisible" title="漏洞详情" append-to-body :width="detailDialogWidth"
                 @closed="vulnDetailVisible = false">
        <div v-loading="detailLoading" element-loading-text="正在加载漏洞信息…">
          <template v-if="detailVuln">
            <div class="flex items-start justify-between gap-3">
              <div class="text-lg font-semibold text-gray-800 leading-snug break-words">{{ detailVuln.title }}</div>
              <el-button class="shrink-0" :icon="Close" circle plain size="small"
                         @click="vulnDetailVisible = false" aria-label="关闭" />
            </div>
            <div class="flex flex-wrap items-center gap-2 mt-3">
              <span class="tl-tag" :style="levelSoftStyle(detailVuln.level)">{{ levelName(detailVuln.level) }}</span>
              <span class="tl-tag" :style="vulTypeSoftStyle(detailVuln.vul_type)">
                {{ meta?.vul_type?.[detailVuln.vul_type] ?? detailVuln.vul_type }}
              </span>
              <span class="tl-tag" :style="statusSoftStyleEx(detailVuln.status, detailVuln.is_retest)">
                {{ statusLabel(detailVuln.status, detailVuln.is_retest, vulStatusMap) }}
              </span>
              <span v-if="detailVuln.assets?.length" class="tl-tag" :style="softStyle(STAT_CARD_COLORS.gray)">
                关联资产：{{ detailVuln.assets.map((a: any) => a.name).join('、') }}
              </span>
            </div>
            <el-descriptions :column="detailCols" border class="mt-4" size="small">
              <el-descriptions-item label="影响URL" :span="detailCols">
                <div v-if="detailAffectedUrls.length" class="flex flex-col gap-0.5">
                  <span v-for="(u, i) in detailAffectedUrls" :key="i">{{ u }}</span>
                </div>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item v-if="detailVuln.testing_plan_id" label="渗透测试工单">已关联工单</el-descriptions-item>
            </el-descriptions>
            <div v-if="detailSections.length" class="mt-4 space-y-4">
              <section v-for="sec in detailSections" :key="sec.title">
                <h4 class="text-sm font-semibold text-gray-700 mb-1.5">{{ sec.title }}</h4>
                <div v-if="sec.html" class="rich-content" v-html="safeHtml(sec.html)" />
                <div v-else class="text-sm text-gray-400">暂无内容</div>
              </section>
            </div>
          </template>
          <el-empty v-else-if="!detailLoading" description="未获取到漏洞详情" :image-size="80" />
        </div>
        <template #footer>
          <el-button @click="vulnDetailVisible = false">关闭</el-button>
          <el-button type="primary" @click="router.push(`/vulns/${detailVuln?.id}`)">查看完整详情</el-button>
        </template>
      </el-dialog>

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
              <span v-if="pickerLinkedIds.includes(row.id)" class="tl-tag ml-2" :style="softStyle(STAT_CARD_COLORS.blue)">已在本计划</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <span class="tl-tag" :style="statusSoftStyleEx(row.status, row.is_retest)">
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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { Plus, ArrowDown, ArrowRight, Document, FolderOpened, WarningFilled, CircleCheck, Close } from '@element-plus/icons-vue'
import client from '../api/client'
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
  statusSoftStyleEx,
  statusLabel,
  vulTypeSoftStyle,
} from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import { safeHtml } from '../utils/html'
import { useExportJobs } from '../composables/useExportJobs'
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

// 无漏洞闭环完结表单状态
const noVulnVisible = ref(false)
const noVulnConclusion = ref('')
const noVulnGenReport = ref(true)
const noVulnTitle = ref('')
const noVulnSubmitting = ref(false)

const vulnPickerVisible = ref(false)
const pickerLoading = ref(false)
const pickerSearch = ref('')
const pickerLevel = ref<number | ''>('')
const pickerVulns = ref<any[]>([])
const pickerSelection = ref<any[]>([])
const pickerAttaching = ref(false)
// 已关联当前计划的漏洞 ID，用于选择器禁用与标记
const pickerLinkedIds = computed(() => vulns.value.map((v: any) => v.id))

// ---------- 漏洞详情弹窗 ----------
const vulnDetailVisible = ref(false)
const detailLoading = ref(false)
const detailVuln = ref<any>(null)
const meta = ref<any>(null)
// 影响URL 多值（后端换行分隔存储）逐行展示
const detailAffectedUrls = computed<string[]>(() =>
  (detailVuln.value?.affected_url ?? '').split('\n').map((u: string) => u.trim()).filter(Boolean))
// 描述 / 复现 / 修复建议 等富文本区段（仅展示有内容的）
const detailSections = computed(() =>
  [
    { title: '漏洞描述', html: detailVuln.value?.description_html },
    { title: '复现步骤', html: detailVuln.value?.reproduce_html },
    { title: '修复建议', html: detailVuln.value?.solution_html },
  ].filter((s) => s.html || s.title === '漏洞描述'))
// 移动端单列、桌面端双列（响应式）
const detailDialogWidth = computed(() =>
  typeof window !== 'undefined' && window.innerWidth < 640 ? '92%' : '720px')
const detailCols = computed(() =>
  typeof window !== 'undefined' && window.innerWidth < 640 ? 1 : 2)

const { fetchJobs, submitExport, downloadJob, removeExportJob: deleteExportJob } = useExportJobs()
const exportJobs = ref<Record<number, any[]>>({})
const exporting = ref<Record<number, string>>({})
// 当前展开导出历史的报告 ID（点击箭头展示该报告的导出版本列表）
const expandedExportId = ref<number | null>(null)
const previewRef = ref<InstanceType<typeof PdfPreviewDialog>>()
let pollTimer: number | undefined

const isAdmin = computed(() => auth.user?.permissions?.includes('*') ?? false)
const isTester = computed(() => plan.value?.testers?.some((u: any) => u.id === auth.user?.id) ?? false)
// 需求：录入漏洞阶段仅认领该计划的账号可录入/编辑/流转漏洞；管理员未认领也不放行
const canManageVulns = computed(() => isTester.value)
// 计划级操作（生成报告、发起复测等）：认领者或管理员
const canOperate = computed(() => isAdmin.value || isTester.value)
// 无漏洞完结仅允许在测试开始前/初测中两个状态发起（后端同步校验无关联漏洞）
const canCompleteNoVuln = computed(() => [10, 20].includes(plan.value?.status))

// 步骤条 active 推导：10 未认领→0，已认领→1；20 无漏洞→1、有漏洞→2；30/40→3；50→4；60/70→全部完成（含无漏洞闭环）
const stepActive = computed(() => {
  const s = plan.value?.status
  if (s === 60 || s === 70) return 6
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
    // 预取各报告的导出历史，保证「导出历史（N）」计数准确（未展开前即可看到真实数量）
    const reports = planResp.data.reports || []
    await Promise.all(reports.map((r: any) => loadJobs(r.id).catch(() => undefined)))
  } finally {
    loading.value = false
  }
}

// 需求5/7：按危害等级降序（level 小=超危/高危）；同等级按录入时间升序（submit_time，id 兜底）
function sortVulns(items: any[]) {
  return [...items].sort((a, b) =>
    (a.level ?? 99) - (b.level ?? 99) ||
    new Date(a.submit_time ?? 0).getTime() - new Date(b.submit_time ?? 0).getTime() ||
    a.id - b.id)
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
    noVulnVisible.value = false
    transitionsMap.value = {}
    exportJobs.value = {}
    expandedExportId.value = null
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

// ---------- 漏洞详情弹窗 ----------
async function openVulnDetail(id: number) {
  vulnDetailVisible.value = true
  detailLoading.value = true
  detailVuln.value = null
  try {
    if (!meta.value?.vul_type) meta.value = await auth.fetchMeta()
    const { data } = await client.get(`/vulns/${id}`)
    detailVuln.value = data
  } finally {
    detailLoading.value = false
  }
}

// ---------- 报告 ----------
function toggleGenForm() {
  genFormVisible.value = !genFormVisible.value
  if (genFormVisible.value) {
    // 需求8：自动命名「yyyymmdd+测试系统名称+渗透测试报告」
    genTitle.value = `${dayjs().format('YYYYMMDD')}${plan.value?.system_name ?? ''}渗透测试报告`
    genVulIds.value = vulns.value.map((v) => v.id)
  }
}

async function generateReport() {
  generating.value = true
  try {
    // 相似性检查：基础信息与所选漏洞最后编辑时间与历史报告完全一致时，需用户确认继续
    try {
      const { data } = await client.post('/reports/similarity-check', {
        title: genTitle.value.trim(),
        vul_ids: genVulIds.value,
        testing_plan_id: props.planId,
      })
      if (data.similar) {
        const ok = await ElMessageBox.confirm(
          `检测到与历史报告《${genTitle.value.trim()}》高度相似（标题、所选漏洞及漏洞最后编辑时间均未变化），是否仍要继续生成？`,
          '生成高度相似报告',
          { confirmButtonText: '仍要生成', cancelButtonText: '取消', type: 'warning' },
        ).then(() => true).catch(() => false)
        if (!ok) return
      }
    } catch {
      // 检查接口异常时不阻断生成流程
    }
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

async function removeReport(r: any) {
  await client.delete(`/reports/${r.id}`)
  delete exportJobs.value[r.id]
  if (expandedExportId.value === r.id) expandedExportId.value = null
  ElMessage.success('报告已删除')
  dirty.value = true
  await refresh()
}

async function removeExportJob(r: any, job: any) {
  await deleteExportJob(job.id)
  exportJobs.value[r.id] = (exportJobs.value[r.id] || []).filter((j: any) => j.id !== job.id)
}

async function startRetest(r: any) {
  await client.post(`/reports/${r.id}/retest`)
  ElMessage.success('已发起复测，漏洞进入复测中，已自动生成复测报告')
  dirty.value = true
  await refresh()
}

// ---------- 无漏洞闭环 ----------
function openNoVulnDialog() {
  noVulnConclusion.value = plan.value?.no_vul_conclusion || ''
  noVulnGenReport.value = true
  // 自动命名：yyyymmdd+测试系统名称+渗透测试报告（无漏洞）
  noVulnTitle.value = `${dayjs().format('YYYYMMDD')}${plan.value?.system_name ?? ''}渗透测试报告（无漏洞）`
  noVulnVisible.value = true
}

async function completeNoVuln() {
  noVulnSubmitting.value = true
  try {
    await client.post(`/testing-plans/${props.planId}/complete-no-vuln`, {
      conclusion: noVulnConclusion.value,
      generate_report: noVulnGenReport.value,
      title: noVulnGenReport.value ? noVulnTitle.value.trim() : '',
    })
    ElMessage.success('已确认无漏洞，计划流转为「测试通过」')
    noVulnVisible.value = false
    dirty.value = true
    await refresh()
  } finally {
    noVulnSubmitting.value = false
  }
}

// ---------- 导出（提交后轮询任务列表至完成） ----------
async function loadJobs(reportId: number) {
  exportJobs.value[reportId] = await fetchJobs(reportId)
  return exportJobs.value[reportId]
}

// 展开/收起报告的导出历史版本列表；首次展开时懒加载导出记录
async function toggleExportList(r: any) {
  if (expandedExportId.value === r.id) {
    expandedExportId.value = null
    return
  }
  expandedExportId.value = r.id
  if (!exportJobs.value[r.id]?.length) {
    await loadJobs(r.id)
  }
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
    const ok = await submitExport(r.id, fmt, r.title || plan.value?.system_name || 'report')
    if (ok) {
      await loadJobs(r.id)
      pollJobs(r.id)
    }
  } finally {
    delete exporting.value[r.id]
  }
}

function download(job: any) {
  downloadJob(job, plan.value?.system_name || 'report')
}

onBeforeUnmount(stopPolling)
</script>
