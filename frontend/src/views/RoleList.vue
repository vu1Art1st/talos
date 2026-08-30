<template>
  <el-card shadow="never">
    <div class="flex items-center gap-2 mb-4">
      <span class="text-gray-400 text-sm">基于角色的权限配置，权限按功能模块分组，控制菜单显示与操作范围</span>
      <div class="flex-1" />
      <el-button type="primary" class="btn-min" @click="openRole()">
        <el-icon class="mr-1"><Plus /></el-icon>新建角色
      </el-button>
    </div>

    <el-table v-loading="loading" :data="roles" stripe>
      <el-table-column type="index" label="序号" width="64" />
      <el-table-column prop="name" label="角色名称" width="160" show-overflow-tooltip />
      <el-table-column label="权限" min-width="300">
        <template #default="{ row }">
          <template v-if="row.permissions.includes('*')">
            <span class="tl-tag" :style="softStyle(STAT_CARD_COLORS.red)">全部权限</span>
          </template>
          <template v-else-if="row.permissions.length">
            <span v-for="p in permLabels(row.permissions).slice(0, 3)" :key="p"
                  class="tl-tag mr-1" :style="softStyle(STAT_CARD_COLORS.blue)">{{ p }}</span>
            <el-popover v-if="row.permissions.length > 3" placement="left" :width="280" trigger="hover">
              <template #reference>
                <el-button size="small" type="primary" link class="!p-0">+{{ row.permissions.length - 3 }}</el-button>
              </template>
              <div class="flex flex-wrap gap-1">
                <span v-for="p in permLabels(row.permissions)" :key="p"
                      class="tl-tag" :style="softStyle(STAT_CARD_COLORS.blue)">{{ p }}</span>
              </div>
            </el-popover>
          </template>
          <span v-else class="text-gray-400">未分配权限</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="120" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openRole(row)">配置权限</el-button>
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

  <el-dialog
             :close-on-click-modal="false" v-model="roleDialog" :title="roleForm.id ? '编辑角色' : '新建角色'" width="640px">
    <el-form ref="roleFormRef" :model="roleForm" :rules="roleRules" label-width="90px">
      <el-form-item label="角色名称" prop="name">
        <el-input v-model="roleForm.name" maxlength="64" />
      </el-form-item>
      <el-form-item label="权限配置">
        <div class="w-full">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs text-gray-400">勾选该角色可访问的菜单与操作权限</span>
            <div>
              <el-button size="small" text type="primary" @click="checkAll">全选</el-button>
              <el-button size="small" text @click="clearAll">清空</el-button>
            </div>
          </div>
          <div v-loading="catalogLoading" class="border rounded-lg p-3 max-h-72 overflow-auto"
               style="border-color: var(--tl-border)">
            <div v-for="g in catalog" :key="g.group" class="mb-3 last:mb-0">
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-semibold" style="color: var(--tl-text-2)">{{ g.group }}</span>
                <el-checkbox :model-value="groupChecked(g)" :indeterminate="groupIndeterminate(g)"
                             @change="(val: any) => toggleGroup(g, val)">全选本组</el-checkbox>
              </div>
              <el-checkbox-group v-model="roleForm.permissions" class="flex flex-wrap gap-x-4 gap-y-1">
                <el-checkbox v-for="it in g.items" :key="it.key" :value="it.key">
                  {{ it.label }}
                  <el-tooltip :content="it.desc" placement="top">
                    <el-icon class="text-gray-400 align-middle ml-0.5" style="font-size: 13px"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </el-checkbox>
              </el-checkbox-group>
            </div>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="roleForm.remark" type="textarea" :rows="2" maxlength="255" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="roleDialog = false">取消</el-button>
      <el-button type="primary" :loading="roleSaving" @click="saveRole">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import client from '../api/client'
import { softStyle, STAT_CARD_COLORS } from '../utils/colors'

interface PermItem { key: string; label: string; desc: string }
interface PermGroup { group: string; items: PermItem[] }

const roles = ref<any[]>([])
const loading = ref(false)
const catalog = ref<PermGroup[]>([])
const catalogLoading = ref(false)
const roleDialog = ref(false)
const roleSaving = ref(false)
const roleForm = reactive<any>({ id: null, name: '', permissions: [] as string[], remark: '' })
const roleFormRef = ref<FormInstance>()
const roleRules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请填写角色名称', trigger: 'blur' }],
}

const allKeys = computed(() => catalog.value.flatMap((g) => g.items.map((it) => it.key)))
const labelMap = computed(() => {
  const m = new Map<string, string>()
  for (const g of catalog.value) for (const it of g.items) m.set(it.key, it.label)
  return m
})

async function loadRoles() {
  loading.value = true
  try {
    const { data } = await client.get('/roles')
    roles.value = data
  } finally {
    loading.value = false
  }
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

function permLabels(perms: string[]) {
  return perms.filter((p) => p !== '*').map((p) => labelMap.value.get(p) || p)
}

function groupChecked(g: PermGroup) {
  const keys = g.items.map((it) => it.key)
  return keys.length > 0 && keys.every((k) => roleForm.permissions.includes(k))
}

function groupIndeterminate(g: PermGroup) {
  const keys = g.items.map((it) => it.key)
  return keys.some((k) => roleForm.permissions.includes(k)) && !groupChecked(g)
}

function toggleGroup(g: PermGroup, checked: boolean) {
  const keys = g.items.map((it) => it.key)
  if (checked) {
    roleForm.permissions = Array.from(new Set([...roleForm.permissions, ...keys]))
  } else {
    roleForm.permissions = roleForm.permissions.filter((k) => !keys.includes(k))
  }
}

function checkAll() {
  roleForm.permissions = [...allKeys.value]
}

function clearAll() {
  roleForm.permissions = []
}

function openRole(row?: any) {
  Object.assign(roleForm, row
    ? { id: row.id, name: row.name, permissions: [...row.permissions], remark: row.remark }
    : { id: null, name: '', permissions: [], remark: '' })
  roleDialog.value = true
}

async function saveRole() {
  const valid = await roleFormRef.value.validate().catch(() => false)
  if (!valid) return
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
  await Promise.all([loadRoles(), loadCatalog()])
})
</script>
