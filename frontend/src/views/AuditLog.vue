<template>
  <el-card shadow="never" class="!rounded-lg" v-loading="loading">
    <template #header>
      <div class="flex items-center gap-2">
        <span class="text-base font-semibold">审计日志</span>
        <span class="text-sm text-gray-400">登录事件与敏感操作记录</span>
      </div>
    </template>

    <div class="flex flex-wrap items-center gap-2 mb-4">
      <el-input v-model="filters.username" placeholder="用户名" clearable class="!w-40" />
      <el-select v-model="filters.action" placeholder="动作" clearable filterable class="!w-44">
        <el-option v-for="(name, code) in actionOptions" :key="code" :label="name" :value="code" />
      </el-select>
      <el-input v-model="filters.ip" placeholder="IP" clearable class="!w-36" />
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
                      start-placeholder="开始日期" end-placeholder="结束日期" class="!w-64" />
      <el-button @click="reload">查询</el-button>
    </div>

    <el-tabs v-model="activeTab" @tab-change="reload">
      <el-tab-pane label="登录日志" name="login" />
      <el-tab-pane label="操作日志" name="operation" />
      <el-tab-pane label="全部" name="all" />
    </el-tabs>

    <el-table :data="items" stripe @sort-change="onSortChange">
      <el-table-column prop="create_time" label="时间" width="170" sortable="custom">
        <template #default="{ row }">{{ fmtDateTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column prop="username" label="用户" width="120">
        <template #default="{ row }">{{ row.username || '-' }}</template>
      </el-table-column>
      <el-table-column prop="action" label="动作" width="130" sortable="custom">
        <template #default="{ row }">
          <span class="tl-tag" :style="softStyle(actionColor(row.action))">{{ actionName(row.action) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="详情" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ detailText(row.detail) || '-' }}</template>
      </el-table-column>
      <el-table-column prop="ip" label="IP" width="130">
        <template #default="{ row }">{{ row.ip || '-' }}</template>
      </el-table-column>
      <el-table-column label="User-Agent" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.user_agent || '-' }}</template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无日志记录" :image-size="80" />
      </template>
    </el-table>

    <div class="mt-4 flex justify-end">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useListPage } from '../composables/useListPage'
import { useAuthStore } from '../stores/auth'
import { softStyle, STAT_CARD_COLORS } from '../utils/colors'
import { fmtDateTime } from '../utils/format'

const auth = useAuthStore()
const activeTab = ref<'login' | 'operation' | 'all'>('login')
const dateRange = ref<[string, string] | null>(null)
const filters = reactive({ username: '', action: '', ip: '' })

const { items, total, page, loading, load, reload, onSortChange } = useListPage('/audit/logs', {
  defaultSort: { prop: 'create_time', order: 'descending' },
  extraParams: () => ({
    category: activeTab.value,
    username: filters.username,
    action: filters.action,
    ip: filters.ip,
    date_from: dateRange.value?.[0] ?? '',
    date_to: dateRange.value?.[1] ?? '',
  }),
})

const actionOptions = computed<Record<string, string>>(() => {
  const all = (auth.meta as any)?.audit_actions ?? {}
  return activeTab.value === 'login'
    ? Object.fromEntries(Object.entries(all).filter(([k]) => k.startsWith('login_')))
    : all
})

const actionName = (action: string) =>
  ((auth.meta as any)?.audit_actions as Record<string, string>)?.[action] ?? action

const actionColor = (action: string) => {
  if (action === 'login_success') return STAT_CARD_COLORS.green
  if (action.startsWith('login_')) return STAT_CARD_COLORS.red
  if (action.includes('delete') || action.includes('revoke')) return STAT_CARD_COLORS.red
  if (action.includes('create') || action.includes('transition') || action.includes('claim')) return STAT_CARD_COLORS.blue
  return STAT_CARD_COLORS.gray
}

const detailText = (raw: string) => {
  if (!raw) return ''
  try {
    return Object.entries(JSON.parse(raw))
      .filter(([k]) => k !== 'ip')
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('、') : v}`)
      .join('；')
  } catch {
    return raw
  }
}

onMounted(async () => {
  await auth.fetchMeta()
  await load()
})
</script>
