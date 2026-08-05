<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索标题 / 系统 / 部门" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button type="primary" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增远程检测
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="70"
                       :index="(i: number) => (page - 1) * 20 + i + 1" />
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="system_name" label="系统名称" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="test_time" label="检测时间" width="120" sortable="custom">
        <template #default="{ row }">{{ row.test_time || '-' }}</template>
      </el-table-column>
      <el-table-column prop="department" label="所属部门" width="140" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="appeal_success" label="申诉结果" width="100" sortable="custom">
        <template #default="{ row }">
          <el-tag :type="row.appeal_success ? 'success' : 'info'" size="small">
            {{ row.appeal_success ? '申诉成功' : '未申诉/失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申诉报告" width="110">
        <template #default="{ row }">
          <el-button v-if="row.appeal_report_id" size="small" type="primary" link
                     @click="router.push(`/reports/${row.appeal_report_id}`)">
            查看报告
          </el-button>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该记录？" @confirm="remove(row.id)">
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

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑远程检测' : '新增远程检测'" width="560px">
    <el-form :model="form" label-width="100px">
      <el-form-item label="标题" required>
        <el-input v-model="form.title" placeholder="检测任务标题" />
      </el-form-item>
      <el-form-item label="系统名称">
        <el-input v-model="form.system_name" />
      </el-form-item>
      <el-form-item label="检测时间">
        <el-date-picker v-model="form.test_time" type="date" value-format="YYYY-MM-DD" class="!w-full" />
      </el-form-item>
      <el-form-item label="所属部门">
        <el-input v-model="form.department" />
      </el-form-item>
      <el-form-item label="申诉成功">
        <el-switch v-model="form.appeal_success" />
      </el-form-item>
      <el-form-item label="申诉报告">
        <el-select v-model="form.appeal_report_id" filterable clearable placeholder="对应申诉报告（可选）" class="w-full">
          <el-option v-for="r in reports" :key="r.id" :label="r.title" :value="r.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!form.title" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'

const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const sort = reactive<{ prop: string; order: string }>({ prop: '', order: '' })
const loading = ref(false)
const dialogVisible = ref(false)
const reports = ref<any[]>([])

const emptyForm = () => ({
  id: null as number | null,
  title: '',
  system_name: '',
  test_time: '',
  department: '',
  appeal_success: false,
  appeal_report_id: null as number | null,
})
const form = ref(emptyForm())

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/remote-testings', { params: { search: search.value, page: p, size: 20, sort: sort.prop, order: sort.order } })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSortChange({ prop, order }: any) {
  sort.prop = order ? prop : ''
  sort.order = order === 'ascending' ? 'asc' : order === 'descending' ? 'desc' : ''
  load(1)
}

async function openDialog(row?: any) {
  form.value = row ? { ...emptyForm(), ...row } : emptyForm()
  dialogVisible.value = true
  if (!reports.value.length) {
    const { data } = await client.get('/reports', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
    reports.value = data.items
  }
}

async function save() {
  const body = { ...form.value, test_time: form.value.test_time || '' }
  if (form.value.id) {
    await client.put(`/remote-testings/${form.value.id}`, body)
  } else {
    await client.post('/remote-testings', body)
  }
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await load()
}

async function remove(id: number) {
  await client.delete(`/remote-testings/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(() => load(1))
</script>
