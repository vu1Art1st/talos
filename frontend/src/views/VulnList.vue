<template>
  <div class="space-y-4">
    <!-- 筛选工具栏 -->
    <el-card shadow="never" class="!rounded-lg">
      <div class="flex flex-wrap items-center gap-2">
        <el-input v-model="query.search" placeholder="搜索标题 / URL" clearable class="!w-64"
                  @keyup.enter="reload" @clear="reload">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="query.statuses" placeholder="状态" clearable multiple collapse-tags
                   class="!w-44" @change="reload">
          <el-option v-for="(name, code) in meta?.vul_status" :key="code" :label="name" :value="Number(code)" />
        </el-select>
        <el-select v-model="query.levels" placeholder="等级" clearable multiple collapse-tags
                   class="!w-44" @change="reload">
          <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
        </el-select>
        <el-select v-model="query.vul_types" placeholder="类型" clearable filterable multiple collapse-tags
                   class="!w-52" @change="reload">
          <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
        </el-select>
        <el-select v-model="query.system_types" placeholder="系统类型" clearable filterable multiple collapse-tags
                   class="!w-52" @change="reload">
          <el-option v-for="st in (meta?.system_type ?? [])" :key="st" :label="st" :value="st" />
        </el-select>
        <el-select v-model="query.test_types" placeholder="测试类型" clearable filterable multiple collapse-tags
                   class="!w-52" @change="reload">
          <el-option v-for="t in testTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="query.asset_ids" placeholder="选择资产" clearable filterable remote multiple collapse-tags
                   :remote-method="searchAssets" :loading="assetLoading" class="!w-56" @change="reload">
          <el-option v-for="a in assetOptions" :key="a.id" :label="a.label" :value="a.id" />
        </el-select>
        <el-select v-model="query.departments" placeholder="归属部门" clearable filterable multiple collapse-tags
                   class="!w-48" @change="reload">
          <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
        </el-select>
        <el-date-picker v-model="query.dateRange" type="daterange" unlink-panels
                        range-separator="至" start-placeholder="录入开始" end-placeholder="录入结束"
                        value-format="YYYY-MM-DD" class="!w-64" @change="reload" />
        <el-checkbox v-model="query.mine" @change="reload">只看我提交的</el-checkbox>
        <div class="flex-1" />
        <el-button v-if="auth.hasPerm('vuln:manage') && selected.length" type="danger" class="btn-min" @click="batchRemove">
          <el-icon class="mr-1"><Delete /></el-icon>删除选中 ({{ selected.length }})
        </el-button>
        <el-button v-if="auth.hasPerm('vuln:submit')" type="primary" class="btn-min" @click="router.push('/vulns/new')">
          <el-icon class="mr-1"><Plus /></el-icon>提交漏洞
        </el-button>
      </div>
    </el-card>

    <!-- 统计概览（可折叠，与筛选联动） -->
    <el-collapse v-model="statsOpen" class="!border-0">
      <el-collapse-item name="stats">
        <template #title>
          <span class="tl-collapse-title">
            <span class="tl-collapse-title__main">统计概览</span>
            <span class="tl-collapse-title__sub">（与筛选条件联动实时更新）</span>
          </span>
        </template>
        <div v-loading="statsLoading">
          <!-- 数据卡片：总数 / 4 等级 / 已修复 / 修复率 -->
          <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-4 mb-4 max-w-7xl mx-auto">
            <div class="rounded-xl px-5 py-4 text-white border border-transparent"
                 style="background: linear-gradient(135deg,#6366f1,#8b5cf6)">
              <div class="text-xs opacity-80">漏洞总数</div>
              <div class="text-2xl font-bold tabular-nums">{{ stats?.total ?? 0 }}</div>
            </div>
            <div v-for="lv in levelCards" :key="lv.code" class="rounded-xl px-5 py-4 border"
                 :style="{ background: lv.color + '0f', borderColor: lv.color + '33' }">
              <div class="text-xs" :style="{ color: lv.color }">{{ lv.label }}</div>
              <div class="text-2xl font-bold tabular-nums" :style="{ color: lv.color }">{{ levelCount(lv.code) }}</div>
            </div>
            <div class="rounded-xl px-5 py-4 border"
                 style="background: #67c23a0f; border-color: #67c23a33">
              <div class="text-xs" style="color: #67C23A">已修复</div>
              <div class="text-2xl font-bold tabular-nums" style="color: #67C23A">{{ fixedCount }}</div>
            </div>
            <div class="rounded-xl px-5 py-4 border"
                 style="background: #409eff0f; border-color: #409eff33">
              <div class="text-xs" style="color: #409EFF">修复率</div>
              <div class="text-2xl font-bold tabular-nums" style="color: #409EFF">{{ fixRate }}%</div>
            </div>
          </div>

          <!-- Excel 风格交叉透视表：行=部门→系统，列=等级×修复状态 -->
          <el-card shadow="never" class="!rounded-lg">
            <template #header>
              <div class="flex flex-wrap items-center gap-2 w-full">
                <span class="font-medium">漏洞统计透视表</span>
                <span class="text-xs" style="color: var(--tl-text-3)">
                  （与上方筛选条件联动；按部门→系统分行，按等级×修复状态分列）
                </span>
                <div class="flex flex-wrap items-center gap-1 ml-auto">
                  <el-tag v-if="query.test_types.length" size="small" type="primary" effect="plain">
                    测试类型：{{ query.test_types.join('、') }}
                  </el-tag>
                  <el-tag v-if="query.departments.length" size="small" effect="plain">
                    部门：{{ query.departments.join('、') }}
                  </el-tag>
                  <el-tag v-if="query.levels.length" size="small" effect="plain">
                    等级：{{ query.levels.map(String).join('、') }}
                  </el-tag>
                  <el-tag v-if="query.dateRange && query.dateRange.length === 2" size="small" effect="plain">
                    录入：{{ query.dateRange[0] }} ~ {{ query.dateRange[1] }}
                  </el-tag>
                </div>
              </div>
            </template>
            <div class="max-w-[1300px] mx-auto">
            <el-table :data="pivotTableData" stripe border :max-height="520" :fit="false"
                      :span-method="pivotSpanMethod" show-summary
                      :summary-method="pivotSummaryMethod"
                      class="pivot-table">
              <!-- 行头：部门 / 系统 / 系统类型 -->
              <el-table-column prop="department" label="部门" width="110" fixed />
              <el-table-column prop="asset_name" label="系统" width="130" show-overflow-tooltip />
              <el-table-column prop="system_type" label="系统类型" width="120" show-overflow-tooltip />
              <!-- 合计列 -->
              <el-table-column label="漏洞总数" width="80" align="center">
                <template #default="{ row }"><span class="tabular-nums font-medium">{{ row.total }}</span></template>
              </el-table-column>
              <el-table-column label="已修复总数" width="90" align="center">
                <template #default="{ row }"><span class="tabular-nums" style="color:#67C23A">{{ row.fixed_total }}</span></template>
              </el-table-column>
              <el-table-column label="总修复率" width="80" align="center">
                <template #default="{ row }"><span class="tabular-nums">{{ row.fix_rate }}%</span></template>
              </el-table-column>
              <!-- 等级 × 修复状态 子列组 -->
              <el-table-column v-for="lv in levelPivotCols" :key="lv.code" :label="lv.label">
                <el-table-column :label="'数量'" width="56" align="center">
                  <template #default="{ row }">
                    <span class="tabular-nums" :style="{ color: lv.color, fontWeight: row.levels[lv.code]?.count ? 600 : 400 }">
                      {{ row.levels[lv.code]?.count ?? 0 }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="已修复" width="58" align="center">
                  <template #default="{ row }"><span class="tabular-nums" style="color:#67C23A">{{ row.levels[lv.code]?.fixed ?? 0 }}</span></template>
                </el-table-column>
                <el-table-column label="未修复" width="58" align="center">
                  <template #default="{ row }"><span class="tabular-nums" style="color:#F56C6C">{{ row.levels[lv.code]?.unfixed ?? 0 }}</span></template>
                </el-table-column>
              </el-table-column>
              <template #empty>
                <el-empty description="暂无统计数据" :image-size="60" />
              </template>
            </el-table>
            </div>
          </el-card>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 漏洞列表 -->
    <el-card shadow="never" class="!rounded-lg">
      <el-table v-loading="loading" :data="items" stripe @row-click="(row: any) => router.push(`/vulns/${row.id}`)"
                class="cursor-pointer" @selection-change="(rows: any[]) => (selected = rows)"
                @sort-change="onSortChange">
        <el-table-column v-if="auth.hasPerm('vuln:manage')" type="selection" width="42" />
        <el-table-column type="index" label="序号" width="70" :index="(i: number) => (query.page - 1) * query.size + i + 1" />
        <el-table-column prop="title" label="漏洞名称" min-width="240" show-overflow-tooltip sortable="custom" />
        <el-table-column prop="level" label="等级" width="90" sortable="custom">
          <template #default="{ row }">
            <span class="tl-tag" :style="levelSoftStyle(row.level)">
              {{ meta?.vul_level?.[row.level] ?? row.level }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="vul_type" label="类型" width="150" sortable="custom">
          <template #default="{ row }">{{ meta?.vul_type?.[row.vul_type] ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" sortable="custom">
          <template #default="{ row }">
            <span class="tl-tag" :style="statusSoftStyleEx(row.status, row.is_retest)">
              {{ statusLabel(row.status, row.is_retest, meta?.vul_status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="关联资产" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            {{ (row.assets ?? []).map((a: any) => a.name).join('、') || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="归属部门" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.department || '-' }}</template>
        </el-table-column>
        <el-table-column prop="submit_time" label="提交时间" width="170" sortable="custom">
          <template #default="{ row }">{{ fmtDateTime(row.submit_time) }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无漏洞记录，点击「提交漏洞」开始录入" :image-size="80" />
        </template>
      </el-table>

      <div class="flex justify-end mt-4">
        <el-pagination background layout="total, prev, pager, next" :total="total"
                       :page-size="query.size" :current-page="query.page"
                       @current-change="load" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle, statusLabel, statusSoftStyleEx, levelColor } from '../utils/colors'
import { fmtDateTime } from '../utils/format'

const auth = useAuthStore()
const router = useRouter()
const meta = ref<any>(null)
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const selected = ref<any[]>([])
const query = reactive({
  search: '', statuses: [], levels: [], vul_types: [], system_types: [], test_types: [],
  asset_ids: [], departments: [], dateRange: [],
  mine: false, page: 1, size: 20, sort: '', order: '',
})

// ---------- 筛选数据源：测试类型 / 部门 / 资产远程搜索 ----------
const testTypes = ref<string[]>([])
const departments = ref<string[]>([])
const assetOptions = ref<{ id: number; label: string }[]>([])
const assetCache = ref<Record<number, any>>({})
const assetLoading = ref(false)

async function loadTestTypes() {
  const { data } = await client.get('/dict/test_type')
  testTypes.value = data.map((o: any) => o.name)
}

async function loadDepartments() {
  const { data } = await client.get('/groups')
  departments.value = data.map((g: any) => g.name)
}

// 下拉展示：系统名称 +（子系统）+（系统类型），区分同名系统的不同环境
function assetLabel(a: any) {
  const parts = [a.name]
  if (a.sub_system) parts.push(`（${a.sub_system}）`)
  if (a.system_type) parts.push(`（${a.system_type}）`)
  return parts.join('')
}

// 资产下拉：远程搜索。已选中的资产始终合并进选项，保证多选标签可正确回显
async function searchAssets(keyword = '') {
  assetLoading.value = true
  try {
    const { data } = await client.get('/assets', { params: { search: keyword, page: 1, size: 50 } })
    const opts = data.items.map((a: any) => {
      assetCache.value[a.id] = a
      return { id: a.id, label: assetLabel(a) }
    })
    // 已选资产若不在搜索结果中，追加其标签，避免多选回显为纯数字
    for (const id of query.asset_ids) {
      if (!opts.some((o: any) => o.id === id)) {
        const cached = assetCache.value[id]
        if (cached) opts.push({ id, label: assetLabel(cached) })
      }
    }
    assetOptions.value = opts
  } finally {
    assetLoading.value = false
  }
}

// ---------- 统计概览（顶部 7 张数据卡片） ----------
const statsOpen = ref<string[]>(localStorage.getItem('vuln_stats_open') === '1' ? ['stats'] : [])
watch(statsOpen, (v) => localStorage.setItem('vuln_stats_open', v.length ? '1' : '0'))

const stats = ref<any>(null)
const statsLoading = ref(false)
const levelCards = [
  { code: 10, label: '严重', color: levelColor(10) },
  { code: 20, label: '高危', color: levelColor(20) },
  { code: 30, label: '中危', color: levelColor(30) },
  { code: 40, label: '低危', color: levelColor(40) },
]
const levelCount = (code: number) => stats.value?.by_level?.find((x: any) => x.level === code)?.count ?? 0
const fixedCount = computed(() => stats.value?.by_fix_status?.find((x: any) => x.key === 'fixed')?.count ?? 0)
const fixRate = computed(() => {
  const t = stats.value?.total ?? 0
  return t ? Math.round((fixedCount.value / t) * 1000) / 10 : 0
})

// 多选字段统一走逗号分隔字符串下发（与后端 _parse_*_list 对齐）
function filterParams(): Record<string, any> {
  const p: Record<string, any> = {
    search: query.search || undefined,
    mine: query.mine,
  }
  if (query.statuses.length) p.statuses = query.statuses.join(',')
  if (query.levels.length) p.levels = query.levels.join(',')
  if (query.vul_types.length) p.vul_types = query.vul_types.join(',')
  if (query.system_types.length) p.system_types = query.system_types.join(',')
  if (query.test_types.length) p.test_types = query.test_types.join(',')
  if (query.departments.length) p.departments = query.departments.join(',')
  if (query.asset_ids.length) p.asset_ids = query.asset_ids.join(',')
  if (query.dateRange && query.dateRange.length === 2) {
    p.submit_time_from = query.dateRange[0]
    p.submit_time_to = query.dateRange[1]
  }
  return p
}

async function loadStats() {
  statsLoading.value = true
  try {
    const { data } = await client.get('/vulns/stats', { params: filterParams() })
    stats.value = data
  } finally {
    statsLoading.value = false
  }
}

// ---------- Excel 风格交叉透视表 ----------
const levelPivotCols = [
  { code: 10, label: '严重漏洞', color: levelColor(10) },
  { code: 20, label: '高危漏洞', color: levelColor(20) },
  { code: 30, label: '中危漏洞', color: levelColor(30) },
  { code: 40, label: '低危漏洞', color: levelColor(40) },
]

const pivotTableData = computed(() => stats.value?.pivot?.rows ?? [])

// 「部门」列合并：同一部门的连续行合并
const pivotDeptSpans = computed(() => {
  const spans: Record<number, number> = {}
  const rows = pivotTableData.value
  let i = 0
  while (i < rows.length) {
    let j = i + 1
    while (j < rows.length && rows[j].department === rows[i].department) j++
    spans[i] = j - i
    i = j
  }
  return spans
})

function pivotSpanMethod({ row, rowIndex, columnIndex }: { row: any; rowIndex: number; columnIndex: number }) {
  // 仅对第0列（部门）做合并
  if (columnIndex !== 0) return
  // 合计行（row 为 undefined 或超出数据行）不参与合并，避免隐藏「合计」文本
  if (!row || rowIndex >= pivotTableData.value.length) return
  const rowspan = pivotDeptSpans.value[rowIndex]
  return rowspan ? { rowspan, colspan: 1 } : { rowspan: 0, colspan: 0 }
}

// 合计行自定义方法（show-summary 触发）
function pivotSummaryMethod({ columns, data }: { columns: any[]; data: any[] }) {
  const t = stats.value?.pivot?.totals
  if (!t) return []
  const sums: (string | number)[] = ['合计', '', '', t.total, t.fixed_total, `${t.fix_rate}%`]
  for (const lv of levelPivotCols) {
    const L = t.levels[lv.code]
    sums.push(L.count, L.fixed, L.unfixed)
  }
  // 补齐列数（el-table 可能传入比定义多的内部列）
  while (sums.length < columns.length) sums.push('')
  return sums
}

// ---------- 列表加载 ----------
function onSortChange({ prop, order }: any) {
  query.sort = order ? prop : ''
  query.order = order === 'ascending' ? 'asc' : order === 'descending' ? 'desc' : ''
  load(1)
}

async function load(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const { data } = await client.get('/vulns', {
      params: {
        ...filterParams(),
        page: query.page,
        size: query.size,
        sort: query.sort,
        order: query.order,
      },
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function reload() {
  await Promise.all([load(1), loadStats()])
}

async function batchRemove() {
  const ids = selected.value.map((v) => v.id)
  await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 个漏洞？删除后不可恢复`, '批量删除', {
    type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger',
  })
  await client.post('/vulns/batch-delete', { ids })
  ElMessage.success(`已删除 ${ids.length} 个漏洞`)
  // 当前页被删空时回退一页
  const remainPages = Math.max(1, Math.ceil((total.value - ids.length) / query.size))
  await reload()
  await load(Math.min(query.page, remainPages))
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await Promise.all([reload(), loadTestTypes(), loadDepartments(), searchAssets()])
})
</script>

<style scoped>
/* 统计概览标题：居中 + 两侧渐变装饰线；保留 el-collapse 折叠/展开能力，仅做视觉增强 */
.tl-collapse-title {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  min-width: 0;
}
.tl-collapse-title::before,
.tl-collapse-title::after {
  content: '';
  height: 1px;
  flex: none;
  width: 100px;
}
.tl-collapse-title::before { background: linear-gradient(to right, transparent, #c7c9ff); }
.tl-collapse-title::after { background: linear-gradient(to left, transparent, #c7c9ff); }
.tl-collapse-title__main { font-size: 15px; font-weight: 600; color: var(--tl-text-1); white-space: nowrap; }
.tl-collapse-title__sub { font-size: 12px; color: var(--tl-text-3); white-space: nowrap; }
</style>
