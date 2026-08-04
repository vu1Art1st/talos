<template>
  <el-dialog :model-value="visible" :title="form.id ? '编辑资产' : '新建资产'" width="680px"
             @update:model-value="emit('update:visible', $event)" @open="onOpen">
    <el-form :model="form" label-width="100px">
      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="系统命名" required>
          <el-input v-model="form.name" placeholder="例如：电商交易系统" />
        </el-form-item>
        <el-form-item label="子系统名称">
          <el-input v-model="form.sub_system" placeholder="例如：订单中心（可选）" />
        </el-form-item>
        <el-form-item label="部门">
          <el-select v-model="form.department" filterable allow-create default-first-option clearable
                     placeholder="选择部门，或输入后回车新增" class="w-full">
            <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="系统类型">
          <el-select v-model="form.system_type" filterable allow-create default-first-option clearable
                     placeholder="选择或输入新类型" class="w-full">
            <el-option v-for="name in (meta?.system_type ?? [])" :key="name" :label="name" :value="name" />
          </el-select>
        </el-form-item>
      </div>

      <el-form-item label="公网URL">
        <div class="w-full space-y-2">
          <div v-for="(item, i) in form.public_urls" :key="i" class="flex gap-2">
            <el-input v-model="item.url" placeholder="https://..." class="flex-1" />
            <el-select v-model="item.tag" class="!w-28">
              <el-option v-for="(name, code) in meta?.url_tag" :key="code" :label="name" :value="Number(code)" />
            </el-select>
            <el-button type="danger" link @click="form.public_urls.splice(i, 1)">删除</el-button>
          </div>
          <el-button size="small" @click="form.public_urls.push({ url: '', tag: 10 })">
            <el-icon class="mr-1"><Plus /></el-icon>添加公网URL
          </el-button>
        </div>
      </el-form-item>

      <el-form-item label="内网URL">
        <el-select v-model="form.internal_urls" multiple filterable allow-create default-first-option
                   :reserve-keyword="false" placeholder="输入后回车添加，例如 http://10.0.0.8:8080" class="w-full" />
      </el-form-item>

      <el-form-item label="端口与服务">
        <div class="w-full space-y-2">
          <div v-for="(item, i) in form.port_services" :key="i" class="flex items-center gap-2">
            <el-input v-model="item.port" placeholder="端口，例如 443" class="!w-36" />
            <span class="text-gray-400">:</span>
            <el-input v-model="item.service" placeholder="服务，例如 HTTPS / Web服务" class="flex-1" />
            <el-button type="danger" link @click="form.port_services.splice(i, 1)">删除</el-button>
          </div>
          <el-button size="small" @click="form.port_services.push({ port: '', service: '' })">
            <el-icon class="mr-1"><Plus /></el-icon>新增
          </el-button>
        </div>
      </el-form-item>

      <el-form-item label="中间件">
        <div class="w-full space-y-2">
          <div v-for="(item, i) in form.middlewares" :key="i" class="flex gap-2">
            <el-input v-model="item.name" placeholder="名称，例如 Nginx" class="flex-1" />
            <el-input v-model="item.version" placeholder="版本号，例如 1.24" class="!w-40" />
            <el-button type="danger" link @click="form.middlewares.splice(i, 1)">删除</el-button>
          </div>
          <el-button size="small" @click="form.middlewares.push({ name: '', version: '' })">
            <el-icon class="mr-1"><Plus /></el-icon>新增
          </el-button>
        </div>
      </el-form-item>

      <el-form-item label="数据库">
        <div class="w-full space-y-2">
          <div v-for="(item, i) in form.databases" :key="i" class="flex gap-2">
            <el-input v-model="item.name" placeholder="名称，例如 MySQL" class="flex-1" />
            <el-input v-model="item.version" placeholder="版本号，例如 8.0" class="!w-40" />
            <el-button type="danger" link @click="form.databases.splice(i, 1)">删除</el-button>
          </div>
          <el-button size="small" @click="form.databases.push({ name: '', version: '' })">
            <el-icon class="mr-1"><Plus /></el-icon>新增
          </el-button>
        </div>
      </el-form-item>

      <el-form-item label="系统负责人">
        <div class="w-full space-y-2">
          <el-select v-if="memberOptions.length" :model-value="undefined" filterable
                     placeholder="从组织成员中选择添加，或下方直接录入" class="w-full" @change="pickMember">
            <el-option v-for="(o, i) in memberOptions" :key="i" :value="i"
                       :label="`${o.name}（${o.group}）`">
              <div class="flex justify-between gap-4">
                <span>{{ o.name }}<span class="text-xs text-gray-400 ml-1">{{ o.group }}</span></span>
                <span class="text-xs text-gray-400">{{ [o.phone, o.email].filter(Boolean).join(' / ') }}</span>
              </div>
            </el-option>
          </el-select>
          <div v-for="(owner, i) in form.owners" :key="i" class="flex gap-2">
            <el-input v-model="owner.name" placeholder="姓名" class="!w-28" />
            <el-input v-model="owner.phone" placeholder="联系方式" class="flex-1" />
            <el-input v-model="owner.email" placeholder="邮箱" class="flex-1" />
            <el-button type="danger" link @click="form.owners.splice(i, 1)">删除</el-button>
          </div>
          <el-button size="small" @click="form.owners.push({ name: '', phone: '', email: '' })">
            <el-icon class="mr-1"><Plus /></el-icon>添加负责人
          </el-button>
        </div>
      </el-form-item>

      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="状态">
          <el-select v-model="form.status" class="w-full">
            <el-option v-for="(name, code) in meta?.asset_status" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="1" />
        </el-form-item>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{
  visible: boolean
  /** 编辑时传入资产对象；新建传 null。name 字段可预填搜索关键字 */
  asset?: any | null
}>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'saved', asset: any): void
}>()

const auth = useAuthStore()
const meta = ref<any>(null)
const saving = ref(false)
const groups = ref<any[]>([])
const members = ref<any[]>([])

// 组织成员（含所属组织名），供资产系统负责人下拉选择快速添加
const memberOptions = computed(() =>
  members.value.map((m) => ({
    name: m.name, phone: m.phone ?? '', email: m.email ?? '',
    group: groups.value.find((g) => g.id === m.group_id)?.name ?? '',
  })))

const emptyForm = () => ({
  id: null, name: '', sub_system: '', department: '', system_type: '',
  public_urls: [] as any[], internal_urls: [] as string[],
  port_services: [] as any[], middlewares: [] as any[], databases: [] as any[],
  owners: [] as any[], status: 10, remark: '',
})
const form = reactive<any>(emptyForm())

function onOpen() {
  Object.assign(form, emptyForm(), JSON.parse(JSON.stringify(props.asset ?? {})))
  loadGroups()
  loadMembers()
}

async function loadGroups() {
  const { data } = await client.get('/groups')
  groups.value = data
}

async function loadMembers() {
  const { data } = await client.get('/group-members/all')
  members.value = data
}

function pickMember(idx: number) {
  const o = memberOptions.value[idx]
  if (!o) return
  if (form.owners.some((x: any) => x.name === o.name && x.phone === o.phone)) {
    return ElMessage.info('该负责人已添加')
  }
  form.owners.push({ name: o.name, phone: o.phone, email: o.email })
}

async function persistSystemType() {
  // 新录入的系统类型持久化到字典，供后续复用（无权限时仅保存到资产）
  const name = (form.system_type ?? '').trim()
  if (!name || (meta.value?.system_type ?? []).includes(name)) return
  try {
    await client.post('/dict/system_type', { name, sort: 999 })
    if (auth.meta?.system_type) auth.meta.system_type.push(name)
  } catch {
    /* 权限不足时静默，资产仍保存该类型 */
  }
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写系统命名')
  form.public_urls = form.public_urls.filter((u: any) => u.url.trim())
  form.port_services = form.port_services.filter((p: any) => (p.port ?? '').trim() || (p.service ?? '').trim())
  form.middlewares = form.middlewares.filter((m: any) => (m.name ?? '').trim())
  form.databases = form.databases.filter((d: any) => (d.name ?? '').trim())
  form.owners = form.owners.filter((o: any) => o.name.trim())
  await persistSystemType()
  saving.value = true
  try {
    const { data } = form.id
      ? await client.put(`/assets/${form.id}`, form)
      : await client.post('/assets', form)
    ElMessage.success('保存成功')
    emit('update:visible', false)
    emit('saved', data)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await loadGroups()
  await loadMembers()
})
</script>
