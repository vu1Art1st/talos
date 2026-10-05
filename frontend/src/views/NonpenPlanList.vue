<template>
  <div class="space-y-3">
    <FilterToolbar>
      <div class="tl-search-field">
        <el-input v-model="search" placeholder="搜索计划名称 / 系统 / 部门 / 工单ID" clearable
                  @keyup.enter="reload" @clear="reload">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <el-select v-model="actionable" class="!w-36" @change="reload">
        <el-option label="全部" :value="false" />
        <el-option label="仅可进行" :value="true" />
      </el-select>
      <template #actions>
        <el-button type="primary" class="btn-min" @click="openCreateDialog">
          <el-icon class="mr-1"><Plus /></el-icon>新增漏扫基线工单
        </el-button>
      </template>
    </FilterToolbar>

    <!-- 统计概览：总数 / 复测完成 / 三类扫描次数 -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
      <StatCard label="漏扫基线工单总数" :color="STAT_CARD_COLORS.blue" :value="stats.total ?? 0" />
      <StatCard label="复测完成数" :color="STAT_CARD_COLORS.green" :value="stats.retest_done ?? 0" />
      <StatCard label="基线扫描次数" :color="STAT_CARD_COLORS.orange" :value="stats.baseline_times ?? 0" />
      <StatCard label="主机扫描次数" :color="STAT_CARD_COLORS.red" :value="stats.host_times ?? 0" />
      <StatCard label="Web扫描次数" :color="STAT_CARD_COLORS.gray" :value="stats.web_times ?? 0" />
    </div>

    <el-card shadow="never" body-style="padding: 0 0 12px">
    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange"
              :default-sort="{ prop: 'receive_time', order: 'descending' }">
      <template #empty>
        <el-empty :image-size="80"
                  :description="actionable || search ? '未找到符合条件（可进行 / 搜索）的漏扫基线工单' : '暂无漏扫基线工单，点击右上角「新增漏扫基线工单」开始'" />
      </template>
      <el-table-column type="index" label="序号" width="64"
                       :index="(i: number) => (page - 1) * size + i + 1" />
      <el-table-column label="工单ID" min-width="150" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="font-mono" style="color: var(--el-color-primary); font-weight: 600">{{ row.ticket_id || '-' }}</span>
          <span v-if="row.linked" class="linked-badge" title="由渗透测试工单联动创建，编辑/删除将与对方双向同步">联动</span>
        </template>
      </el-table-column>
      <el-table-column prop="plan_name" label="计划名称" min-width="130" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.plan_name || '-' }}</template>
      </el-table-column>
      <el-table-column prop="system_name" label="测试系统" min-width="140" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="test_type" label="测试类型" width="150" show-overflow-tooltip sortable="custom"
                       label-class-name="col-test-type">
        <template #default="{ row }">{{ row.test_type || '-' }}</template>
      </el-table-column>
      <el-table-column prop="department" label="所属部门" width="110" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.department || '-' }}</template>
      </el-table-column>
      <el-table-column label="工单提起" width="100">
        <template #default="{ row }">{{ fmtDate(row.ticket_time) }}</template>
      </el-table-column>
      <el-table-column prop="receive_time" label="需求接收" width="115" sortable="custom">
        <template #default="{ row }">{{ fmtDate(row.receive_time) }}</template>
      </el-table-column>
      <el-table-column v-for="t in nonpenItems()" :key="t.key" :label="t.name" width="100">
        <template #default="{ row }">
          <span v-if="row.items?.[t.key]" class="dot-tag" :class="{ 'ignored-tag': row.items[t.key].status === 'ignored' }"
                :style="dotStyle(nonpenItemMeta(row.items[t.key].status).color)">
            <i></i>{{ nonpenItemMeta(row.items[t.key].status).label }}
          </span>
          <span v-else style="color: var(--tl-text-3)">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openPlanDrawer(row, 'info')">工单信息</el-button>
          <el-button size="small" type="primary" link @click="openPlanDrawer(row, 'flow')">流程</el-button>
          <el-popconfirm :title="row.linked ? '确认删除？将同步删除其来源渗透测试工单' : '确认删除该漏扫基线工单？'"
                         @confirm="remove(row)">
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
  <el-dialog v-model="createVisible" title="新增漏扫基线工单" width="800px" :close-on-click-modal="false">
    <NonpenPlanInfoPanel v-if="createVisible" mode="create"
                         @saved="onCreated" @cancel="createVisible = false" />
  </el-dialog>

  <NonpenPlanWorkflowDrawer v-model:visible="drawerVisible" v-model:tab="drawerTab"
                            :plan-id="drawerPlanId" @changed="reload" />
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import client from '../api/client'
import FilterToolbar from '../components/FilterToolbar.vue'
import TlPagination from '../components/TlPagination.vue'
import NonpenPlanInfoPanel from '../components/NonpenPlanInfoPanel.vue'
import NonpenPlanWorkflowDrawer from '../components/NonpenPlanWorkflowDrawer.vue'
import StatCard from '../components/StatCard.vue'
import { useListPage } from '../composables/useListPage'
import { dotStyle, nonpenItemMeta, nonpenItems, STAT_CARD_COLORS } from '../utils/colors'
import { fmtDate } from '../utils/format'
import type { NonpenPlan, PlanDrawerTab } from '../types'

const route = useRoute()
const router = useRouter()

const actionable = ref(false)
const { items, total, page, size, search, sort, loading, load, onSortChange, onSizeChange } = useListPage<NonpenPlan>('/nonpen-plans', {
  defaultSort: { prop: 'receive_time', order: 'desc' },
  extraParams: () => (actionable.value ? { actionable: true } : {}),
})
const stats = ref<Record<string, number>>({})
const createVisible = ref(false)

async function loadStats() {
  const { data } = await client.get('/nonpen-plans/stats')
  stats.value = data
}

async function reload() {
  await Promise.all([load(1), loadStats()])
}

function openCreateDialog() {
  createVisible.value = true
}

async function onCreated() {
  createVisible.value = false
  await reload()
}

async function remove(row: NonpenPlan) {
  if (row.linked) {
    await ElMessageBox.confirm(
      `该计划由渗透测试工单联动创建，删除将同步删除其来源渗透测试工单（互相级联），确认删除「${row.plan_name || row.system_name}」？`,
      '删除确认', { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' },
    )
  }
  await client.delete(`/nonpen-plans/${row.id}`)
  ElMessage.success('删除成功')
  await reload()
}

// ---------- 工单抽屉：工单信息 / 测试流程 两个标签共用 ----------
const drawerVisible = ref(false)
const drawerPlanId = ref<number | null>(null)
const drawerTab = ref<PlanDrawerTab>('flow')

function openPlanDrawer(row: NonpenPlan, tab: PlanDrawerTab) {
  drawerPlanId.value = row.id
  drawerTab.value = tab
  drawerVisible.value = true
}

function routeTab(value: unknown): PlanDrawerTab {
  return value === 'info' ? 'info' : 'flow'
}

// 抽屉显隐 ↔ URL：打开写 plan + tab，关闭清除；replace 避免污染历史栈
watch(drawerVisible, (v) => {
  const query = { ...route.query }
  if (v && drawerPlanId.value) {
    query.plan = String(drawerPlanId.value)
    query.tab = drawerTab.value
  } else {
    delete query.plan
    delete query.tab
  }
  void router.replace({ query }).catch(() => {})
})

// 标签变化同样写 URL，保证刷新/分享后落在同一标签
watch(drawerTab, (tab) => {
  if (!drawerVisible.value || !drawerPlanId.value) return
  const query = { ...route.query, plan: String(drawerPlanId.value), tab }
  void router.replace({ query }).catch(() => {})
})

// 首次进入（含站内深链 ?plan=<id>&tab=<info|flow>）按 URL 恢复抽屉
onMounted(() => {
  const planQ = Number(route.query.plan)
  if (Number.isInteger(planQ) && planQ > 0) {
    drawerPlanId.value = planQ
    drawerTab.value = routeTab(route.query.tab)
    drawerVisible.value = true
  }
})

// 路由参数变化（组件复用、onMounted 不再触发）时同步打开
watch(() => [route.query.plan, route.query.tab] as const, ([q, tab]) => {
  const id = Number(q)
  if (!Number.isInteger(id) || id <= 0) return
  const nextTab = routeTab(tab)
  if (drawerVisible.value && drawerPlanId.value === id && drawerTab.value === nextTab) return
  drawerPlanId.value = id
  drawerTab.value = nextTab
  drawerVisible.value = true
})

onMounted(() => {
  void reload()
})
</script>

<style scoped>
/* 表头统一单行：文案+排序箭头不换行，保持各列表头整洁对齐 */
:deep(.el-table th .cell) {
  white-space: nowrap;
}
/* 忽略标签弱化：低透明度 + 删除线，与「未开始」正常灰区分 */
.ignored-tag {
  text-decoration: line-through;
  opacity: 0.55;
}

/* 测试项勾选卡片 */
</style>
