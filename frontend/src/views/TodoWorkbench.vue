<template>
  <div class="flex flex-col gap-4" v-loading="loading">
    <div class="flex items-center gap-3">
      <span class="text-sm font-semibold">个人待办</span>
      <span class="text-xs text-gray-400">按权限聚合原有待办，并新增已认领的进行中 / 已完成工单</span>
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
            <el-button v-if="g.count > 0" size="small" link @click="toggleAll(g)">
              {{ expanded[g.category] ? '收起' : '查看全部' }}
            </el-button>
          </div>
        </template>
        <el-empty v-if="!displayItems(g).length" description="无" :image-size="48" />
        <template v-else>
          <ul class="todo-list" :class="{ 'todo-list-scroll': expanded[g.category] }">
            <li v-for="(it, idx) in displayItems(g)" :key="String(it.id ?? idx)" @click="goItem(g, it)">
              <span class="truncate">{{ itemTitle(g.category, it) }}</span>
              <span class="text-2xs text-gray-400 flex-none">{{ itemExtra(g.category, it) }}</span>
            </li>
          </ul>
          <div v-if="expanded[g.category]" class="todo-more">
            <el-button v-if="hasMore(g)" size="small" link :loading="loadingMore[g.category] === true"
                       @click="loadMore(g)">
              加载更多（{{ displayItems(g).length }} / {{ g.count }}）
            </el-button>
            <span v-else class="text-2xs text-gray-400">已显示全部 {{ g.count }} 条</span>
          </div>
        </template>
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
import type { TodoGroup, TodoItemPage, TodoSummary } from '../types'

/** 展开态每页拉取的条数（页面内「加载更多」追加） */
const EXPAND_PAGE_SIZE = 20

const router = useRouter()
const loading = ref(false)
const groups = ref<TodoGroup[]>([])
/** 分类 → 是否已在卡片内展开（展开只影响本卡片，不做任何路由跳转） */
const expanded = ref<Record<string, boolean>>({})
/** 分类 → 展开态已拉取的完整明细 */
const fullItems = ref<Record<string, Record<string, unknown>[]>>({})
const loadingMore = ref<Record<string, boolean>>({})

const CATEGORY_COLORS: Record<string, string> = {
  plan_unclaimed: STAT_CARD_COLORS.blue,
  my_vulns: STAT_CARD_COLORS.orange,
  retest: STAT_CARD_COLORS.orange,
  import_pending: STAT_CARD_COLORS.blue,
  sla_due: STAT_CARD_COLORS.orange,
  sla_overdue: STAT_CARD_COLORS.red,
  plan_in_progress: STAT_CARD_COLORS.blue,
  plan_completed: STAT_CARD_COLORS.green,
}

const categoryColor = (c: string) => CATEGORY_COLORS[c] ?? STAT_CARD_COLORS.gray

function itemTitle(category: string, it: Record<string, unknown>): string {
  if (
    category === 'plan_unclaimed'
    || category === 'retest'
    || category === 'plan_in_progress'
    || category === 'plan_completed'
  ) {
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
  if (category === 'plan_in_progress' || category === 'plan_completed') {
    return String(it.status_name ?? it.department ?? '')
  }
  return ''
}

/** 展开态展示完整明细（已拉取的缓存优先），折叠态只展示聚合接口带回的最近几条 */
const displayItems = (g: TodoGroup) => (
  expanded.value[g.category] ? (fullItems.value[g.category] ?? g.items) : g.items
)

const hasMore = (g: TodoGroup) => displayItems(g).length < g.count

async function loadMore(g: TodoGroup) {
  // 只用展开态已拉取的条数推进分页，避免把折叠态的预览条目算作重复明细
  const shown = fullItems.value[g.category] ?? []
  loadingMore.value = { ...loadingMore.value, [g.category]: true }
  try {
    const page = Math.floor(shown.length / EXPAND_PAGE_SIZE) + 1
    const { data } = await client.get<TodoItemPage>(`/todos/${g.category}`, {
      params: { page, size: EXPAND_PAGE_SIZE },
    })
    fullItems.value = { ...fullItems.value, [g.category]: [...shown, ...data.items] }
  } finally {
    loadingMore.value = { ...loadingMore.value, [g.category]: false }
  }
}

/** 「查看全部 / 收起」：在卡片内展开全部待办，不跳转到工单等其他列表页 */
async function toggleAll(g: TodoGroup) {
  const open = expanded.value[g.category] !== true
  expanded.value = { ...expanded.value, [g.category]: open }
  if (!open || fullItems.value[g.category]) return
  if (g.items.length >= g.count) {
    fullItems.value = { ...fullItems.value, [g.category]: g.items }
    return
  }
  await loadMore(g)
}

/** 条目自带深链时直达对象；无深链时展开所在卡片，不做列表页兜底跳转 */
function goItem(g: TodoGroup, it: Record<string, unknown>) {
  const link = it.link
  if (typeof link === 'string' && link) {
    router.push(link)
    return
  }
  void toggleAll(g)
}

async function load() {
  loading.value = true
  try {
    const { data } = await client.get<TodoSummary>('/todos')
    groups.value = data.groups
    const opened = groups.value.filter((g) => expanded.value[g.category] === true)
    fullItems.value = {}
    for (const g of opened) await loadMore(g)
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
/* 展开态条目较多时限高滚动，避免单张卡片撑满整页 */
.todo-list-scroll { max-height: 320px; overflow-y: auto; }
.todo-more { display: flex; align-items: center; justify-content: center; padding-top: 6px; }
</style>
