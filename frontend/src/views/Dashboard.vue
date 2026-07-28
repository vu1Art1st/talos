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
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import * as echarts from 'echarts'
import { DataLine, CircleCheck, Warning, Grid } from '@element-plus/icons-vue'
import client from '../api/client'
import { LEVEL_COLORS_BY_NAME, STATUS_COLORS_BY_NAME } from '../utils/colors'

const trendRef = ref<HTMLElement>()
const levelRef = ref<HTMLElement>()
const statusRef = ref<HTMLElement>()
const typeRef = ref<HTMLElement>()
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
