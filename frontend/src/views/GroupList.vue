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
      <el-table-column type="index" label="序号" width="80" />
      <el-table-column prop="name" label="组织名称" min-width="160" sortable />
      <el-table-column label="成员数" width="100">
        <template #default="{ row }">{{ row.member_count ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="备注" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>
      <el-table-column v-if="auth.hasPerm('user:manage')" label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openMembers(row)">人员录入</el-button>
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该组织？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无组织，点击「新建组织」创建" :image-size="80" />
      </template>
    </el-table>
  </el-card>

  <!-- 组织编辑 -->
  <el-dialog
             :close-on-click-modal="false" v-model="dialogVisible" :title="form.id ? '编辑组织' : '新建组织'" width="480px">
    <el-form :model="form" label-width="90px">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" placeholder="请输入组织名称" maxlength="64" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="选填" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <!-- 人员录入 -->
  <el-dialog
             :close-on-click-modal="false" v-model="memberDialogVisible" :title="`人员录入 - ${memberGroupName}`" width="640px">
    <div class="flex items-center gap-2 mb-3">
      <span class="text-gray-400 text-sm">组织成员将作为资产「系统负责人」的可选项</span>
      <div class="flex-1" />
      <el-button type="primary" size="small" @click="openMemberForm()">
        <el-icon class="mr-1"><Plus /></el-icon>录入人员
      </el-button>
    </div>
    <el-table v-loading="membersLoading" :data="members" stripe size="small">
      <el-table-column type="index" label="序号" width="70" />
      <el-table-column prop="name" label="姓名" min-width="120" />
      <el-table-column prop="phone" label="电话" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.phone || '-' }}</template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.email || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openMemberForm(row)">编辑</el-button>
          <el-popconfirm title="确认删除该成员？" @confirm="removeMember(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无成员，点击「录入人员」添加" :image-size="80" />
      </template>
    </el-table>
  </el-dialog>

  <!-- 成员编辑 -->
  <el-dialog
             :close-on-click-modal="false" v-model="memberFormVisible" :title="memberForm.id ? '编辑人员' : '录入人员'" width="480px">
    <el-form :model="memberForm" label-width="90px">
      <el-form-item label="姓名" required>
        <el-input v-model="memberForm.name" placeholder="请输入姓名" maxlength="64" />
      </el-form-item>
      <el-form-item label="电话">
        <el-input v-model="memberForm.phone" placeholder="联系电话（选填）" maxlength="32" />
      </el-form-item>
      <el-form-item label="邮箱">
        <el-input v-model="memberForm.email" placeholder="邮箱（选填）" maxlength="128" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="memberFormVisible = false">取消</el-button>
      <el-button type="primary" :loading="memberSaving" @click="saveMember">保存</el-button>
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

// 人员管理
const memberDialogVisible = ref(false)
const memberGroupId = ref(0)
const memberGroupName = ref('')
const members = ref<any[]>([])
const membersLoading = ref(false)
const memberFormVisible = ref(false)
const memberSaving = ref(false)
const memberForm = reactive({ id: 0, name: '', phone: '', email: '' })

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/groups')
    // 成员数由前端聚合全部成员统计（组织列表仅展示用）
    const { data: allMembers } = await client.get('/group-members/all')
    const countMap = new Map<number, number>()
    for (const m of allMembers) countMap.set(m.group_id, (countMap.get(m.group_id) ?? 0) + 1)
    items.value = data.map((g: any) => ({ ...g, member_count: countMap.get(g.id) ?? 0 }))
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
  const body = { name: form.name, remark: form.remark }
  saving.value = true
  try {
    if (form.id) {
      await client.put(`/groups/${form.id}`, body)
    } else {
      await client.post('/groups', body)
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

// ---------- 人员管理 ----------
async function loadMembers(groupId: number) {
  membersLoading.value = true
  try {
    const { data } = await client.get(`/groups/${groupId}/members`)
    members.value = data
  } finally {
    membersLoading.value = false
  }
}

function openMembers(row: any) {
  memberGroupId.value = row.id
  memberGroupName.value = row.name
  memberDialogVisible.value = true
  loadMembers(row.id)
}

function openMemberForm(row?: any) {
  memberForm.id = row?.id ?? 0
  memberForm.name = row?.name ?? ''
  memberForm.phone = row?.phone ?? ''
  memberForm.email = row?.email ?? ''
  memberFormVisible.value = true
}

async function saveMember() {
  if (!memberForm.name.trim()) return ElMessage.warning('请输入姓名')
  const body = { name: memberForm.name, phone: memberForm.phone, email: memberForm.email }
  memberSaving.value = true
  try {
    if (memberForm.id) {
      await client.put(`/groups/${memberGroupId.value}/members/${memberForm.id}`, body)
    } else {
      await client.post(`/groups/${memberGroupId.value}/members`, body)
    }
    ElMessage.success('保存成功')
    memberFormVisible.value = false
    await loadMembers(memberGroupId.value)
    await load()
  } finally {
    memberSaving.value = false
  }
}

async function removeMember(id: number) {
  await client.delete(`/groups/${memberGroupId.value}/members/${id}`)
  ElMessage.success('删除成功')
  await loadMembers(memberGroupId.value)
  await load()
}

onMounted(load)
</script>
