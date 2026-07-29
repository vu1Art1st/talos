<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <span class="text-gray-400 text-sm">组织（组）用于资产归属与用户分组管理</span>
      <div class="flex-1" />
      <el-button v-if="auth.hasPerm('user:manage')" type="primary" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新建组织
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="组织名称" min-width="200" />
      <el-table-column label="备注" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>
      <el-table-column v-if="auth.hasPerm('user:manage')" label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该组织？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑组织' : '新建组织'" width="440px">
    <el-form :model="form" label-width="80px">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" placeholder="请输入组织名称" maxlength="64" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="选填" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const items = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const form = reactive({ id: 0, name: '', remark: '' })

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/groups')
    items.value = data
  } finally {
    loading.value = false
  }
}

function openDialog(row?: any) {
  form.id = row?.id ?? 0
  form.name = row?.name ?? ''
  form.remark = row?.remark ?? ''
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请输入组织名称')
  saving.value = true
  try {
    if (form.id) {
      await client.put(`/groups/${form.id}`, { name: form.name, remark: form.remark })
    } else {
      await client.post('/groups', { name: form.name, remark: form.remark })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(id: number) {
  await client.delete(`/groups/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(load)
</script>
