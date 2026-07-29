<template>
  <div class="space-y-4">
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <el-card v-for="card in cards" :key="card.label" shadow="hover" class="!rounded-lg">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-gray-400 text-sm">{{ card.label }}</div>
            <div class="text-2xl font-bold mt-1" :style="{ color: card.color }">{{ card.value }}</div>
          </div>
          <el-icon :size="36" :color="card.color" class="opacity-70">
            <component :is="card.icon" />
          </el-icon>
        </div>
      </el-card>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <el-card shadow="hover" class="!rounded-lg">
        <template #header>近 12 个月漏洞趋势</template>
        <div ref="trendRef" class="h-72" />
      </el-card>
      <el-card shadow="hover" class="!rounded-lg">
        <template #header>漏洞等级分布</template>
        <div ref="levelRef" class="h-72" />
      </el-card>
      <el-card shadow="hover" class="!rounded-lg">
        <template #header>漏洞状态分布</template>
        <div ref="statusRef" class="h-72" />
      </el-card>
      <el-card shadow="hover" class="!rounded-lg">
        <template #header>漏洞类型 Top10</template>
        <div ref="typeRef" class="h-72" />
      </el-card>
    </div>

    <el-card shadow="hover" class="!rounded-lg">
      <template #header>各部门安全概况（按测试计划所属部门统计）</template>
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
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import * as echarts from 'echarts'
import { DataLine, CircleCheck, Warning, Grid } from '@element-plus/icons-vue'
import client from '../api/client'
import { LEVEL_COLORS_BY_NAME, STATUS_COLORS_BY_NAME } from '../utils/colors'

const trendRef = ref<HTMLElement>()
const levelRef = ref<HTMLElement>()
const statusRef = ref<HTMLElement>()
const typeRef = ref<HTMLElement>()
const deptRef = ref<HTMLElement>()
const deptData = ref<any[]>([])
const charts = shallowRef<echarts.ECharts[]>([])
const cards = ref([
  { label: '漏洞总数', value: 0, color: '#409EFF', icon: DataLine },
  { label: '未闭环漏洞', value: 0, color: '#F56C6C', icon: Warning },
  { label: '修复率', value: '0%', color: '#67C23A', icon: CircleCheck },
  { label: '在管资产', value: 0, color: '#909399', icon: Grid },
])

function mk(el: HTMLElement | undefined, option: echarts.EChartsOption) {
  if (!el) return
  const chart = echarts.init(el)
  chart.setOption(option)
  charts.value.push(chart)
}

onMounted(async () => {
  const { data } = await client.get('/dashboard/stats')
  cards.value[0].value = data.total_vulns
  cards.value[1].value = data.open_vulns
  cards.value[2].value = `${data.fix_rate}%`
  cards.value[3].value = data.total_assets

  mk(trendRef.value, {
    tooltip: { trigger: 'axis' },
    legend: { data: ['提交', '修复完成'] },
    grid: { left: 40, right: 16, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: data.trend.map((t: any) => t.month) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '提交', type: 'line', smooth: true, areaStyle: { opacity: 0.15 }, data: data.trend.map((t: any) => t.submitted), color: '#409EFF' },
      { name: '修复完成', type: 'line', smooth: true, areaStyle: { opacity: 0.15 }, data: data.trend.map((t: any) => t.fixed), color: '#67C23A' },
    ],
  })

  mk(levelRef.value, {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: ['42%', '68%'], center: ['50%', '45%'],
      label: { formatter: '{b}: {c}' },
      data: data.by_level.map((x: any) => ({
        name: x.name, value: x.count,
        itemStyle: { color: LEVEL_COLORS_BY_NAME[x.name] },
      })),
    }],
  })

  mk(statusRef.value, {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie', radius: '62%', center: ['50%', '45%'],
      data: data.by_status.map((x: any) => ({
        name: x.name, value: x.count,
        itemStyle: { color: STATUS_COLORS_BY_NAME[x.name] },
      })),
    }],
  })

  mk(typeRef.value, {
    tooltip: { trigger: 'axis' },
    grid: { left: 110, right: 24, top: 16, bottom: 30 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: data.by_type.map((x: any) => x.name).reverse() },
    series: [{ type: 'bar', barMaxWidth: 18, color: '#409EFF', data: data.by_type.map((x: any) => x.count).reverse() }],
  })

  // 部门安全概况：柱状（提测/漏洞/已修复）+ 折线（修复率，右轴）
  deptData.value = data.by_department ?? []
  if (deptData.value.length) {
    await nextTick()
    mk(deptRef.value, {
      tooltip: { trigger: 'axis' },
      legend: { data: ['提测次数', '发现漏洞', '已修复', '修复率(%)'] },
      grid: { left: 48, right: 48, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: deptData.value.map((d: any) => d.department) },
      yAxis: [
        { type: 'value', minInterval: 1 },
        { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      ],
      series: [
        { name: '提测次数', type: 'bar', barMaxWidth: 24, color: '#409EFF', data: deptData.value.map((d: any) => d.plans) },
        { name: '发现漏洞', type: 'bar', barMaxWidth: 24, color: '#E6A23C', data: deptData.value.map((d: any) => d.vulns) },
        { name: '已修复', type: 'bar', barMaxWidth: 24, color: '#67C23A', data: deptData.value.map((d: any) => d.fixed) },
        { name: '修复率(%)', type: 'line', yAxisIndex: 1, color: '#F56C6C', data: deptData.value.map((d: any) => d.fix_rate) },
      ],
    })
  }

  window.addEventListener('resize', onResize)
})

function onResize() {
  charts.value.forEach((c) => c.resize())
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  charts.value.forEach((c) => c.dispose())
})
</script>
