<template>
  <el-card shadow="never" class="!rounded-lg max-w-5xl">
    <el-form :model="form" label-width="90px">
      <el-form-item label="漏洞名称" required>
        <el-input v-model="form.title" placeholder="例如：后台登录接口存在SQL注入" />
      </el-form-item>
      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="漏洞等级">
          <el-select v-model="form.level" class="w-full">
            <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="漏洞类型">
          <el-select v-model="form.vul_type" filterable class="w-full">
            <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属应用">
          <el-select v-model="form.app_id" filterable clearable class="w-full" placeholder="选择应用">
            <el-option v-for="a in apps" :key="a.id" :label="a.name" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="所在层">
          <el-select v-model="form.layer" class="w-full">
            <el-option v-for="(name, code) in meta?.vul_layer" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
      </div>
      <el-form-item label="影响URL">
        <el-input v-model="form.affected_url" placeholder="https://..." />
      </el-form-item>
      <el-form-item label="漏洞描述">
        <RichEditor v-model="form.description_html" class="w-full"
                    @update:json="(j: any) => (form.description_json = j)" />
      </el-form-item>
      <el-form-item label="复现步骤">
        <RichEditor v-model="form.reproduce_html" class="w-full"
                    @update:json="(j: any) => (form.reproduce_json = j)" />
      </el-form-item>
      <el-form-item label="修复建议">
        <RichEditor v-model="form.solution_html" class="w-full"
                    @update:json="(j: any) => (form.solution_json = j)" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
        <el-button @click="router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import RichEditor from '../components/RichEditor.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const meta = ref<any>(null)
const apps = ref<any[]>([])
const saving = ref(false)
const editId = route.name === 'vuln-edit' ? Number(route.params.id) : null

const form = reactive<any>({
  title: '', level: 30, vul_type: 75, layer: 10, affected_url: '', app_id: null,
  description_html: '', description_json: null,
  reproduce_html: '', reproduce_json: null,
  solution_html: '', solution_json: null,
  source: 10, score: 0, risk_score: 0, left_risk_score: 0, asset_level: 0,
})

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  const { data } = await client.get('/apps', { params: { size: 100 } })
  apps.value = data.items
  if (editId) {
    const { data: vul } = await client.get(`/vulns/${editId}`)
    Object.assign(form, vul)
  }
})

async function save() {
  if (!form.title.trim()) return ElMessage.warning('请填写漏洞名称')
  saving.value = true
  try {
    if (editId) {
      await client.put(`/vulns/${editId}`, form)
      ElMessage.success('保存成功')
      router.push(`/vulns/${editId}`)
    } else {
      const { data } = await client.post('/vulns', form)
      ElMessage.success('漏洞提交成功，等待审核')
      router.push(`/vulns/${data.id}`)
    }
  } finally {
    saving.value = false
  }
}
</script>
