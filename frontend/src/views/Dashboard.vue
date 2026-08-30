<template>
  <div class="space-y-3">
    <!-- 筛选工具栏 -->
    <FilterToolbar>
      <span class="text-xs text-gray-400">按时间筛选：</span>
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" class="!w-60"
                      start-placeholder="提交起" end-placeholder="提交止" @change="reload" />
      <el-select v-model="deptFilter" filterable clearable placeholder="全部部门" class="!w-40" @change="reload">
        <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
      </el-select>
      <el-select v-model="sourceFilter" clearable placeholder="全部来源" class="!w-40" @change="reload">
        <el-option v-for="(name, code) in sourceMap" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-select v-model="levelFilter" clearable placeholder="全部等级" class="!w-40" @change="reload">
        <el-option v-for="(name, code) in levelMap" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-button v-if="hasFilter" link type="primary" @click="resetFilters">重置</el-button>
    </FilterToolbar>

    <div v-loading="loading" class="space-y-3">
      <!-- 统计卡（StatCard v2 + SVG 迷你趋势线） -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard v-for="card in cards" :key="card.label" :label="card.label" :value="card.value">
          <template #spark><SparkLine :points="card.spark" :color="card.sparkColor" /></template>
        </StatCard>
      </div>

      <!-- 趋势（2fr） + 等级分布（1fr） -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <el-card shadow="never" class="lg:col-span-2">
          <template #header>近 12 个月漏洞趋势</template>
          <div ref="trendRef" class="h-64" />
        </el-card>
        <el-card shadow="never">
          <template #header>漏洞等级分布</template>
          <div ref="levelRef" class="h-64" />
        </el-card>
      </div>

      <!-- 类型 Top10（2fr，CSS 横条） + 状态分布（1fr，堆叠条 + 图例） -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <el-card shadow="never" class="lg:col-span-2">
          <template #header>漏洞类型 Top10</template>
          <div v-if="byType.length" class="py-1">
            <div v-for="t in byType" :key="t.name" class="hb-row">
              <span class="hb-label" :title="t.name">{{ t.name }}</span>
              <span class="hb-track">
                <span class="hb-bar" :style="{ width: typePct(t.count), background: vulTypeColor(t.type) }"></span>
              </span>
              <span class="hb-val num">{{ t.count }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无类型数据" :image-size="60" />
        </el-card>
        <el-card shadow="never">
          <template #header>漏洞状态分布</template>
          <template v-if="byStatus.length">
            <div class="stack-bar">
              <i v-for="s in byStatus" :key="s.name"
                 :style="{ width: statusPct(s.count), background: statusColorByName(s.name) }"
                 :title="`${s.name} ${s.count}`"></i>
            </div>
            <div class="grid grid-cols-2 gap-x-4 gap-y-2">
              <div v-for="s in byStatus" :key="s.name" class="flex items-center gap-2 text-xs text-gray-500">
                <i class="w-2 h-2 rounded-[3px] flex-none" :style="{ background: statusColorByName(s.name) }"></i>
                <span class="truncate">{{ s.name }}</span>
                <b class="ml-auto num">{{ s.count }}</b>
              </div>
            </div>
          </template>
          <el-empty v-else description="暂无状态数据" :image-size="60" />
        </el-card>
      </div>

      <!-- 部门安全概况 -->
      <el-card shadow="never">
        <template #header>各部门安全概况（按渗透测试工单所属部门统计）</template>
        <template v-if="deptData.length">
          <div ref="deptRef" class="h-72" />
          <el-table :data="deptData" stripe size="small" class="mt-3">
            <el-table-column prop="department" label="部门" min-width="150" show-overflow-tooltip />
            <el-table-column prop="plans" label="提测次数" width="100" />
            <el-table-column prop="vulns" label="发现漏洞" width="100" />
            <el-table-column prop="high" label="高危及以上" width="110">
              <template #default="{ row }"><span class="num">{{ row.high ?? 0 }}</span></template>
            </el-table-column>
            <el-table-column prop="fixed" label="已修复" width="90" />
            <el-table-column label="未闭环" width="90">
              <template #default="{ row }">
                <span class="num" :style="row.open > 0 ? { color: 'var(--tl-danger)' } : {}">{{ row.open ?? 0 }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="mandays" label="占用人天" width="100">
              <template #default="{ row }"><span class="num">{{ row.mandays ?? 0 }}</span></template>
            </el-table-column>
            <el-table-column label="修复率" width="90">
              <template #default="{ row }">
                <span class="num">{{ row.fix_rate === null ? '-' : `${row.fix_rate}%` }}</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
        <el-empty v-else description="暂无部门提测数据" :image-size="80" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import * as echarts from 'echarts'
import client from '../api/client'
import FilterToolbar from '../components/FilterToolbar.vue'
import SparkLine from '../components/SparkLine.vue'
import StatCard from '../components/StatCard.vue'
import { areaGradient, chartThemeName, PALETTE } from '../utils/chartTheme'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { levelColorByName, statusColorByName, vulTypeColor } from '../utils/colors'

// 图表系列色（唯一色源 chartTheme.PALETTE，语义化命名便于系列引用）
const [SERIES_MINT, SERIES_SKY, SERIES_AMBER, , , , SERIES_PINK] = PALETTE

const auth = useAuthStore()
const theme = useThemeStore()
const trendRef = ref<HTMLElement>()
const levelRef = ref<HTMLElement>()
const deptRef = ref<HTMLElement>()
const deptData = ref<any[]>([])
const charts = shallowRef<echarts.ECharts[]>([])
const loading = ref(false)
const lastData = ref<any>(null)

const byType = computed(() => lastData.value?.by_type ?? [])
const byStatus = computed(() => lastData.value?.by_status ?? [])
const typeMax = computed(() => Math.max(1, ...byType.value.map((t: any) => t.count)))
const statusTotal = computed(() => byStatus.value.reduce((s: number, x: any) => s + x.count, 0))
const typePct = (n: number) => `${((n / typeMax.value) * 100).toFixed(1)}%`
const statusPct = (n: number) => `${((n / (statusTotal.value || 1)) * 100).toFixed(2)}%`

// 按事件多维筛选：时间范围 / 部门 / 来源 / 等级
const dateRange = ref<[string, string] | null>(null)
const deptFilter = ref('')
const sourceFilter = ref<number | null>(null)
const levelFilter = ref<number | null>(null)
const departments = ref<string[]>([])
const sourceMap = ref<Record<number, string>>({})
const levelMap = ref<Record<number, string>>({})
const hasFilter = computed(() =>
  !!dateRange.value || !!deptFilter.value || sourceFilter.value !== null || levelFilter.value !== null)

const cards = ref([
  { label: '漏洞总数', value: 0 as number | string, sparkColor: '#10b981', spark: [] as number[] },
  { label: '未闭环漏洞', value: 0 as number | string, sparkColor: '#fb923c', spark: [] as number[] },
  { label: '修复率', value: '0%' as number | string, sparkColor: '#34d399', spark: [] as number[] },
  { label: '在管资产', value: 0 as number | string, sparkColor: '#38bdf8', spark: [] as number[] },
])

function mk(el: HTMLElement | undefined, option: echarts.EChartsOption) {
  if (!el) return
  const chart = echarts.init(el, chartThemeName(theme.dark))
  chart.setOption(option)
  charts.value.push(chart)
}

function disposeCharts() {
  charts.value.forEach((c) => c.dispose())
  charts.value = []
}

function filterParams(): Record<string, any> {
  const params: Record<string, any> = {}
  if (dateRange.value?.length === 2) {
    params.date_from = dateRange.value[0]
    params.date_to = dateRange.value[1]
  }
  if (deptFilter.value) params.department = deptFilter.value
  if (sourceFilter.value !== null && sourceFilter.value !== ('' as any)) params.source = sourceFilter.value
  if (levelFilter.value !== null && levelFilter.value !== ('' as any)) params.level = levelFilter.value
  return params
}

function resetFilters() {
  dateRange.value = null
  deptFilter.value = ''
  sourceFilter.value = null
  levelFilter.value = null
  reload()
}

async function reload() {
  loading.value = true
  try {
    const { data } = await client.get('/dashboard/stats', { params: filterParams() })
    lastData.value = data
    cards.value[0].value = data.total_vulns
    cards.value[1].value = data.open_vulns
    cards.value[2].value = `${data.fix_rate}%`
    cards.value[3].value = data.total_assets
    // 迷你趋势线复用 12 个月趋势数据（在管资产暂无独立趋势，沿用提交轮廓）
    const submitted = data.trend.map((t: any) => t.submitted)
    const fixed = data.trend.map((t: any) => t.fixed)
    cards.value[0].spark = submitted
    cards.value[1].spark = data.trend.map((t: any) => Math.max(0, t.submitted - t.fixed))
    cards.value[2].spark = fixed
    cards.value[3].spark = submitted
    deptData.value = data.by_department ?? []
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}

// 图表渲染与数据获取分离，便于主题切换时按新主题重建
function renderCharts() {
  if (!lastData.value) return
  const data = lastData.value
  disposeCharts()

  // 渐变面积趋势图
  const submitted = data.trend.map((t: any) => t.submitted)
  const fixed = data.trend.map((t: any) => t.fixed)
  mk(trendRef.value, {
    tooltip: { trigger: 'axis' },
    legend: { data: ['提交', '修复完成'], top: 0 },
    grid: { left: 40, right: 16, top: 40, bottom: 30 },
    xAxis: { type: 'category', boundaryGap: false, data: data.trend.map((t: any) => t.month) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '提交', type: 'line', smooth: true, symbol: 'none', data: submitted,
        lineStyle: { width: 2.5, color: SERIES_MINT }, itemStyle: { color: SERIES_MINT }, areaStyle: { color: areaGradient(SERIES_MINT) } },
      { name: '修复完成', type: 'line', smooth: true, symbol: 'none', data: fixed,
        lineStyle: { width: 2.5, color: SERIES_SKY }, itemStyle: { color: SERIES_SKY }, areaStyle: { color: areaGradient(SERIES_SKY) } },
    ],
  })

  // 等级分布：圆角环形 + 中心 KPI 总数 + 右侧图例
  const levelTotal = data.by_level.reduce((s: number, x: any) => s + x.count, 0)
  mk(levelRef.value, {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', right: 4, top: 'middle', formatter: (name: string) => {
      const x = data.by_level.find((l: any) => l.name === name)
      return `${name}  ${x ? x.count : ''}`
    } },
    title: {
      text: String(levelTotal), subtext: '漏洞总数', left: '34%', top: '40%',
      textAlign: 'center',
      textStyle: { fontSize: 22, fontWeight: 700, color: theme.dark ? '#e8efec' : '#1c2622' },
      subtextStyle: { fontSize: 11.5, color: theme.dark ? '#5f716b' : '#8a968f' },
    },
    series: [{
      type: 'pie', radius: ['52%', '74%'], center: ['36%', '50%'],
      itemStyle: { borderRadius: 8, borderColor: theme.dark ? '#101513' : '#ffffff', borderWidth: 3 },
      label: { show: false },
      data: data.by_level.map((x: any) => ({
        name: x.name, value: x.count, itemStyle: { color: levelColorByName(x.name) },
      })),
    }],
  })

  // 部门安全概况：圆角柱状（提测/漏洞/已修复）+ 折线（修复率，右轴）
  if (deptData.value.length) {
    mk(deptRef.value, {
      tooltip: { trigger: 'axis' },
      legend: { data: ['提测次数', '发现漏洞', '已修复', '修复率(%)'], top: 0 },
      grid: { left: 48, right: 48, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: deptData.value.map((d: any) => d.department) },
      yAxis: [
        { type: 'value', minInterval: 1 },
        { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { show: false } },
      ],
      series: [
        { name: '提测次数', type: 'bar', barMaxWidth: 20, itemStyle: { borderRadius: [4, 4, 0, 0], color: SERIES_MINT }, data: deptData.value.map((d: any) => d.plans) },
        { name: '发现漏洞', type: 'bar', barMaxWidth: 20, itemStyle: { borderRadius: [4, 4, 0, 0], color: SERIES_AMBER }, data: deptData.value.map((d: any) => d.vulns) },
        { name: '已修复', type: 'bar', barMaxWidth: 20, itemStyle: { borderRadius: [4, 4, 0, 0], color: SERIES_SKY }, data: deptData.value.map((d: any) => d.fixed) },
        { name: '修复率(%)', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 7,
          lineStyle: { width: 2.5, color: SERIES_PINK }, itemStyle: { color: SERIES_PINK }, data: deptData.value.map((d: any) => d.fix_rate) },
      ],
    })
  }
}

// 主题切换：按新主题重建图表
watch(() => theme.dark, async () => {
  await nextTick()
  renderCharts()
})

onMounted(async () => {
  const meta = await auth.fetchMeta()
  sourceMap.value = meta?.vul_source ?? {}
  levelMap.value = meta?.vul_level ?? {}
  client.get('/groups').then(({ data }) => {
    departments.value = data.map((g: any) => g.name)
  }).catch(() => { /* 无权限时部门筛选项置空 */ })
  await reload()
  window.addEventListener('resize', onResize)
})

function onResize() {
  charts.value.forEach((c) => c.resize())
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  disposeCharts()
})
</script>

<style scoped>
/* 类型 Top10 横条（demo-2 hb-row 范式，CSS 替代 ECharts 横柱） */
.hb-row {
  display: grid;
  grid-template-columns: 100px 1fr 44px;
  align-items: center;
  gap: 12px;
  padding: 5px 0;
}
.hb-label {
  font-size: 12.5px;
  color: var(--tl-text-2);
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hb-track { height: 12px; border-radius: 6px; background: var(--tl-surface-2); overflow: hidden; }
.hb-bar { display: block; height: 100%; border-radius: 6px; transition: width .6s cubic-bezier(.22, 1, .36, 1); }
.hb-val { font-size: 12px; font-weight: 600; color: var(--tl-text-1); text-align: right; }

/* 状态分布堆叠条 + 图例 */
.stack-bar {
  display: flex;
  height: 12px;
  border-radius: 6px;
  overflow: hidden;
  gap: 2px;
  margin: 6px 0 14px;
}
.stack-bar i { display: block; height: 100%; min-width: 3px; }
</style>
