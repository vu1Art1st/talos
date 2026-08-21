<template>
  <div class="space-y-4">
    <el-card shadow="never" class="!rounded-lg">
      <template #header>
        <div class="flex items-center justify-between">
          <span>用户管理</span>
          <el-button type="primary" size="small" @click="openUser()">
            <el-icon class="mr-1"><Plus /></el-icon>新建用户
          </el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="users" stripe @sort-change="onSortChange">
        <el-table-column type="index" label="序号" width="70"
                         :index="(i: number) => (page - 1) * 20 + i + 1" />
        <el-table-column prop="username" label="用户名" width="140" sortable="custom" />
        <el-table-column prop="realname" label="姓名" width="120" sortable="custom" />
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip sortable="custom" />
        <el-table-column prop="role_name" label="角色" width="130" />
        <el-table-column prop="is_active" label="状态" width="90" sortable="custom">
          <template #default="{ row }">
            <span class="tl-tag" :style="row.is_active ? softStyle(STAT_CARD_COLORS.green) : softStyle(STAT_CARD_COLORS.red)">
              {{ row.is_active ? '正常' : '禁用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
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
      <div class="flex justify-end mt-4">
        <el-pagination background layout="total, prev, pager, next" :total="total"
                       :page-size="20" :current-page="page" @current-change="loadUsers" />
      </div>
    </el-card>

    <el-card shadow="never" class="!rounded-lg">
      <template #header>
        <div class="flex items-center justify-between">
          <span>角色与权限</span>
          <el-button type="primary" size="small" @click="openRole()">
            <el-icon class="mr-1"><Plus /></el-icon>新建角色
          </el-button>
        </div>
      </template>
      <el-table v-loading="rolesLoading" :data="roles" stripe>
        <el-table-column prop="name" label="角色名称" width="160" />
        <el-table-column label="权限">
          <template #default="{ row }">
            <span v-if="row.permissions.includes('*')" class="tl-tag mr-1" :style="softStyle(STAT_CARD_COLORS.red)">全部权限</span>
            <span v-for="p in row.permissions.filter((x: string) => x !== '*')" :key="p"
                  class="tl-tag mr-1 mb-1" :style="softStyle(STAT_CARD_COLORS.blue)">{{ p }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openRole(row)">编辑</el-button>
            <el-popconfirm title="确认删除该角色？" @confirm="removeRole(row.id)">
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无角色，点击「新建角色」创建" :image-size="80" />
        </template>
      </el-table>
    </el-card>
  </div>

  <el-dialog
             :close-on-click-modal="false" v-model="userDialog" :title="userForm.id ? '编辑用户' : '新建用户'" width="480px">
    <el-form :model="userForm" label-width="90px">
      <el-form-item label="用户名" required>
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
        <el-select v-model="userForm.role_id" class="w-full">
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
             :close-on-click-modal="false" v-model="roleDialog" :title="roleForm.id ? '编辑角色' : '新建角色'" width="480px">
    <el-form :model="roleForm" label-width="90px">
      <el-form-item label="角色名称" required>
        <el-input v-model="roleForm.name" />
      </el-form-item>
      <el-form-item label="权限">
        <el-checkbox-group v-model="roleForm.permissions">
          <el-checkbox v-for="p in allPerms" :key="p" :value="p" class="!mr-4">{{ p }}</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="roleForm.remark" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="roleDialog = false">取消</el-button>
      <el-button type="primary" :loading="roleSaving" @click="saveRole">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import { useListPage } from '../composables/useListPage'
import { softStyle, STAT_CARD_COLORS } from '../utils/colors'

const { items: users, total, page, loading, load: loadUsers, onSortChange } = useListPage('/users')
const roles = ref<any[]>([])
const allPerms = ref<string[]>([])
const rolesLoading = ref(false)
const userDialog = ref(false)
const roleDialog = ref(false)
const userSaving = ref(false)
const roleSaving = ref(false)
const userForm = reactive<any>({ id: null, username: '', password: '', realname: '', email: '', role_id: null, is_active: true })
const roleForm = reactive<any>({ id: null, name: '', permissions: [], remark: '' })

async function loadRoles() {
  rolesLoading.value = true
  try {
    const [r, p] = await Promise.all([client.get('/roles'), client.get('/roles/permissions')])
    roles.value = r.data
    allPerms.value = p.data
  } finally {
    rolesLoading.value = false
  }
}

function openUser(row?: any) {
  Object.assign(userForm, row
    ? { ...row, password: '' }
    : { id: null, username: '', password: '', realname: '', email: '', role_id: null, is_active: true })
  userDialog.value = true
}

async function saveUser() {
  if (!userForm.username.trim()) return ElMessage.warning('请填写用户名')
  userSaving.value = true
  try {
    const body = { ...userForm, password: userForm.password || null }
    if (userForm.id) await client.put(`/users/${userForm.id}`, body)
    else await client.post('/users', body)
    ElMessage.success('保存成功')
    userDialog.value = false
    await loadUsers()
  } finally {
    userSaving.value = false
  }
}

async function removeUser(id: number) {
  await client.delete(`/users/${id}`)
  ElMessage.success('删除成功')
  await loadUsers()
}

function openRole(row?: any) {
  Object.assign(roleForm, row
    ? { ...row, permissions: [...row.permissions] }
    : { id: null, name: '', permissions: [], remark: '' })
  roleDialog.value = true
}

async function saveRole() {
  if (!roleForm.name.trim()) return ElMessage.warning('请填写角色名称')
  roleSaving.value = true
  try {
    if (roleForm.id) await client.put(`/roles/${roleForm.id}`, roleForm)
    else await client.post('/roles', roleForm)
    ElMessage.success('保存成功')
    roleDialog.value = false
    await loadRoles()
  } finally {
    roleSaving.value = false
  }
}

async function removeRole(id: number) {
  await client.delete(`/roles/${id}`)
  ElMessage.success('删除成功')
  await loadRoles()
}

onMounted(async () => {
  await Promise.all([loadUsers(1), loadRoles()])
})
</script>
