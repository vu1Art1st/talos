<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索系统 / 类型 / 部门" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="statusFilter" clearable placeholder="全部状态" class="!w-36" @change="load(1)">
        <el-option v-for="(name, code) in statusMap" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <div class="flex-1" />
      <el-button type="primary" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增测试计划
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="system_name" label="测试系统" min-width="160" show-overflow-tooltip />
      <el-table-column prop="test_type" label="测试类型" width="110" show-overflow-tooltip />
      <el-table-column prop="department" label="所属部门" width="120" show-overflow-tooltip />
      <el-table-column label="状态" width="95">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusMap[row.status] ?? row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="测试人员" width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.testers?.length">
            {{ row.testers.map((u: any) => u.realname || u.username).join('、') }}
          </span>
          <span v-else class="text-gray-400">未认领</span>
        </template>
      </el-table-column>
      <el-table-column label="漏洞统计" width="180">
        <template #default="{ row }">
          <span class="inline-flex gap-1">
            <el-tag size="small" color="#A61B29" style="color:#fff;border:none">超 {{ row.stat_critical }}</el-tag>
            <el-tag size="small" type="danger">高 {{ row.stat_high }}</el-tag>
            <el-tag size="small" type="warning">中 {{ row.stat_medium }}</el-tag>
            <el-tag size="small" type="primary">低 {{ row.stat_low }}</el-tag>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="关联漏洞" width="90">
        <template #default="{ row }">
          <el-popover v-if="row.vuls?.length" placement="right" width="360" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.vuls.length }} 个</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="v in row.vuls" :key="v.id" class="flex items-center gap-2">
                <el-tag size="small" :color="levelColor(v.level)" style="color:#fff;border:none">
                  {{ levelName(v.level) }}
                </el-tag>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/vulns/${v.id}`)">#{{ v.id }} {{ v.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="需求接收" width="105">
        <template #default="{ row }">{{ row.receive_time || '-' }}</template>
      </el-table-column>
      <el-table-column label="复测完成" width="105">
        <template #default="{ row }">{{ row.retest_done_time || '-' }}</template>
      </el-table-column>
      <el-table-column label="复测轮数" width="90">
        <template #default="{ row }">
          <el-popover v-if="row.retest_round_count" placement="left" width="380" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.retest_round_count }} 轮</el-button>
            </template>
            <el-table :data="row.retest_rounds" size="small">
              <el-table-column label="轮次" width="55">
                <template #default="{ row: r }">第 {{ r.round_no }} 轮</template>
              </el-table-column>
              <el-table-column label="开始时间" width="105">
                <template #default="{ row: r }">{{ fmtTime(r.start_time) }}</template>
              </el-table-column>
              <el-table-column label="完成时间" width="105">
                <template #default="{ row: r }">
                  <el-tag v-if="!r.done_time" size="small" type="warning">进行中</el-tag>
                  <span v-else>{{ fmtTime(r.done_time) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="来源" show-overflow-tooltip>
                <template #default="{ row: r }">{{ r.source || '-' }}</template>
              </el-table-column>
            </el-table>
          </el-popover>
          <span v-else class="text-gray-400">0 轮</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="290" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isTester(row)" size="small" type="success" link @click="claim(row)">认领</el-button>
          <el-popconfirm v-else title="确认退出该计划的认领？" @confirm="quit(row)">
            <template #reference>
              <el-button size="small" type="info" link>退出</el-button>
            </template>
          </el-popconfirm>
          <el-button v-if="canOperate(row)" size="small" type="warning" link
                     @click="router.push(`/vulns/new?plan_id=${row.id}`)">录入漏洞</el-button>
          <el-button v-if="canOperate(row)" size="small" type="success" link
                     @click="router.push(`/reports?gen_plan=${row.id}`)">生成报告</el-button>
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该计划？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑测试计划' : '新增测试计划'" width="680px">
    <el-form :model="form" label-width="100px">
      <div class="grid grid-cols-2 gap-x-4">
        <el-form-item label="测试系统" required>
          <el-input v-model="form.system_name" />
        </el-form-item>
        <el-form-item label="测试类型">
          <el-select v-model="form.test_type" filterable clearable placeholder="请选择测试类型" class="w-full">
            <el-option v-for="t in testTypeOptions" :key="t" :label="t" :value="t" />
            <template #footer>
              <el-button size="small" type="primary" link @click="addTestType">
                <el-icon class="mr-1"><Plus /></el-icon>新增测试类型
              </el-button>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="所属部门">
          <el-select v-model="form.department" filterable clearable placeholder="请选择部门" class="w-full">
            <el-option v-for="d in departmentOptions" :key="d" :label="d" :value="d" />
            <template #footer>
              <el-button size="small" type="primary" link @click="addDepartment">
                <el-icon class="mr-1"><Plus /></el-icon>新增部门
              </el-button>
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="测试状态">
          <el-select v-model="form.status" class="w-full" :disabled="!statusEditable">
            <el-option v-for="(name, code) in statusMap" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="需求接收">
          <el-date-picker v-model="form.receive_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="初测完成">
          <el-date-picker v-model="form.first_test_done_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="复测通知">
          <el-date-picker v-model="form.retest_notice_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="复测完成">
          <el-date-picker v-model="form.retest_done_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
        </el-form-item>
        <el-form-item label="超危数">
          <el-input-number v-model="form.stat_critical" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
        <el-form-item label="高危数">
          <el-input-number v-model="form.stat_high" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
        <el-form-item label="中危数">
          <el-input-number v-model="form.stat_medium" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
        <el-form-item label="低危数">
          <el-input-number v-model="form.stat_low" :min="0" class="!w-full" :disabled="statsAuto" />
        </el-form-item>
      </div>
      <div v-if="statsAuto" class="text-xs text-gray-400 mb-2 pl-[100px]">
        已有关联漏洞，统计由系统按漏洞等级自动重算
      </div>
      <div v-if="form.id && !statusEditable" class="text-xs text-gray-400 mb-2 pl-[100px]">
        认领该计划后才可修改测试状态
      </div>
      <el-form-item label="漏洞简述">
        <el-input v-model="form.brief" type="textarea" :rows="2" placeholder="漏洞情况简述" />
      </el-form-item>
      <el-form-item label="详细描述">
        <el-input v-model="form.detail" type="textarea" :rows="4" placeholder="数据来源等详细信息" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!form.system_name" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelColor } from '../utils/colors'

const auth = useAuthStore()
const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const statusFilter = ref<number | null>(null)
const loading = ref(false)
const dialogVisible = ref(false)
const statusMap = ref<Record<number, string>>({})
const dialogRow = ref<any>(null)
const testTypes = ref<string[]>([])
const departments = ref<string[]>([])

const statusTag = (s: number) =>
  ({ 10: 'info', 20: 'warning', 30: 'primary', 40: 'danger', 50: 'warning', 60: 'success' } as Record<number, string>)[s] ?? 'info'

const levelName = (lv: number) =>
  ({ 10: '严重', 20: '高危', 30: '中危', 40: '低危', 50: '安全' } as Record<number, string>)[lv] ?? lv

const fmtTime = (t: string | null) => (t ? String(t).slice(0, 10) : '-')

// 旧数据的值可能不在字典/组织列表中，临时追加以正常回显
const testTypeOptions = computed(() =>
  form.value.test_type && !testTypes.value.includes(form.value.test_type)
    ? [...testTypes.value, form.value.test_type]
    : testTypes.value)
const departmentOptions = computed(() =>
  form.value.department && !departments.value.includes(form.value.department)
    ? [...departments.value, form.value.department]
    : departments.value)

const isAdmin = computed(() => auth.user?.permissions?.includes('*') ?? false)
const isTester = (row: any) => row.testers?.some((u: any) => u.id === auth.user?.id) ?? false
const canOperate = (row: any) => isAdmin.value || isTester(row)

// 状态：新建时仅管理员可指定；编辑时须为认领者或管理员
const statusEditable = computed(() =>
  form.value.id ? (dialogRow.value ? canOperate(dialogRow.value) : false) : isAdmin.value)
// 有关联漏洞时统计自动重算，禁止手填
const statsAuto = computed(() => (dialogRow.value?.vuls?.length ?? 0) > 0)

const emptyForm = () => ({
  id: null as number | null,
  system_name: '',
  test_type: '',
  department: '',
  receive_time: '',
  first_test_done_time: '',
  retest_notice_time: '',
  retest_done_time: '',
  status: 10,
  stat_critical: 0,
  stat_high: 0,
  stat_medium: 0,
  stat_low: 0,
  brief: '',
  detail: '',
})
const form = ref(emptyForm())

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const params: Record<string, any> = { search: search.value, page: p, size: 20 }
    if (statusFilter.value !== null && statusFilter.value !== ('' as any)) params.status = statusFilter.value
    const { data } = await client.get('/testing-plans', { params })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function openDialog(row?: any) {
  dialogRow.value = row ?? null
  form.value = row ? { ...emptyForm(), ...row } : emptyForm()
  dialogVisible.value = true
}

async function save() {
  const body = { ...form.value }
  delete (body as any).testers
  delete (body as any).vuls
  delete (body as any).retest_rounds
  delete (body as any).retest_round_count
  if (form.value.id) {
    await client.put(`/testing-plans/${form.value.id}`, body)
  } else {
    await client.post('/testing-plans', body)
  }
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await load()
}

async function loadTestTypes() {
  const { data } = await client.get('/dict/test_type')
  testTypes.value = data.map((o: any) => o.name)
}

async function loadDepartments() {
  const { data } = await client.get('/groups')
  departments.value = data.map((g: any) => g.name)
}

async function addTestType() {
  const { value } = await ElMessageBox.prompt('请输入新的测试类型名称', '新增测试类型', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/dict/test_type', { name: value.trim() })
  ElMessage.success('测试类型已新增')
  await loadTestTypes()
  form.value.test_type = value.trim()
}

async function addDepartment() {
  const { value } = await ElMessageBox.prompt('请输入新的部门（组织）名称，保存后同步至组织管理', '新增部门', {
    confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  }).catch(() => ({ value: '' }))
  if (!value?.trim()) return
  await client.post('/groups', { name: value.trim(), remark: '' })
  ElMessage.success('部门已新增')
  await loadDepartments()
  form.value.department = value.trim()
}

async function claim(row: any) {
  await client.post(`/testing-plans/${row.id}/claim`)
  ElMessage.success('认领成功，已加入测试人员')
  await load()
}

async function quit(row: any) {
  await client.post(`/testing-plans/${row.id}/quit`)
  ElMessage.success('已退出该计划')
  await load()
}

async function remove(id: number) {
  await client.delete(`/testing-plans/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(async () => {
  const meta = await auth.fetchMeta()
  statusMap.value = meta?.testing_plan_status ?? {}
  await Promise.all([load(1), loadTestTypes(), loadDepartments()])
})
</script>
