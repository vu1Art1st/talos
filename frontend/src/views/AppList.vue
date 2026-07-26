<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索应用名称 / URL" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button type="primary" @click="openEdit()">
        <el-icon class="mr-1"><Plus /></el-icon>新建应用
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="应用名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="url" label="URL" min-width="200" show-overflow-tooltip />
      <el-table-column label="类型" width="110">
        <template #default="{ row }">{{ meta?.app_type?.[row.app_type] ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="安全等级" width="100">
        <template #default="{ row }">{{ meta?.app_sec_level?.[row.sec_level] ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 10 ? 'success' : 'info'" size="small">
            {{ meta?.app_status?.[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确认删除该应用？" @confirm="remove(row.id)">
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

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑应用' : '新建应用'" width="520px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="URL">
        <el-input v-model="form.url" />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="form.app_type" class="w-full">
          <el-option v-for="(name, code) in meta?.app_type" :key="code" :label="name" :value="Number(code)" />
        </el-select>
      </el-form-item>
      <el-form-item label="安全等级">
        <el-select v-model="form.sec_level" class="w-full">
          <el-option v-for="(name, code) in meta?.app_sec_level" :key="code" :label="name" :value="Number(code)" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status" class="w-full">
          <el-option v-for="(name, code) in meta?.app_status" :key="code" :label="name" :value="Number(code)" />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const meta = ref<any>(null)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const loading = ref(false)
const dialogVisible = ref(false)
const form = reactive<any>({ id: null, name: '', url: '', app_type: 20, sec_level: 40, status: 10, remark: '' })

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/apps', { params: { search: search.value, page: p, size: 20 } })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function openEdit(row?: any) {
  Object.assign(form, row ?? { id: null, name: '', url: '', app_type: 20, sec_level: 40, status: 10, remark: '' })
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写应用名称')
  if (form.id) await client.put(`/apps/${form.id}`, form)
  else await client.post('/apps', form)
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await load()
}

async function remove(id: number) {
  await client.delete(`/apps/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load(1)
})
</script>
