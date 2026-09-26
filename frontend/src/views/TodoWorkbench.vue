<template>
  <div class="flex flex-col gap-4" v-loading="loading">
    <div class="flex items-center gap-3">
      <span class="text-sm font-semibold">个人待办</span>
      <span class="text-xs text-gray-400">按你的权限聚合：待认领 / 我提交的漏洞 / 待复测 / 待确认导入 / SLA 临期与逾期</span>
      <div class="flex-1" />
      <el-button class="btn-min" @click="load">刷新</el-button>
    </div>

    <el-empty v-if="!loading && !groups.length" description="暂无待办事项" :image-size="80" />

    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <el-card v-for="g in groups" :key="g.category" shadow="never" class="todo-card">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="text-sm font-semibold">{{ g.name || todoTypeName(g.category) }}</span>
            <span class="tl-tag" :style="softStyle(categoryColor(g.category))">{{ g.count }}</span>
            <div class="flex-1" />
            <el-button size="small" link @click="goList(g.category)">查看全部</el-button>
          </div>
        </template>
        <el-empty v-if="!g.items.length" description="无" :image-size="48" />
        <ul v-else class="todo-list">
          <li v-for="(it, idx) in g.items" :key="idx" @click="goItem(g.category, it)">
            <span class="truncate">{{ itemTitle(g.category, it) }}</span>
            <span class="text-2xs text-gray-400 flex-none">{{ itemExtra(g.category, it) }}</span>
          </li>
        </ul>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import client from '../api/client'
import { softStyle, STAT_CARD_COLORS, todoTypeName } from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import type { TodoGroup, TodoSummary } from '../types'

const router = useRouter()
const loading = ref(false)
const groups = ref<TodoGroup[]>([])

const CATEGORY_COLORS: Record<string, string> = {
  plan_unclaimed: STAT_CARD_COLORS.blue,
  my_vulns: STAT_CARD_COLORS.orange,
  retest: STAT_CARD_COLORS.orange,
  import_pending: STAT_CARD_COLORS.blue,
  sla_due: STAT_CARD_COLORS.orange,
  sla_overdue: STAT_CARD_COLORS.red,
}

const categoryColor = (c: string) => CATEGORY_COLORS[c] ?? STAT_CARD_COLORS.gray

function itemTitle(category: string, it: Record<string, unknown>): string {
  if (category === 'plan_unclaimed' || category === 'retest') {
    return `${it.system_name ?? ''}（${it.ticket_id ?? '-'}）`
  }
  if (category === 'import_pending') return String(it.filename ?? '')
  return String(it.title ?? '')
}

function itemExtra(category: string, it: Record<string, unknown>): string {
  if (category === 'sla_due' || category === 'sla_overdue') {
    return it.due_at ? fmtDateTime(String(it.due_at)) : ''
  }
  if (category === 'plan_unclaimed') return String(it.department ?? '')
  if (category === 'import_pending') return `${it.total ?? 0} 条记录`
  return ''
}

function goList(category: string) {
  const routes: Record<string, string> = {
    plan_unclaimed: '/testing-plans',
    my_vulns: '/vulns',
    retest: '/testing-plans',
    import_pending: '/reports/imports',
    sla_due: '/vulns',
    sla_overdue: '/vulns',
  }
  router.push(routes[category] ?? '/dashboard')
}

function goItem(category: string, it: Record<string, unknown>) {
  const link = it.link
  if (typeof link === 'string' && link) {
    router.push(link)
    return
  }
  goList(category)
}

async function load() {
  loading.value = true
  try {
    const { data } = await client.get<TodoSummary>('/todos')
    groups.value = data.groups
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.todo-list { list-style: none; margin: 0; padding: 0; }
.todo-list li {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 6px; border-radius: 6px; font-size: 13px;
  color: var(--tl-text-1); cursor: pointer;
}
.todo-list li:hover { background: var(--tl-surface-2); }
</style>
