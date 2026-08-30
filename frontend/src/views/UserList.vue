<template>
  <el-card shadow="never">
    <div class="flex items-center flex-wrap gap-2 mb-3">
      <div class="tl-search-field">
        <el-input v-model="search" placeholder="搜索用户名 / 姓名" clearable
                  @keyup.enter="load(1)" @clear="load(1)">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <div class="flex-1" />
      <el-button type="primary" class="btn-min" @click="openUser()">
        <el-icon class="mr-1"><Plus /></el-icon>新建用户
      </el-button>
    </div>

    <el-table v-loading="loading" :data="users" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="64"
                       :index="(i: number) => (page - 1) * size + i + 1" />
      <el-table-column prop="username" label="用户名" width="140" sortable="custom" />
      <el-table-column prop="realname" label="姓名" width="120" sortable="custom" />
      <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="role_name" label="角色" width="130" show-overflow-tooltip />
      <el-table-column prop="is_active" label="状态" width="90" sortable="custom">
        <template #default="{ row }">
          <span class="dot-tag" :style="dotStyle(row.is_active ? STAT_CARD_COLORS.green : STAT_CARD_COLORS.red)">
            <i></i>{{ row.is_active ? '正常' : '禁用' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openPerm(row)">查看权限</el-button>
          <el-button size="small" type="primary" link @click="openUser(row)">编辑</el-button>
          <el-popconfirm title="确认删除该用户？" @confirm="removeUser(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无用户，点击「新建用户」创建" :image-size="80" />
      </template>
    </el-table>

    <TlPagination v-model:page="page" v-model:size="size" :total="total"
                  @page-change="load" @size-change="onSizeChange" />
  </el-card>

  <el-dialog
             :close-on-click-modal="false" v-model="userDialog" :title="userForm.id ? '编辑用户' : '新建用户'" width="480px">
    <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-width="90px">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="userForm.username" :disabled="!!userForm.id" />
      </el-form-item>
      <el-form-item :label="userForm.id ? '重置密码' : '密码'">
        <el-input v-model="userForm.password" type="password" show-password
                  :placeholder="userForm.id ? '留空表示不修改' : ''" />
      </el-form-item>
      <el-form-item label="姓名">
        <el-input v-model="userForm.realname" />
      </el-form-item>
      <el-form-item label="邮箱">
        <el-input v-model="userForm.email" />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="userForm.role_id" clearable class="w-full" placeholder="未分配角色">
          <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-switch v-model="userForm.is_active" active-text="正常" inactive-text="禁用" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="userDialog = false">取消</el-button>
      <el-button type="primary" :loading="userSaving" @click="saveUser">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog
             :close-on-click-modal="false" v-model="permDialog"
             :title="`权限查看 - ${permUser?.username || ''}`" width="640px">
    <div v-loading="catalogLoading" class="min-h-24">
      <el-alert v-if="permUser?.permissions?.includes('*')" type="warning" :closable="false" show-icon class="mb-3"
                title="该用户角色拥有全部权限（*）" />
      <div v-for="g in catalog" :key="g.group" class="mb-4 last:mb-0">
        <div class="text-sm font-semibold mb-2" style="color: var(--tl-text-2)">{{ g.group }}</div>
        <div class="flex flex-wrap gap-2">
          <el-tooltip v-for="it in g.items" :key="it.key" :content="it.desc" placement="top">
            <span class="tl-tag"
                  :style="userHasPerm(permUser, it.key) ? softStyle(STAT_CARD_COLORS.blue) : softStyle(STAT_CARD_COLORS.gray)">
              {{ it.label }}
            </span>
          </el-tooltip>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button type="primary" @click="permDialog = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import client from '../api/client'
import { useListPage } from '../composables/useListPage'
import { dotStyle, softStyle, STAT_CARD_COLORS } from '../utils/colors'
import TlPagination from '../components/TlPagination.vue'

interface PermItem { key: string; label: string; desc: string }
interface PermGroup { group: string; items: PermItem[] }

const { items: users, total, page, size, search, loading, load, onSortChange, onSizeChange } = useListPage('/users')

const roles = ref<any[]>([])
const catalog = ref<PermGroup[]>([])
const catalogLoading = ref(false)
const userDialog = ref(false)
const permDialog = ref(false)
const permUser = ref<any>(null)
const userSaving = ref(false)
const userForm = reactive<any>({ id: null, username: '', password: '', realname: '', email: '', role_id: null, is_active: true })
const userFormRef = ref<FormInstance>()
const userRules: FormRules = {
  username: [{ required: true, whitespace: true, message: '请填写用户名', trigger: 'blur' }],
}

async function loadRoles() {
  const { data } = await client.get('/roles')
  roles.value = data
}

async function loadCatalog() {
  catalogLoading.value = true
  try {
    const { data } = await client.get('/roles/permissions/catalog')
    catalog.value = data
  } finally {
    catalogLoading.value = false
  }
}

function openUser(row?: any) {
  Object.assign(userForm, row
    ? { ...row, password: '' }
    : { id: null, username: '', password: '', realname: '', email: '', role_id: null, is_active: true })
  userDialog.value = true
}

async function saveUser() {
  const valid = await userFormRef.value.validate().catch(() => false)
  if (!valid) return
  userSaving.value = true
  try {
    const body = { ...userForm, password: userForm.password || null }
    if (userForm.id) await client.put(`/users/${userForm.id}`, body)
    else await client.post('/users', body)
    ElMessage.success('保存成功')
    userDialog.value = false
    await load()
  } finally {
    userSaving.value = false
  }
}

async function removeUser(id: number) {
  await client.delete(`/users/${id}`)
  ElMessage.success('删除成功')
  await load()
}

function userHasPerm(user: any, key: string) {
  const perms = user?.permissions ?? []
  return perms.includes('*') || perms.includes(key)
}

function openPerm(row: any) {
  permUser.value = row
  permDialog.value = true
  if (!catalog.value.length) loadCatalog()
}

onMounted(async () => {
  await Promise.all([load(1), loadRoles(), loadCatalog()])
})
</script>
