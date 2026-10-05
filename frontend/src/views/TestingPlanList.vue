<template>
  <div class="space-y-3">
    <FilterToolbar>
      <div class="tl-search-field">
        <el-input v-model="search" placeholder="搜索系统 / 类型 / 部门 / 工单ID" clearable
                  @keyup.enter="reload" @clear="reload">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <el-select v-model="rangeKind" placeholder="统计周期" class="!w-28" clearable @change="onRangeChange">
        <el-option v-for="o in DATE_RANGE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <!-- daterange 根节点即 .el-input__wrapper（自带 flex-grow:1），在 .tl-filterbar 内会被拉伸撑满，
           必须显式 grow-0 才能让 !w-64 的固定宽度生效 -->
      <el-date-picker v-if="rangeKind === 'custom'" v-model="customRange" type="daterange"
                      value-format="YYYY-MM-DD" class="!w-64 !grow-0" start-placeholder="周期开始"
                      end-placeholder="周期结束" @change="reload" />
      <el-popover
        :visible="filterVisible"
        trigger="manual"
        placement="bottom-start"
        :width="960"
      >
        <template #reference>
          <!-- manual 模式下 el-popover 不监听外部点击，失焦收回由 useClickOutside 负责；
               触发按钮需包一层才能取到真实 DOM（el-button 的 ref 是组件实例） -->
          <span ref="filterTriggerRef" class="inline-flex">
            <el-button :type="filterCount ? 'primary' : 'default'" @click="filterVisible = !filterVisible">
              <el-icon class="mr-1"><Filter /></el-icon>筛选
              <span v-if="filterCount" class="filter-count">{{ filterCount }}</span>
            </el-button>
          </span>
        </template>
        <div ref="filterPanelRef" class="filter-panel">
          <div class="mb-2 text-sm font-medium">聚合筛选（支持条件分组与嵌套）</div>
          <div class="filter-presets">
            <span class="filter-presets__label">快捷预设</span>
            <el-button
              size="small"
              :type="hasPreset('pending') ? 'primary' : 'default'"
              plain
              @click="applyPreset('pending')"
            >待办流程</el-button>
            <el-button
              size="small"
              :type="hasPreset('unclaimed') ? 'primary' : 'default'"
              plain
              @click="applyPreset('unclaimed')"
            >无人认领</el-button>
            <el-button
              size="small"
              :type="hasPreset('my_tests') ? 'primary' : 'default'"
              plain
              :disabled="!auth.user?.id"
              @click="applyPreset('my_tests')"
            >当前可测试</el-button>
          </div>
          <FilterBuilder v-model="filterTree" :fields="filterFields" @change="onFiltersChange" />
        </div>
      </el-popover>
      <template #actions>
      <!-- 导入导出：三操作收纳为下拉，分别对应原「导入模板下载 / 导入 Excel / 导出 Excel」 -->
      <el-dropdown trigger="click" @command="onImportExport">
        <el-button>
          导入导出<el-icon class="ml-1"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="template">
              <el-icon class="mr-1"><Download /></el-icon>导入模板下载
            </el-dropdown-item>
            <el-dropdown-item command="import" :disabled="importing">
              <el-icon class="mr-1"><Upload /></el-icon>导入 Excel
            </el-dropdown-item>
            <el-dropdown-item command="export">
              <el-icon class="mr-1"><Download /></el-icon>导出 Excel
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="importInputRef" type="file" accept=".xlsx" class="hidden" @change="onImportFileChange" />
      <el-button type="primary" class="btn-min" @click="openCreateDialog">
        <el-icon class="mr-1"><Plus /></el-icon>新增渗透测试工单
      </el-button>
      </template>
    </FilterToolbar>

    <el-collapse v-model="statsPanel" class="tl-collapse mb-3">
      <el-collapse-item name="stats">
        <template #title>
          <span class="tl-collapse-title">
            <span class="tl-collapse-title__main">统计概览</span>
            <span class="tl-collapse-title__sub">（与筛选条件联动实时更新）</span>
          </span>
        </template>
        <div class="px-2">
          <!-- 维度勾选：可换行，避免条件过多时溢出边界 -->
          <el-checkbox-group v-model="dims" class="mb-3 flex flex-wrap gap-x-4 gap-y-1">
            <el-checkbox v-for="d in DIMENSIONS" :key="d.key" :value="d.key">{{ d.label }}</el-checkbox>
          </el-checkbox-group>
          <div v-loading="statsLoading" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <StatCard v-for="d in cardDims" :key="d.key" :label="d.label" :color="d.color" :value="statValue(d.key)" />
          </div>
          <div v-show="dims.includes('vulns_by_month')" ref="monthChartRef" class="w-full h-64 mt-3" />
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-collapse v-model="conclusionPanel" class="tl-collapse mb-3">
      <el-collapse-item name="conclusion">
        <template #title>
          <span class="tl-collapse-title">
            <span class="tl-collapse-title__main">结论输出</span>
            <span class="tl-collapse-title__sub">
              （按统计周期生成：初测完成 / 复测发起 / 复测完成 / 复测报告生成，可复制 / 下载附件）
            </span>
          </span>
        </template>
        <div v-loading="conclusionLoading" class="px-2 py-1">
          <div class="conclusion-box">
            <p class="conclusion-text">{{ conclusion.summary || '暂无符合条件的渗透测试工单，请先调整筛选条件' }}</p>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 mt-3">
            <StatCard label="部门数" :color="STAT_CARD_COLORS.blue" :value="conclusion.departments ?? 0" />
            <StatCard label="完成系统数" :color="STAT_CARD_COLORS.green" :value="conclusion.systems ?? 0" />
            <StatCard label="初测完成系统" :color="STAT_CARD_COLORS.blue" :value="conclusion.first_test_systems ?? 0" />
            <StatCard label="初测发现漏洞" :color="STAT_CARD_COLORS.red" :value="conclusion.first_test_vulns ?? 0" />
            <StatCard label="复测完成系统" :color="STAT_CARD_COLORS.orange" :value="conclusion.retest_systems ?? 0" />
            <StatCard label="已完成整改" :color="STAT_CARD_COLORS.green" :value="conclusion.retest_fixed_systems ?? 0" />
            <StatCard label="未完成整改" :color="STAT_CARD_COLORS.red" :value="conclusion.retest_unfixed_systems ?? 0" />
            <StatCard label="周期内发起复测" :color="STAT_CARD_COLORS.orange" :value="conclusion.retest_started_systems ?? 0" />
            <StatCard label="周期内复测报告" :color="STAT_CARD_COLORS.blue" :value="conclusion.retest_report_count ?? 0" />
          </div>
          <div class="flex gap-2 mt-3">
            <el-button type="primary" :disabled="!conclusion.summary" @click="copyConclusion">复制结论</el-button>
            <el-button :disabled="!conclusion.summary" @click="downloadConclusion">下载附件</el-button>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-card shadow="never" body-style="padding: 0 0 12px">
    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange"
              :default-sort="{ prop: 'receive_time', order: 'descending' }">
      <template #empty>
        <el-empty :image-size="80"
                  description="暂无符合条件的渗透测试工单，请调整筛选条件" />
      </template>
      <el-table-column type="index" label="序号" width="64"
                       :index="(i: number) => (page - 1) * size + i + 1" />
      <el-table-column label="工单ID" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="font-mono">{{ row.ticket_id || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="plan_name" label="计划名称" min-width="130" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.plan_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="system_name" label="测试系统" min-width="140" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="test_type" label="测试类型" width="150" show-overflow-tooltip sortable="custom"
                       label-class-name="col-test-type" />
      <el-table-column prop="department" label="所属部门" width="110" show-overflow-tooltip sortable="custom" />
      <el-table-column label="工单提起" width="100">
        <template #default="{ row }">{{ fmtDate(row.ticket_time) }}</template>
      </el-table-column>
      <el-table-column prop="receive_time" label="需求接收" width="115" sortable="custom">
        <template #default="{ row }">{{ fmtDate(row.receive_time) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="85" sortable="custom">
        <template #default="{ row }">
          <span class="dot-tag" :style="planStatusDotStyle(row.status)">
            <i></i>{{ statusMap[row.status] ?? row.status }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="first_test_done_time" label="初测完成" width="115" sortable="custom">
        <template #default="{ row }">{{ fmtDate(row.first_test_done_time) }}</template>
      </el-table-column>
      <el-table-column prop="retest_done_time" label="复测完成" width="115" sortable="custom">
        <template #default="{ row }">{{ fmtDate(row.retest_done_time) }}</template>
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
      <el-table-column label="测试人员" width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.testers?.length">
            {{ row.testers.map((u: { realname?: string | null; username?: string }) => u.realname || u.username).join('、') }}
          </span>
          <span v-else class="text-gray-400">未认领</span>
        </template>
      </el-table-column>
      <el-table-column label="预估/实际人天" width="135">
        <template #default="{ row }">
          <span>{{ row.est_mandays ?? 0 }} / {{ row.actual_mandays ?? 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联漏洞" width="110">
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
      <el-table-column label="关联报告" width="110">
        <template #default="{ row }">
          <el-popover v-if="row.reports?.length" placement="right" width="440" trigger="hover">
            <template #reference>
              <el-button size="small" type="success" link>{{ row.reports.length }} 份</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="r in row.reports" :key="r.id" class="flex items-center gap-2">
                <!-- 复测状态（未发起复测 / 复测中 / 复测完成）：区分已复测与未复测的报告 -->
                <span class="tl-tag" :style="retestStateSoftStyle(r.retest_state)">
                  {{ retestStateName(r.retest_state) }}
                </span>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/reports/${r.id}`)">{{ r.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="复测轮数" width="110">
        <template #default="{ row }">
          <el-popover v-if="row.retest_round_count" placement="left" width="480" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.retest_round_count }} 轮</el-button>
            </template>
            <el-table :data="row.retest_rounds" size="small">
              <el-table-column label="轮次" width="55">
                <template #default="{ row: r }">第 {{ r.round_no }} 轮</template>
              </el-table-column>
              <el-table-column label="开始时间" width="105">
                <template #default="{ row: r }">{{ fmtDateTime(r.start_time) }}</template>
              </el-table-column>
              <el-table-column label="完成时间" width="105">
                <template #default="{ row: r }">
                  <span v-if="!r.done_time" class="tl-tag" :style="softStyle(STAT_CARD_COLORS.orange)">进行中</span>
                  <span v-else>{{ fmtDateTime(r.done_time) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="源报告" show-overflow-tooltip>
                <template #default="{ row: r }">{{ reportTitleById(row, r.src_report_id) }}</template>
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
          <el-button size="small" type="primary" link @click="openPlanDrawer(row, 'info')">工单信息</el-button>
          <el-button size="small" type="primary" link @click="openWorkflow(row)">流程</el-button>
          <el-popconfirm title="确认删除该计划？" @confirm="removePlan(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="px-4">
      <TlPagination v-model:page="page" v-model:size="size" :total="total"
                    @page-change="load" @size-change="onSizeChange" />
    </div>
  </el-card>
  </div>

  <!-- 新增工单：编辑查看统一在抽屉「工单信息」标签内完成 -->
  <el-dialog :close-on-click-modal="false" v-model="createVisible" title="新增渗透测试工单" width="800px">
    <PlanInfoPanel v-if="createVisible" mode="create" :status-map="statusMap"
                   @saved="onCreated" @cancel="createVisible = false" />
  </el-dialog>

  <PlanWorkflowDrawer v-model:visible="workflowVisible" v-model:tab="workflowTab"
                      :plan-id="workflowPlanId" :focus-vuln-id="focusVulnId" @changed="onWorkflowChanged" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Download, Filter, Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import {
  levelBadgeStyle,
  levelName,
  levelSoftStyle,
  planStatusDotStyle,
  retestStateName,
  retestStateSoftStyle,
  softStyle,
  STAT_CARD_COLORS,
} from '../utils/colors'
import { fmtDate, fmtDateTime } from '../utils/format'
import { DATE_RANGE_OPTIONS } from '../utils/dateRange'
import PlanInfoPanel from '../components/PlanInfoPanel.vue'
import PlanWorkflowDrawer from '../components/PlanWorkflowDrawer.vue'
import StatCard from '../components/StatCard.vue'
import FilterBuilder from '../components/FilterBuilder.vue'
import FilterToolbar from '../components/FilterToolbar.vue'
import TlPagination from '../components/TlPagination.vue'
import { useClickOutside } from '../composables/useClickOutside'
import { useListPage } from '../composables/useListPage'
import type { FilterFieldDef, PlanDrawerTab, QueryParams, TestingPlan, TestingPlanFilterOptions } from '../types'
import { usePlanConclusion } from '../composables/usePlanConclusion'
import { usePlanFilters } from '../composables/usePlanFilters'
import { usePlanImportExport } from '../composables/usePlanImportExport'
import { DIMENSIONS as PLAN_STAT_DIMENSIONS, usePlanStats } from '../composables/usePlanStats'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
// 函数声明提升：筛选条件变化 → 列表回到首页并同步刷新统计（reload 定义见下方）
function triggerReload() {
  reload()
}

// ---------- 筛选状态（审计 E-2：已下沉至 composables/usePlanFilters.ts） ----------
const {
  rangeKind, customRange, onRangeChange,
  filterVisible, filterTree, filterCount, hasPreset, applyPreset, onFiltersChange,
  periodLabel, buildParams, disposeFilters,
} = usePlanFilters(triggerReload, { getCurrentUserId: () => auth.user?.id })

// 聚合筛选面板：manual 模式下 el-popover 不监听外部点击，点空白处不会收回 —— 由本函数补回。
// ignoreSelectors 放行面板内 el-select / el-date-picker / el-popconfirm 的 teleport 浮层，
// 否则点开下拉会把整个面板一起关掉。
const filterTriggerRef = ref<HTMLElement>()
const filterPanelRef = ref<HTMLElement>()
useClickOutside(
  [filterTriggerRef, filterPanelRef],
  filterVisible,
  () => { filterVisible.value = false },
  { ignoreSelectors: ['.el-popper'] },
)

// 列表查询：extraParams 以函数声明传入（提升），保证「查询参数口径」全站唯一
const { items, total, page, size, search, sort, loading, load, onSortChange, onSizeChange } = useListPage<TestingPlan>('/testing-plans', {
  defaultSort: { prop: 'receive_time', order: 'desc' },
  extraParams: filterParams,
})
// 状态字典（筛选与信息面板共用）；新增弹窗仅有显隐状态，表单逻辑在 PlanInfoPanel 内
const statusMap = ref<Record<number, string>>({})
const createVisible = ref(false)
const filterOptions = ref<TestingPlanFilterOptions>({
  system_names: [], test_types: [], departments: [], testers: [],
})

async function loadFilterOptions() {
  const { data } = await client.get<TestingPlanFilterOptions>('/testing-plans/filter-options')
  filterOptions.value = data
}

// 时间范围筛选状态（rangeKind / customRange / onRangeChange）已下沉至 composables/usePlanFilters.ts

// ---------- 结论输出（审计 E-2：已下沉至 composables/usePlanConclusion.ts） ----------
const {
  conclusionPanel, conclusion, conclusionLoading,
  loadConclusion, copyConclusion, downloadConclusion,
} = usePlanConclusion(conclusionParams)

// 聚合筛选（规则持久化 / 完整性判定 / 防抖刷新）已下沉至 composables/usePlanFilters.ts（审计 E-2）

// 支持聚合筛选的列字段定义（与后端 _PLAN_FILTER_FIELDS 白名单保持一致）
const filterFields = computed<FilterFieldDef[]>(() => [
  {
    key: 'system_name', label: '测试系统', type: 'text', group: 'common',
    multiple: true, operators: ['eq', 'ne'],
    options: filterOptions.value.system_names.map((name) => ({ label: name, value: name })),
  },
  {
    key: 'test_type', label: '测试类型', type: 'text', group: 'common',
    multiple: true, operators: ['eq', 'ne'],
    options: filterOptions.value.test_types.map((name) => ({ label: name, value: name })),
  },
  {
    key: 'department', label: '所属部门', type: 'text', group: 'common',
    multiple: true, operators: ['eq', 'ne'],
    options: filterOptions.value.departments.map((name) => ({ label: name, value: name })),
  },
  {
    key: 'status', label: '状态', type: 'enum', group: 'common',
    multiple: true, operators: ['eq', 'ne'],
    options: Object.entries(statusMap.value).map(([k, v]) => ({ label: v, value: Number(k) })),
  },
  {
    key: 'testers', label: '测试人员', type: 'text', group: 'common',
    multiple: true, operators: ['eq', 'ne'],
    options: [
      ...filterOptions.value.testers.map((tester) => ({
        label: tester.name, value: tester.id,
      })),
      { label: '未认领', value: '__unclaimed__' },
    ],
  },
  {
    key: 'receive_time', label: '需求接收', type: 'date', group: 'advanced',
    operators: ['gte', 'lte', 'between'],
  },
  {
    key: 'est_mandays', label: '预估人天', type: 'number', group: 'advanced',
    operators: ['gte', 'lte', 'between'],
  },
  {
    key: 'actual_mandays', label: '实际人天', type: 'number', group: 'advanced',
    operators: ['gte', 'lte', 'between'],
  },
])

// ---------- 统计面板（审计 E-2：已下沉至 composables/usePlanStats.ts，维度常量随之下沉） ----------
const {
  dims, stats, statsLoading, monthChartRef, cardDims, statsPanel,
  loadStats, resizeChart, disposeChart,
} = usePlanStats(filterParams)
const DIMENSIONS = PLAN_STAT_DIMENSIONS

/** 统计卡数值：仅数值维度参与渲染（`cardDims` 已排除图表维度 vulns_by_month） */
function statValue(key: string): number {
  const v = (stats.value as Record<string, unknown>)[key]
  return typeof v === 'number' ? v : 0
}

/** 查询参数拼装：列表 / 统计 / 结论 / 导出共用（口径由 usePlanFilters.buildParams 统一）
 *  注意：useListPage 返回的 `search` 是 Ref、`sort` 是响应式对象（见 ListPageState），取值方式不同 */
function filterParams(): QueryParams {
  return buildParams(search.value, sort)
}

/** 结论专用参数：在列表口径上附加周期名称（供结论文案括注「（本周）」，仅结论两个接口使用） */
function conclusionParams(): QueryParams {
  return { ...filterParams(), period_label: periodLabel.value }
}

/** 复测轮次的「源报告」标题：由 src_report_id 在工单关联报告中反查（旧数据无关联时显示 -） */
function reportTitleById(row: TestingPlan, reportId?: number | null): string {
  if (!reportId) return '-'
  return row.reports?.find((r) => r.id === reportId)?.title ?? '-'
}

// loadStats / renderMonthChart 已下沉至 composables/usePlanStats.ts（审计 E-2）

// 筛选变化：列表回到首页并同步刷新统计
async function reload() {
  await Promise.all([load(1), loadStats(), loadConclusion()])
}

// ---------- 导入导出（审计 E-2：已下沉至 composables/usePlanImportExport.ts） ----------
const {
  importing, importInputRef,
  exportExcel, downloadTemplate, doImport, onImportExport, onImportFileChange,
} = usePlanImportExport({
  getFilterParams: filterParams,
  onImported: reloadAfterImport,
})

// 函数声明提升：导入完成后回到首页并刷新列表与统计
function reloadAfterImport() {
  return Promise.all([load(1), loadStats()])
}

function openCreateDialog() {
  createVisible.value = true
}

async function onCreated() {
  createVisible.value = false
  await Promise.all([load(), loadStats()])
}

async function removePlan(id: number) {
  await client.delete(`/testing-plans/${id}`)
  ElMessage.success('删除成功')
  await Promise.all([load(), loadStats()])
}

// ---------- 工单抽屉：工单信息 / 测试流程 两个标签共用（状态进 URL） ----------
// 抽屉打开的工单、当前标签与回退定位的漏洞持久化为 ?plan=&tab=&vuln=：
// 从漏洞编辑页 redirect 回来时按参数自动重开抽屉、切到流程标签、展开刚编辑的漏洞行。
const workflowVisible = ref(false)
const workflowPlanId = ref<number | null>(null)
const workflowTab = ref<PlanDrawerTab>('flow')
const focusVulnId = computed(() => {
  const n = Number(route.query.vuln)
  return Number.isInteger(n) && n > 0 ? n : null
})

function openPlanDrawer(row: TestingPlan, tab: PlanDrawerTab) {
  workflowPlanId.value = row.id
  workflowTab.value = tab
  workflowVisible.value = true
}

// 行内「流程」入口：保持既有命名，等价于打开抽屉并落到流程标签
function openWorkflow(row: TestingPlan) {
  openPlanDrawer(row, 'flow')
}

// 缺省 tab=flow（兼容站内信 ?plan=<id> 直达流程）；带 ?vuln= 时强制流程标签
function routeTab(value: unknown): PlanDrawerTab {
  if (focusVulnId.value) return 'flow'
  return value === 'info' ? 'info' : 'flow'
}

// 抽屉显隐 ↔ URL 查询参数双向同步：打开写入 plan + tab，关闭清除 plan/tab/vuln；
// replace 避免污染历史栈（浏览器后退直接回到无抽屉的列表）。
watch(workflowVisible, (v) => {
  const query = { ...route.query }
  if (v && workflowPlanId.value) {
    query.plan = String(workflowPlanId.value)
    query.tab = workflowTab.value
  } else {
    delete query.plan
    delete query.tab
    delete query.vuln
  }
  void router.replace({ query }).catch(() => {})
})

// 标签切换同样写 URL，保证刷新/分享后落在同一标签
watch(workflowTab, (tab) => {
  if (!workflowVisible.value || !workflowPlanId.value) return
  const query = { ...route.query, plan: String(workflowPlanId.value), tab }
  void router.replace({ query }).catch(() => {})
})

// 首次进入（含编辑页 redirect 回跳）：按 URL 参数恢复抽屉
onMounted(() => {
  const planQ = Number(route.query.plan)
  if (Number.isInteger(planQ) && planQ > 0) {
    workflowPlanId.value = planQ
    workflowTab.value = routeTab(route.query.tab)
    workflowVisible.value = true
  }
})

// 路由参数变化（个人待办 / 站内信深链 ?plan=<id>）：组件复用、onMounted 不再触发时也要打开抽屉，
// 保证「点工单条目 → 直达该工单的流程抽屉」而不是停留在列表页。
watch(() => [route.query.plan, route.query.tab, route.query.vuln] as const, ([q, tab]) => {
  const id = Number(q)
  if (!Number.isInteger(id) || id <= 0) return
  const nextTab = routeTab(tab)
  if (workflowVisible.value && workflowPlanId.value === id && workflowTab.value === nextTab) return
  workflowPlanId.value = id
  workflowTab.value = nextTab
  workflowVisible.value = true
})

// 抽屉内发生认领/漏洞/报告/复测等变更后刷新列表与统计
async function onWorkflowChanged() {
  await Promise.all([load(), loadStats()])
}

function onResize() {
  resizeChart()
}

onMounted(async () => {
  const meta = await auth.fetchMeta()
  statusMap.value = meta?.testing_plan_status ?? {}
  window.addEventListener('resize', onResize)
  await Promise.all([
    load(1), loadStats(), loadConclusion(), loadFilterOptions(),
  ])
})

onBeforeUnmount(() => {
  disposeFilters()
  window.removeEventListener('resize', onResize)
  disposeChart()
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
/* 表头统一单行：文案+排序箭头不换行，保持各列表头整洁对齐 */
:deep(.el-table th .cell) {
  white-space: nowrap;
}
/* 筛选按钮上的条件数徽标 */
/* 快捷预设：直接写入下方条件树 */
.filter-presets {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.filter-presets__label {
  font-size: 12px;
  color: var(--tl-text-3);
  margin-right: 2px;
}

/* ---------- 创建漏扫基线工单（联动） ---------- */
/* 单行布局：圆圈、标题、说明文字垂直居中共用一条水平轴线；wrap 兜底窄屏换行 */
.tp-create-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
  border: 1px dashed var(--tl-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.tp-create-head:hover { border-color: var(--el-color-primary); }
.tp-create-head.on {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.tp-create-check {
  width: 20px;
  height: 20px;
  flex: none;
  border-radius: 50%;
  border: 1px solid var(--tl-border);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}
.tp-create-head.on .tp-create-check {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  color: #fff;
}
.tp-create-title { font-size: 13px; font-weight: 500; }
.tp-create-desc { font-size: 12px; color: var(--tl-text-3); }

/* 结论输出：结论文字卡片 */
.conclusion-box {
  padding: 12px 14px;
  border: 1px solid var(--tl-border);
  border-radius: 8px;
  background: var(--tl-surface);
}
.conclusion-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--tl-text-1);
}

/* 统计卡 / 勾选卡 / 折叠标题样式已上提 style.css 全局共用 */</style>

