<template>
  <div class="space-y-4">
    <el-card shadow="never" class="!rounded-lg">
      <div class="flex items-center flex-wrap gap-2">
        <span class="text-sm" style="color: var(--tl-text-3)">按时间筛选：</span>
        <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" class="!w-60"
                        start-placeholder="提交起" end-placeholder="提交止" @change="reload" />
        <el-select v-model="deptFilter" filterable clearable placeholder="全部部门" class="!w-40" @change="reload">
          <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
        </el-select>
        <el-select v-model="sourceFilter" clearable placeholder="全部来源" class="!w-36" @change="reload">
          <el-option v-for="(name, code) in sourceMap" :key="code" :label="name" :value="Number(code)" />
        </el-select>
        <el-select v-model="levelFilter" clearable placeholder="全部等级" class="!w-36" @change="reload">
          <el-option v-for="(name, code) in levelMap" :key="code" :label="name" :value="Number(code)" />
        </el-select>
        <el-button v-if="hasFilter" link type="primary" @click="resetFilters">重置</el-button>
      </div>
    </el-card>

    <div v-loading="loading" class="space-y-4">
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <el-card v-for="(card, i) in cards" :key="card.label" shadow="never" class="!rounded-lg tl-hover">
        <div class="flex items-start justify-between">
          <div class="min-w-0">
            <div class="text-sm" style="color: var(--tl-text-3)">{{ card.label }}</div>
            <div class="text-2xl font-bold mt-1 tabular-nums" style="color: var(--tl-text-1)">{{ card.value }}</div>
          </div>
          <div class="w-11 h-11 rounded-xl flex items-center justify-center flex-none"
               :style="{ background: card.gradient, boxShadow: '0 6px 16px ' + card.glow }">
            <el-icon :size="22" color="#fff"><component :is="card.icon" /></el-icon>
          </div>
        </div>
        <div :ref="(el) => (sparkRefs[i] = el as HTMLElement)" class="h-9 mt-2 -mb-1" />
      </el-card>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <el-card shadow="never" class="!rounded-lg tl-hover">
        <template #header>近 12 个月漏洞趋势</template>
        <div ref="trendRef" class="h-72" />
      </el-card>
      <el-card shadow="never" class="!rounded-lg tl-hover">
        <template #header>漏洞等级分布</template>
        <div ref="levelRef" class="h-72" />
      </el-card>
      <el-card shadow="never" class="!rounded-lg tl-hover">
        <template #header>漏洞状态分布</template>
        <div ref="statusRef" class="h-72" />
      </el-card>
      <el-card shadow="never" class="!rounded-lg tl-hover">
        <template #header>漏洞类型 Top10</template>
        <div ref="typeRef" class="h-72" />
      </el-card>
    </div>

    <el-card shadow="never" class="!rounded-lg tl-hover">
      <template #header>各部门安全概况（按渗透测试工单所属部门统计）</template>
      <template v-if="deptData.length">
        <div ref="deptRef" class="h-80" />
        <el-table :data="deptData" stripe size="small" class="mt-4">
          <el-table-column prop="department" label="部门" min-width="160" show-overflow-tooltip />
          <el-table-column prop="plans" label="提测次数" width="110" />
          <el-table-column prop="vulns" label="发现漏洞" width="110" />
          <el-table-column prop="fixed" label="已修复" width="110" />
          <el-table-column label="修复率" width="110">
            <template #default="{ row }">
              {{ row.fix_rate === null ? '-' : `${row.fix_rate}%` }}
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
import { DataLine, CircleCheck, Warning, Grid } from '@element-plus/icons-vue'
import client from '../api/client'
import { areaGradient, chartThemeName, PALETTE } from '../utils/chartTheme'

// 图表系列色（唯一色源 chartTheme.PALETTE，语义化命名便于系列引用）
const [SERIES_MAIN, SERIES_GREEN, SERIES_AMBER, , , , SERIES_PINK] = PALETTE
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { LEVEL_COLORS_BY_NAME, STATUS_COLORS_BY_NAME, vulTypeColor } from '../utils/colors'

const auth = useAuthStore()
const theme = useThemeStore()
const trendRef = ref<HTMLElement>()
const levelRef = ref<HTMLElement>()
const statusRef = ref<HTMLElement>()
const typeRef = ref<HTMLElement>()
const deptRef = ref<HTMLElement>()
const sparkRefs = ref<HTMLElement[]>([])
const deptData = ref<any[]>([])
const charts = shallowRef<echarts.ECharts[]>([])
const loading = ref(false)
let lastData: any = null

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
  { label: '漏洞总数', value: 0 as number | string, icon: DataLine,
    gradient: 'linear-gradient(135deg,#6366f1,#8b5cf6)', glow: 'rgba(99,102,241,.35)' },
  { label: '未闭环漏洞', value: 0 as number | string, icon: Warning,
    gradient: 'linear-gradient(135deg,#f43f5e,#f97316)', glow: 'rgba(244,63,94,.35)' },
  { label: '修复率', value: '0%' as number | string, icon: CircleCheck,
    gradient: 'linear-gradient(135deg,#10b981,#22c55e)', glow: 'rgba(16,185,129,.35)' },
  { label: '在管资产', value: 0 as number | string, icon: Grid,
    gradient: 'linear-gradient(135deg,#0ea5e9,#06b6d4)', glow: 'rgba(14,165,233,.35)' },
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
    lastData = data
    cards.value[0].value = data.total_vulns
    cards.value[1].value = data.open_vulns
    cards.value[2].value = `${data.fix_rate}%`
    cards.value[3].value = data.total_assets
    deptData.value = data.by_department ?? []
    await nextTick()
    renderCharts()
  } finally {
    loading.value = false
  }
}

// 图表渲染与数据获取分离，便于主题切换时按新主题重建
function renderCharts() {
  if (!lastData) return
  const data = lastData
  disposeCharts()

  // 统计卡片内嵌 sparkline（复用趋势数据）
  const submitted = data.trend.map((t: any) => t.submitted)
  const fixed = data.trend.map((t: any) => t.fixed)
  const openTrend = data.trend.map((t: any) => Math.max(0, t.submitted - t.fixed))
  const sparks = [submitted, openTrend, fixed, submitted]
  sparkRefs.value.forEach((el, i) => {
    mk(el, {
      grid: { left: 0, right: 0, top: 4, bottom: 0 },
      xAxis: { type: 'category', show: false, data: data.trend.map((t: any) => t.month) },
      yAxis: { type: 'value', show: false, min: 'dataMin' },
      tooltip: { show: false },
      series: [{
        type: 'line', data: sparks[i], smooth: true, symbol: 'none',
        lineStyle: { width: 2, color: SERIES_MAIN }, areaStyle: { color: areaGradient(SERIES_MAIN) },
      }],
    })
  })

  // 渐变面积趋势图
  mk(trendRef.value, {
    tooltip: { trigger: 'axis' },
    legend: { data: ['提交', '修复完成'], top: 0 },
    grid: { left: 40, right: 16, top: 40, bottom: 30 },
    xAxis: { type: 'category', boundaryGap: false, data: data.trend.map((t: any) => t.month) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '提交', type: 'line', smooth: true, symbol: 'none', data: submitted,
        lineStyle: { width: 2.5, color: SERIES_MAIN }, itemStyle: { color: SERIES_MAIN }, areaStyle: { color: areaGradient(SERIES_MAIN) } },
      { name: '修复完成', type: 'line', smooth: true, symbol: 'none', data: fixed,
        lineStyle: { width: 2.5, color: SERIES_GREEN }, itemStyle: { color: SERIES_GREEN }, areaStyle: { color: areaGradient(SERIES_GREEN) } },
    ],
  })

  // 等级分布：圆角环形 + 中心 KPI 总数
  const levelTotal = data.by_level.reduce((s: number, x: any) => s + x.count, 0)
  mk(levelRef.value, {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    title: {
      text: String(levelTotal), subtext: '漏洞总数', left: 'center', top: '36%',
      textStyle: { fontSize: 24, fontWeight: 700, color: theme.dark ? '#e6edf3' : '#111827' },
      subtextStyle: { fontSize: 12, color: theme.dark ? '#6e7681' : '#9ca3af' },
    },
    series: [{
      type: 'pie', radius: ['52%', '72%'], center: ['50%', '45%'],
      itemStyle: { borderRadius: 8, borderColor: theme.dark ? '#161b22' : '#fff', borderWidth: 3 },
      label: { show: false },
      data: data.by_level.map((x: any) => ({
        name: x.name, value: x.count, itemStyle: { color: LEVEL_COLORS_BY_NAME[x.name] },
      })),
    }],
  })

  // 状态分布：圆角环形
  mk(statusRef.value, {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['40%', '68%'], center: ['50%', '45%'],
      itemStyle: { borderRadius: 8, borderColor: theme.dark ? '#161b22' : '#fff', borderWidth: 3 },
      label: { formatter: '{b} {c}' },
      data: data.by_status.map((x: any) => ({
        name: x.name, value: x.count, itemStyle: { color: STATUS_COLORS_BY_NAME[x.name] },
      })),
    }],
  })

  // 类型 Top10：横向柱，每根柱子按漏洞类型差异化着色（同类型恒为同色）
  mk(typeRef.value, {
    tooltip: { trigger: 'axis' },
    grid: { left: 110, right: 32, top: 16, bottom: 30 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: data.by_type.map((x: any) => x.name).reverse() },
    series: [{
      type: 'bar', barMaxWidth: 14,
      data: [...data.by_type].reverse().map((x: any) => ({
        value: x.count,
        itemStyle: { color: vulTypeColor(x.type), borderRadius: [0, 6, 6, 0] },
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
        { name: '提测次数', type: 'bar', barMaxWidth: 20, itemStyle: { borderRadius: [4, 4, 0, 0], color: SERIES_MAIN }, data: deptData.value.map((d: any) => d.plans) },
        { name: '发现漏洞', type: 'bar', barMaxWidth: 20, itemStyle: { borderRadius: [4, 4, 0, 0], color: SERIES_AMBER }, data: deptData.value.map((d: any) => d.vulns) },
        { name: '已修复', type: 'bar', barMaxWidth: 20, itemStyle: { borderRadius: [4, 4, 0, 0], color: SERIES_GREEN }, data: deptData.value.map((d: any) => d.fixed) },
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
