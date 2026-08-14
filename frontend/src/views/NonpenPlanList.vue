<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center flex-wrap gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索计划名称 / 系统 / 部门 / 工单ID" clearable class="!w-64"
                @keyup.enter="reload" @clear="reload">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="actionable" class="!w-36" @change="reload">
        <el-option label="全部" :value="false" />
        <el-option label="仅可进行" :value="true" />
      </el-select>
      <div class="flex-1" />
      <el-button type="primary" class="btn-min" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增漏扫基线工单
      </el-button>
    </div>

    <!-- 统计概览：总数 / 复测完成 / 三类扫描次数 -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-4">
      <div class="rounded-lg border px-5 py-4" style="border-color: var(--tl-border); background: var(--tl-surface-2)">
        <div class="text-xs" style="color: var(--tl-text-3)">漏扫基线工单总数</div>
        <div class="text-2xl font-semibold" :style="{ color: STAT_CARD_COLORS.blue }">{{ stats.total ?? 0 }}</div>
      </div>
      <div class="rounded-lg border px-5 py-4" style="border-color: var(--tl-border); background: var(--tl-surface-2)">
        <div class="text-xs" style="color: var(--tl-text-3)">复测完成数</div>
        <div class="text-2xl font-semibold" :style="{ color: STAT_CARD_COLORS.green }">{{ stats.retest_done ?? 0 }}</div>
      </div>
      <div class="rounded-lg border px-5 py-4" style="border-color: var(--tl-border); background: var(--tl-surface-2)">
        <div class="text-xs" style="color: var(--tl-text-3)">基线扫描次数</div>
        <div class="text-2xl font-semibold" :style="{ color: STAT_CARD_COLORS.orange }">{{ stats.baseline_times ?? 0 }}</div>
      </div>
      <div class="rounded-lg border px-5 py-4" style="border-color: var(--tl-border); background: var(--tl-surface-2)">
        <div class="text-xs" style="color: var(--tl-text-3)">主机扫描次数</div>
        <div class="text-2xl font-semibold" :style="{ color: STAT_CARD_COLORS.red }">{{ stats.host_times ?? 0 }}</div>
      </div>
      <div class="rounded-lg border px-5 py-4" style="border-color: var(--tl-border); background: var(--tl-surface-2)">
        <div class="text-xs" style="color: var(--tl-text-3)">Web扫描次数</div>
        <div class="text-2xl font-semibold" :style="{ color: STAT_CARD_COLORS.gray }">{{ stats.web_times ?? 0 }}</div>
      </div>
    </div>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange"
              :default-sort="{ prop: 'receive_time', order: 'descending' }">
      <template #empty>
        <el-empty :image-size="80"
                  :description="actionable || search ? '未找到符合条件（可进行 / 搜索）的漏扫基线工单' : '暂无漏扫基线工单，点击右上角「新增漏扫基线工单」开始'" />
      </template>
      <el-table-column type="index" label="序号" width="60"
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
      <el-table-column v-for="t in NONPEN_ITEMS" :key="t.key" :label="t.name" width="100">
        <template #default="{ row }">
          <span v-if="row.items?.[t.key]" class="tl-tag" :class="{ 'ignored-tag': row.items[t.key].status === 'ignored' }"
                :style="softStyle(nonpenItemMeta(row.items[t.key].status).color)">
            {{ nonpenItemMeta(row.items[t.key].status).label }}
          </span>
          <span v-else style="color: var(--tl-text-3)">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openWorkflow(row)">流程</el-button>
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm :title="row.linked ? '确认删除？将同步删除其来源渗透测试工单' : '确认删除该漏扫基线工单？'"
                         @confirm="remove(row)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="size" :current-page="page" @current-change="load" />
    </div>
  </el-card>

  <!-- 新增 / 编辑弹窗 -->
  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑漏扫基线工单' : '新增漏扫基线工单'" width="760px"
             :close-on-click-modal="false">
    <el-form :model="form" label-width="90px">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6">
        <el-form-item label="计划名称">
          <el-input v-model="form.plan_name" placeholder="与测试系统区分的漏扫基线工单名称" />
        </el-form-item>
        <el-form-item label="关联资产">
          <div class="w-full flex gap-2">
            <el-select v-model="form.asset_ids" multiple filterable remote clearable
                       :remote-method="searchAssets" :loading="assetLoading"
                       placeholder="输入资产名称搜索并选择，选择后自动带出测试系统与所属部门" class="flex-1"
                       @change="onAssetsChange">
              <el-option v-for="a in assetOptions" :key="a.id" :label="a.label" :value="a.id" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="测试系统" required>
          <el-input v-model="form.system_name" placeholder="被测系统名称" />
        </el-form-item>
        <el-form-item label="测试类型">
          <el-select v-model="form.test_type" filterable clearable placeholder="请选择测试类型" class="w-full">
            <el-option v-for="t in testTypeOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属部门">
          <el-select v-model="form.department" filterable clearable placeholder="请选择部门" class="w-full">
            <el-option v-for="d in departmentOptions" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="工单ID">
          <div class="w-full">
            <el-input v-model="form.ticket_id_manual" placeholder="留空则按需求接收日期自动生成（如 20260810-1）"
                      clearable />
            <div v-if="form.id && !form.ticket_id_manual && form.ticket_id"
                 class="text-xs mt-1" style="color: var(--tl-text-3)">当前自动生成：{{ form.ticket_id }}，留空保存即保持该值</div>
          </div>
        </el-form-item>
        <el-form-item label="工单提起">
          <el-date-picker v-model="form.ticket_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="需求接收">
          <el-date-picker v-model="form.receive_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
      </div>
      <el-form-item label="测试项">
        <div class="w-full grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div v-for="t in NONPEN_ITEMS" :key="t.key" class="test-item-check" :class="{ checked: form.test_items.includes(t.key) }"
               @click="toggleTestItem(t.key)">
            <div class="tick"><el-icon v-if="form.test_items.includes(t.key)" :size="13"><Check /></el-icon></div>
            <div>
              <div class="ti-name">{{ t.name }}</div>
              <div class="ti-desc">{{ t.desc }}</div>
            </div>
          </div>
        </div>
        <div class="text-xs mt-1" style="color: var(--tl-text-3)">未勾选的测试项将标记为「忽略」，不参与统计</div>
      </el-form-item>
      <el-form-item label="详细描述">
        <el-input v-model="form.detail" type="textarea" :rows="4" placeholder="扫描范围、数据来源等详细信息" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!form.system_name" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <NonpenPlanWorkflowDrawer v-model:visible="workflowVisible" :plan-id="workflowPlanId" @changed="reload" />
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Plus, Search } from '@element-plus/icons-vue'
import client from '../api/client'
import { softStyle, STAT_CARD_COLORS } from '../utils/colors'
import { fmtDate } from '../utils/format'
import { NONPEN_ITEMS, nonpenItemMeta } from '../constants/nonpen'
import NonpenPlanWorkflowDrawer from '../components/NonpenPlanWorkflowDrawer.vue'

const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const search = ref('')
const actionable = ref(false)
const sort = reactive<{ prop: string; order: string }>({ prop: 'receive_time', order: 'desc' })
const loading = ref(false)
const stats = ref<Record<string, number>>({})
const dialogVisible = ref(false)
const testTypes = ref<string[]>([])
const departments = ref<string[]>([])

const emptyForm = () => ({
  id: null as number | null,
  plan_name: '',
  system_name: '',
  test_type: '',
  department: '',
  receive_time: '',
  ticket_time: '',
  ticket_id_manual: '',
  asset_ids: [] as number[],
  test_items: [] as string[],
  detail: '',
})
const form = ref(emptyForm())

// 旧数据的值可能不在字典/组织列表中，临时追加以正常回显
const testTypeOptions = computed(() =>
  form.value.test_type && !testTypes.value.includes(form.value.test_type)
    ? [...testTypes.value, form.value.test_type]
    : testTypes.value)
const departmentOptions = computed(() =>
  form.value.department && !departments.value.includes(form.value.department)
    ? [...departments.value, form.value.department]
    : departments.value)

function filterParams(): Record<string, any> {
  const params: Record<string, any> = { search: search.value }
  if (actionable.value) params.actionable = true
  if (sort.prop) {
    params.sort = sort.prop
    params.order = sort.order
  }
  return params
}

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/nonpen-plans', {
      params: { ...filterParams(), page: p, size: size.value },
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const { data } = await client.get('/nonpen-plans/stats')
  stats.value = data
}

function onSortChange({ prop, order }: any) {
  sort.prop = order ? prop : ''
  sort.order = order === 'ascending' ? 'asc' : order === 'descending' ? 'desc' : ''
  load(1)
}

async function reload() {
  await Promise.all([load(1), loadStats()])
}

function toggleTestItem(key: string) {
  const i = form.value.test_items.indexOf(key)
  if (i >= 0) form.value.test_items.splice(i, 1)
  else form.value.test_items.push(key)
}

function openDialog(row?: any) {
  form.value = row
    ? { ...emptyForm(), ...row, test_items: selectedItems(row) }
    : emptyForm()
  form.value.asset_ids = Array.isArray(form.value.asset_ids) ? form.value.asset_ids : []
  assetOptions.value = []
  if (form.value.asset_ids.length) loadAssetLabels()
  prevAssetIds = [...form.value.asset_ids]
  dialogVisible.value = true
}

// 编辑回显：非忽略（有效）测试项即为已勾选项
function selectedItems(row: any): string[] {
  const itemsMap = row.items ?? {}
  return NONPEN_ITEMS
    .filter((t) => itemsMap[t.key] && itemsMap[t.key].status !== 'ignored')
    .map((t) => t.key)
}

async function save() {
  // 工单ID必须有来源：需求接收日期（自动生成）或手动工单ID（二者至少其一）
  if (!form.value.ticket_id_manual && !form.value.receive_time) {
    ElMessage.warning('请填写「需求接收日期」（用于自动生成工单ID），或手动指定工单ID')
    return
  }
  const body: any = { ...form.value }
  delete body.id
  delete body.ticket_id
  delete body.ticket_seq
  delete body.items
  delete body.linked
  delete body.actionable
  delete body.testing_plan_id
  delete body.create_time
  delete body.update_time
  if (form.value.id) {
    await client.put(`/nonpen-plans/${form.value.id}`, body)
  } else {
    await client.post('/nonpen-plans', body)
  }
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await reload()
}

async function remove(row: any) {
  if (row.linked) {
    await ElMessageBox.confirm(
      `该计划由渗透测试工单联动创建，删除将同步删除其来源渗透测试工单（互相级联），确认删除「${row.plan_name || row.system_name}」？`,
      '删除确认', { type: 'warning' },
    )
  }
  await client.delete(`/nonpen-plans/${row.id}`)
  ElMessage.success('删除成功')
  await reload()
}

// ---------- 关联资产 ----------
const assetOptions = ref<any[]>([])
const assetLoading = ref(false)
const assetCache = ref<Record<number, any>>({})
let prevAssetIds: number[] = []

function assetLabel(a: any) {
  const parts = [a.name]
  if (a.sub_system) parts.push(`（${a.sub_system}）`)
  if (a.system_type) parts.push(`（${a.system_type}）`)
  return parts.join('')
}

async function searchAssets(keyword: string) {
  assetLoading.value = true
  try {
    const { data } = await client.get('/assets', {
      params: { search: keyword, page: 1, size: 50 },
    })
    assetOptions.value = data.items.map((a: any) => {
      assetCache.value[a.id] = a
      return { id: a.id, label: assetLabel(a) }
    })
  } finally {
    assetLoading.value = false
  }
}

async function loadAssetLabels() {
  const ids = [...form.value.asset_ids]
  if (!ids.length) return
  const rows = await Promise.all(
    ids.map((id: number) => client.get(`/assets/${id}`).catch(() => null)),
  )
  for (const r of rows) {
    const a = r?.data
    if (a && !assetOptions.value.some((o: any) => o.id === a.id)) {
      assetCache.value[a.id] = a
      assetOptions.value.push({ id: a.id, label: assetLabel(a) })
    }
  }
}

// 点选关联资产后自动带出测试系统/所属部门（仅新增模式），仅带出纯系统名称（不含系统类型/子系统），仍可手动修改
function onAssetsChange(ids: number[]) {
  if (form.value.id) return
  const added = ids.filter((id) => !prevAssetIds.includes(id))
  prevAssetIds = [...ids]
  if (!added.length) return
  const asset = assetCache.value[added[added.length - 1]]
  if (!asset) return
  if (asset.name) form.value.system_name = asset.name
  if (asset.department) form.value.department = asset.department
}

// ---------- 流程抽屉 ----------
const workflowVisible = ref(false)
const workflowPlanId = ref<number | null>(null)

function openWorkflow(row: any) {
  workflowPlanId.value = row.id
  workflowVisible.value = true
}

async function loadDicts() {
  const [{ data: t }, { data: g }] = await Promise.all([
    client.get('/dict/test_type'),
    client.get('/groups'),
  ])
  testTypes.value = t.map((o: any) => o.name)
  departments.value = g.map((x: any) => x.name)
}

onMounted(async () => {
  await loadDicts()
  await reload()
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
.test-item-check {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--tl-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--tl-surface);
}
.test-item-check:hover { border-color: var(--el-color-primary); }
.test-item-check.checked {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.test-item-check .tick {
  width: 18px;
  height: 18px;
  flex: none;
  margin-top: 1px;
  border-radius: 50%;
  border: 1px solid var(--tl-border);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}
.test-item-check.checked .tick {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary);
  color: #fff;
}
.ti-name { font-size: 13px; font-weight: 500; }
.ti-desc { font-size: 12px; margin-top: 2px; color: var(--tl-text-3); }
</style>
