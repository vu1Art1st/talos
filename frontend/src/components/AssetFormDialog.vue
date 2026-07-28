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
          <el-input v-model="form.department" placeholder="例如：电商事业部" />
        </el-form-item>
        <el-form-item label="安全等级">
          <el-select v-model="form.sec_level" class="w-full">
            <el-option v-for="(name, code) in meta?.asset_sec_level" :key="code" :label="name" :value="Number(code)" />
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

      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="开放端口">
          <el-select v-model="form.ports" multiple filterable allow-create default-first-option
                     :reserve-keyword="false" placeholder="输入后回车添加，例如 443" class="w-full" />
        </el-form-item>
        <el-form-item label="对应服务">
          <el-input v-model="form.services" placeholder="例如：Web服务 / API网关" />
        </el-form-item>
        <el-form-item label="中间件类型">
          <el-input v-model="form.middleware" placeholder="例如：Nginx / Tomcat" />
        </el-form-item>
        <el-form-item label="数据库类型">
          <el-input v-model="form.database_type" placeholder="例如：MySQL / Redis" />
        </el-form-item>
      </div>

      <el-form-item label="系统负责人">
        <div class="w-full space-y-2">
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
import { onMounted, reactive, ref } from 'vue'
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

const emptyForm = () => ({
  id: null, name: '', sub_system: '', department: '',
  public_urls: [] as any[], internal_urls: [] as string[], ports: [] as string[],
  services: '', middleware: '', database_type: '',
  owners: [] as any[], sec_level: 40, status: 10, remark: '',
})
const form = reactive<any>(emptyForm())

function onOpen() {
  Object.assign(form, emptyForm(), JSON.parse(JSON.stringify(props.asset ?? {})))
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写系统命名')
  form.public_urls = form.public_urls.filter((u: any) => u.url.trim())
  form.owners = form.owners.filter((o: any) => o.name.trim())
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
})
</script>
