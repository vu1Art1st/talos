<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center flex-wrap gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索系统 / 类型 / 部门" clearable class="!w-64"
                @keyup.enter="reload" @clear="reload">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="statusFilter" clearable placeholder="全部状态" class="!w-32" @change="reload">
        <el-option v-for="(name, code) in statusMap" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-select v-model="typeFilter" filterable clearable placeholder="全部类型" class="!w-32" @change="reload">
        <el-option v-for="t in testTypes" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="deptFilter" filterable clearable placeholder="全部部门" class="!w-32" @change="reload">
        <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" class="!w-64"
                      start-placeholder="接收起" end-placeholder="接收止" @change="reload" />
      <el-checkbox v-model="myTests" @change="reload">显示当前可测试系统</el-checkbox>
      <el-checkbox v-model="unclaimed" @change="reload">显示无人认领的测试</el-checkbox>
      <div class="flex-1" />
      <el-button @click="downloadTemplate">
        <el-icon class="mr-1"><Download /></el-icon>导入模板下载
      </el-button>
      <el-upload :show-file-list="false" :http-request="doImport" accept=".xlsx" class="inline-block">
        <el-button :loading="importing">
          <el-icon class="mr-1"><Upload /></el-icon>导入Excel
        </el-button>
      </el-upload>
      <el-button @click="exportExcel">
        <el-icon class="mr-1"><Download /></el-icon>导出Excel
      </el-button>
      <el-button type="primary" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增测试计划
      </el-button>
    </div>

    <el-collapse v-model="statsPanel" class="mb-4">
      <el-collapse-item name="stats">
        <template #title>
          <span class="font-medium">统计概览</span>
          <span class="text-xs text-gray-400 ml-2">（与筛选条件联动实时更新）</span>
        </template>
        <el-checkbox-group v-model="dims" class="mb-3">
          <el-checkbox v-for="d in DIMENSIONS" :key="d.key" :value="d.key">{{ d.label }}</el-checkbox>
        </el-checkbox-group>
        <div v-loading="statsLoading" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <div v-for="d in cardDims" :key="d.key"
               class="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3">
            <div class="text-xs text-gray-500">{{ d.label }}</div>
            <div class="text-2xl font-semibold" :style="{ color: d.color }">{{ stats[d.key] ?? 0 }}</div>
          </div>
        </div>
        <div v-show="dims.includes('vulns_by_month')" ref="monthChartRef" class="w-full h-64 mt-4" />
      </el-collapse-item>
    </el-collapse>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="60"
                       :index="(i: number) => (page - 1) * 20 + i + 1" />
      <el-table-column label="工单ID" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="font-mono">{{ row.ticket_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="plan_name" label="计划名称" min-width="130" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.plan_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="system_name" label="测试系统" min-width="140" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="test_type" label="测试类型" width="100" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="department" label="所属部门" width="110" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="status" label="状态" width="85" sortable="custom">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusMap[row.status] ?? row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="测试人员" width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.testers?.length">
            {{ row.testers.map((u: any) => u.realname || u.username).join('、') }}
          </span>
          <span v-else class="text-gray-400">未认领</span>
        </template>
      </el-table-column>
      <el-table-column label="漏洞统计" min-width="230">
        <template #default="{ row }">
          <span class="inline-flex gap-1">
            <span class="tl-tag" :style="levelBadgeStyle(10, row.stat_critical)">超 {{ row.stat_critical }}</span>
            <span class="tl-tag" :style="levelBadgeStyle(20, row.stat_high)">高 {{ row.stat_high }}</span>
            <span class="tl-tag" :style="levelBadgeStyle(30, row.stat_medium)">中 {{ row.stat_medium }}</span>
            <span class="tl-tag" :style="levelBadgeStyle(40, row.stat_low)">低 {{ row.stat_low }}</span>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="关联漏洞" width="78">
        <template #default="{ row }">
          <el-popover v-if="row.vuls?.length" placement="right" width="360" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.vuls.length }} 个</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="v in row.vuls" :key="v.id" class="flex items-center gap-2">
                <span class="tl-tag" :style="levelSoftStyle(v.level)">
                  {{ levelName(v.level) }}
                </span>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/vulns/${v.id}`)">{{ v.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="关联报告" width="78">
        <template #default="{ row }">
          <el-popover v-if="row.reports?.length" placement="right" width="360" trigger="hover">
            <template #reference>
              <el-button size="small" type="success" link>{{ row.reports.length }} 份</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="r in row.reports" :key="r.id" class="flex items-center gap-2">
                <el-tag size="small" :type="r.status === 'completed' ? 'success' : 'info'">
                  {{ reportStatusName(r.status) }}
                </el-tag>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/reports/${r.id}`)">{{ r.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="预估/实际人天" width="105">
        <template #default="{ row }">
          <span>{{ row.est_mandays ?? 0 }} / {{ row.actual_mandays ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="工单提起" width="100">
        <template #default="{ row }">{{ row.ticket_time || '-' }}</template>
      </el-table-column>
      <el-table-column prop="receive_time" label="需求接收" width="100" sortable="custom">
        <template #default="{ row }">{{ row.receive_time || '-' }}</template>
      </el-table-column>
      <el-table-column prop="retest_done_time" label="复测完成" width="100" sortable="custom">
        <template #default="{ row }">{{ row.retest_done_time || '-' }}</template>
      </el-table-column>
      <el-table-column label="复测轮数" width="78">
        <template #default="{ row }">
          <el-popover v-if="row.retest_round_count" placement="left" width="380" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.retest_round_count }} 轮</el-button>
            </template>
            <el-table :data="row.retest_rounds" size="small">
              <el-table-column label="轮次" width="55">
                <template #default="{ row: r }">第 {{ r.round_no }} 轮</template>
              </el-table-column>
              <el-table-column label="开始时间" width="105">
                <template #default="{ row: r }">{{ fmtTime(r.start_time) }}</template>
              </el-table-column>
              <el-table-column label="完成时间" width="105">
                <template #default="{ row: r }">
                  <el-tag v-if="!r.done_time" size="small" type="warning">进行中</el-tag>
                  <span v-else>{{ fmtTime(r.done_time) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="来源" show-overflow-tooltip>
                <template #default="{ row: r }">{{ r.source || '-' }}</template>
              </el-table-column>
            </el-table>
          </el-popover>
          <span v-else class="text-gray-400">0 轮</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openWorkflow(row)">流程</el-button>
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该计划？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑测试计划' : '新增测试计划'" width="680px">
    <el-form :model="form" label-width="100px">
      <div class="grid grid-cols-2 gap-x-4">
        <el-form-item label="计划名称">
          <el-input v-model="form.plan_name" placeholder="与测试系统区分的测试计划名称" />
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
        <el-form-item label="测试系统" required>
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
            <el-option v-for="(name, code) in statusMap" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="工单提起">
          <el-date-picker v-model="form.ticket_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="需求接收">
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
          <el-input-number v-model="form.actual_mandays" :min="0" :precision="1" :step="0.5" class="!w-full" />
        </el-form-item>
      </div>
      <div v-if="statsAuto" class="text-xs text-gray-400 mb-2 pl-[100px]">
        已有关联漏洞，统计由系统按漏洞等级自动重算
      </div>
      <div v-if="form.id && !statusEditable" class="text-xs text-gray-400 mb-2 pl-[100px]">
        认领该计划后才可修改测试状态
      </div>
      <el-form-item label="漏洞简述">
        <el-input v-model="form.brief" type="textarea" :rows="2" placeholder="漏洞情况简述" />
      </el-form-item>
      <el-form-item label="详细描述">
        <el-input v-model="form.detail" type="textarea" :rows="4" placeholder="数据来源等详细信息" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!form.system_name" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <PlanWorkflowDrawer v-model:visible="workflowVisible" :plan-id="workflowPlanId" @changed="onWorkflowChanged" />

  <AssetFormDialog v-model:visible="assetDialogVisible" :asset="assetPrefill" @saved="onAssetCreated" />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle, levelBadgeStyle } from '../utils/colors'
import PlanWorkflowDrawer from '../components/PlanWorkflowDrawer.vue'
import AssetFormDialog from '../components/AssetFormDialog.vue'

const auth = useAuthStore()
const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const statusFilter = ref<number | null>(null)
const typeFilter = ref<string>('')
const deptFilter = ref<string>('')
const dateRange = ref<[string, string] | null>(null)
const myTests = ref(false)
const unclaimed = ref(false)
const sort = reactive<{ prop: string; order: string }>({ prop: '', order: '' })
const loading = ref(false)
const dialogVisible = ref(false)
const statusMap = ref<Record<number, string>>({})
const dialogRow = ref<any>(null)
const testTypes = ref<string[]>([])
const departments = ref<string[]>([])

// ---------- 统计面板 ----------
const DIMENSIONS = [
  { key: 'total_plans', label: '测试计划总数', color: '#409EFF' },
  { key: 'retest_done_plans', label: '复测完成数', color: '#67C23A' },
  { key: 'first_test_count', label: '初测次数', color: '#E6A23C' },
  { key: 'retest_count', label: '复测次数', color: '#F56C6C' },
  { key: 'total_test_count', label: '总测试次数', color: '#909399' },
  { key: 'est_mandays_total', label: '预估人天总计', color: '#409EFF' },
  { key: 'actual_mandays_total', label: '实际人天总计', color: '#67C23A' },
  { key: 'remaining_est_mandays', label: '剩余预估人天（未测试）', color: '#E6A23C' },
  { key: 'vulns_by_month', label: '按月漏洞数', color: '#409EFF' },
] as const
const STATS_DIMS_KEY = 'testing_plan_stats_dims'
const statsPanel = ref<string[]>(['stats'])
const dims = ref<string[]>(loadDims())
const stats = ref<Record<string, number>>({})
const statsLoading = ref(false)
const monthChartRef = ref<HTMLElement>()
let monthChart: echarts.ECharts | null = null

function loadDims(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(STATS_DIMS_KEY) || 'null')
    if (Array.isArray(saved) && saved.length) return saved
  } catch { /* ignore */ }
  return DIMENSIONS.map((d) => d.key)
}

// 勾选的计数类维度（排除图表维度）以数字卡片展示
const cardDims = computed(() =>
  DIMENSIONS.filter((d) => d.key !== 'vulns_by_month' && dims.value.includes(d.key)))

watch(dims, (v) => {
  localStorage.setItem(STATS_DIMS_KEY, JSON.stringify(v))
  if (v.includes('vulns_by_month')) nextTick(renderMonthChart)
})

const statusTag = (s: number) =>
  ({ 10: 'info', 20: 'warning', 30: 'primary', 40: 'danger', 50: 'warning', 60: 'success' } as Record<number, string>)[s] ?? 'info'

const levelName = (lv: number) =>
  ({ 10: '严重', 20: '高危', 30: '中危', 40: '低危', 50: '安全' } as Record<number, string>)[lv] ?? lv

const fmtTime = (t: string | null) => (t ? String(t).slice(0, 10) : '-')

const reportStatusName = (s: string) =>
  ({ draft: '草稿', final: '定稿', completed: '已完成' } as Record<string, string>)[s] ?? s

// 旧数据的值可能不在字典/组织列表中，临时追加以正常回显
const testTypeOptions = computed(() =>
  form.value.test_type && !testTypes.value.includes(form.value.test_type)
    ? [...testTypes.value, form.value.test_type]
    : testTypes.value)
const departmentOptions = computed(() =>
  form.value.department && !departments.value.includes(form.value.department)
    ? [...departments.value, form.value.department]
    : departments.value)

const isAdmin = computed(() => auth.user?.permissions?.includes('*') ?? false)
const isTester = (row: any) => row.testers?.some((u: any) => u.id === auth.user?.id) ?? false
const canOperate = (row: any) => isAdmin.value || isTester(row)

// 状态：新建时仅管理员可指定；编辑时须为认领者或管理员
const statusEditable = computed(() =>
  form.value.id ? (dialogRow.value ? canOperate(dialogRow.value) : false) : isAdmin.value)
// 有关联漏洞时统计自动重算，禁止手填
const statsAuto = computed(() => (dialogRow.value?.vuls?.length ?? 0) > 0)

const emptyForm = () => ({
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
  brief: '',
  detail: '',
})
const form = ref(emptyForm())

function filterParams(): Record<string, any> {
  const params: Record<string, any> = { search: search.value }
  if (statusFilter.value !== null && statusFilter.value !== ('' as any)) params.status = statusFilter.value
  if (typeFilter.value) params.test_type = typeFilter.value
  if (deptFilter.value) params.department = deptFilter.value
  if (dateRange.value?.length === 2) {
    params.receive_from = dateRange.value[0]
    params.receive_to = dateRange.value[1]
  }
  if (myTests.value) params.my_tests = true
  if (unclaimed.value) params.unclaimed = true
  if (sort.prop) {
    params.sort = sort.prop
    params.order = sort.order
  }
  return params
}

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/testing-plans', {
      params: { ...filterParams(), page: p, size: 20 },
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSortChange({ prop, order }: any) {
  sort.prop = order ? prop : ''
  sort.order = order === 'ascending' ? 'asc' : order === 'descending' ? 'desc' : ''
  load(1)
}

async function loadStats() {
  statsLoading.value = true
  try {
    const { data } = await client.get('/testing-plans/stats', { params: filterParams() })
    stats.value = data
    if (dims.value.includes('vulns_by_month')) nextTick(renderMonthChart)
  } finally {
    statsLoading.value = false
  }
}

function renderMonthChart() {
  if (!monthChartRef.value) return
  if (!monthChart) monthChart = echarts.init(monthChartRef.value)
  const rows = (stats.value as any).vulns_by_month ?? []
  monthChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 30, bottom: 40 },
    title: { text: '按月漏洞数', textStyle: { fontSize: 13, fontWeight: 'normal', color: '#909399' } },
    xAxis: { type: 'category', data: rows.map((r: any) => r.month), axisLabel: { rotate: 45 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: rows.map((r: any) => r.count), itemStyle: { color: '#409EFF' }, barMaxWidth: 32 }],
  })
  monthChart.resize()
}

// 筛选变化：列表回到首页并同步刷新统计
async function reload() {
  await Promise.all([load(1), loadStats()])
}

async function exportExcel() {
  const { data } = await client.get('/testing-plans/export', {
    params: filterParams(), responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = '测试计划导出.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadTemplate() {
  const { data } = await client.get('/testing-plans/import/template', { responseType: 'blob' })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = '测试计划导入模板.xlsx'
  a.click()
  URL.revokeObjectURL(url)
}

const importing = ref(false)

async function doImport(options: any) {
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', options.file)
    const { data } = await client.post('/testing-plans/import', fd)
    if (data.failed > 0) {
      await ElMessageBox.alert(
        `共 ${data.total} 行，新增 ${data.created} 行，更新 ${data.updated} 行，失败 ${data.failed} 行：<br/>${data.errors.join('<br/>')}`,
        '导入结果', { dangerouslyUseHTMLString: true },
      )
    } else {
      ElMessage.success(`导入完成：新增 ${data.created} 条，更新 ${data.updated} 条`)
    }
    await Promise.all([load(1), loadStats()])
  } finally {
    importing.value = false
  }
}

function openDialog(row?: any) {
  dialogRow.value = row ?? null
  form.value = row ? { ...emptyForm(), ...row } : emptyForm()
  form.value.asset_ids = Array.isArray(form.value.asset_ids) ? form.value.asset_ids : []
  assetOptions.value = []
  if (form.value.asset_ids.length) loadAssetLabels()
  prevAssetIds = [...form.value.asset_ids]
  dialogVisible.value = true
}

// ---------- 关联资产 ----------
const assetOptions = ref<any[]>([])
const assetLoading = ref(false)
const assetCache = ref<Record<number, any>>({})
let assetSearchTimer: ReturnType<typeof setTimeout> | null = null
const assetDialogVisible = ref(false)
const assetPrefill = ref<any>(null)
let lastAssetKeyword = ''
let prevAssetIds: number[] = []

// 下拉展示：系统名称 +（子系统）+（系统类型，用于区分同名系统的不同环境）
function assetLabel(a: any) {
  const parts = [a.name]
  if (a.sub_system) parts.push(`（${a.sub_system}）`)
  if (a.system_type) parts.push(`（${a.system_type}）`)
  return parts.join('')
}

async function searchAssets(keyword: string) {
  lastAssetKeyword = keyword
  assetLoading.value = true
  try {
    const { data } = await client.get('/assets', {
      params: { search: keyword, page: 1, size: 50 },
    })
    assetOptions.value = data.items.map((a: any) => {
      assetCache.value[a.id] = a
      return { id: a.id, label: assetLabel(a) }
    })
  } finally {
    assetLoading.value = false
  }
}

// 新增测试计划时提供"新增资产"入口，保存后自动关联并填充测试系统/所属部门
function openCreateAsset() {
  assetPrefill.value = lastAssetKeyword ? { name: lastAssetKeyword } : null
  assetDialogVisible.value = true
}

function onAssetCreated(asset: any) {
  if (!asset?.id) return
  assetCache.value[asset.id] = asset
  const label = assetLabel(asset)
  if (!assetOptions.value.some((o: any) => o.id === asset.id)) {
    assetOptions.value.push({ id: asset.id, label })
  }
  if (!form.value.asset_ids.includes(asset.id)) {
    form.value.asset_ids.push(asset.id)
  }
  // 自动填充测试系统与所属部门（资产信息），用户仍可手动修改/覆盖
  form.value.system_name = label
  form.value.department = asset.department || ''
  prevAssetIds = [...form.value.asset_ids]
}

// 点选关联资产后自动带出测试系统/所属部门（仅新增模式），仍可手动修改
function onAssetsChange(ids: number[]) {
  if (form.value.id) return
  const added = ids.filter((id) => !prevAssetIds.includes(id))
  prevAssetIds = [...ids]
  if (!added.length) return
  const asset = assetCache.value[added[added.length - 1]]
  if (!asset) return
  form.value.system_name = assetLabel(asset)
  form.value.department = asset.department || ''
}

async function loadAssetLabels() {
  const ids = [...form.value.asset_ids]
  if (!ids.length) return
  const rows = await Promise.all(
    ids.map((id: number) => client.get(`/assets/${id}`).catch(() => null)),
  )
  for (const r of rows) {
    const a = r?.data
    if (a && !assetOptions.value.some((o: any) => o.id === a.id)) {
      assetCache.value[a.id] = a
      assetOptions.value.push({ id: a.id, label: assetLabel(a) })
    }
  }
}

async function save() {
  const body = { ...form.value }
  delete (body as any).testers
  delete (body as any).vuls
  delete (body as any).reports
  delete (body as any).retest_rounds
  delete (body as any).retest_round_count
  delete (body as any).ticket_id
  delete (body as any).ticket_seq
  if (form.value.id) {
    await client.put(`/testing-plans/${form.value.id}`, body)
  } else {
    await client.post('/testing-plans', body)
  }
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await Promise.all([load(), loadStats()])
}

async function loadTestTypes() {
  const { data } = await client.get('/dict/test_type')
  testTypes.value = data.map((o: any) => o.name)
}

async function loadDepartments() {
  const { data } = await client.get('/groups')
  departments.value = data.map((g: any) => g.name)
}

async function addTestType() {
  const { value } = await ElMessageBox.prompt('请输入新的测试类型名称', '新增测试类型', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/dict/test_type', { name: value.trim() })
  ElMessage.success('测试类型已新增')
  await loadTestTypes()
  form.value.test_type = value.trim()
}

async function addDepartment() {
  const { value } = await ElMessageBox.prompt('请输入新的部门（组织）名称，保存后同步至组织管理', '新增部门', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/groups', { name: value.trim(), remark: '' })
  ElMessage.success('部门已新增')
  await loadDepartments()
  form.value.department = value.trim()
}

async function remove(id: number) {
  await client.delete(`/testing-plans/${id}`)
  ElMessage.success('删除成功')
  await Promise.all([load(), loadStats()])
}

// ---------- 流程抽屉 ----------
const workflowVisible = ref(false)
const workflowPlanId = ref<number | null>(null)

function openWorkflow(row: any) {
  workflowPlanId.value = row.id
  workflowVisible.value = true
}

// 抽屉内发生认领/漏洞/报告/复测等变更后刷新列表与统计
async function onWorkflowChanged() {
  await Promise.all([load(), loadStats()])
}

function onResize() {
  monthChart?.resize()
}

onMounted(async () => {
  const meta = await auth.fetchMeta()
  statusMap.value = meta?.testing_plan_status ?? {}
  window.addEventListener('resize', onResize)
  await Promise.all([load(1), loadStats(), loadTestTypes(), loadDepartments()])
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  monthChart?.dispose()
  monthChart = null
})
</script>

<style scoped>
/* 操作列紧凑排列：压缩按钮间距避免换行 */
:deep(.op-col .cell) {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
:deep(.op-col .el-button) {
  margin-left: 0;
}
</style>
