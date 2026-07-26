<template>
  <div class="space-y-4">
    <el-card shadow="never" class="!rounded-lg">
      <div class="flex flex-wrap items-center gap-3">
        <div class="font-medium">批次 #{{ route.params.id }}</div>
        <el-tag v-if="batch" size="small">{{ batch.filename }}</el-tag>
        <div class="flex-1" />
        <el-select v-model="appId" filterable clearable placeholder="入库到应用（可选）" class="!w-52">
          <el-option v-for="a in apps" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
        <el-button type="primary" :disabled="!selected.length" @click="confirm">
          确认入库（{{ selected.length }} 条）
        </el-button>
      </div>
    </el-card>

    <el-card v-for="rec in records" :key="rec.id" shadow="never" class="!rounded-lg"
             :class="{ 'opacity-50': rec.status === 'discarded' }">
      <div class="flex items-center gap-2 mb-3">
        <el-checkbox v-model="checked[rec.id]" :disabled="rec.status !== 'parsed'" />
        <el-tag :type="recTag(rec.status)" size="small">{{ recName(rec.status) }}</el-tag>
        <el-tag v-if="rec.parse_error" type="warning" size="small" effect="plain">{{ rec.parse_error }}</el-tag>
        <div class="flex-1" />
        <el-button v-if="rec.status !== 'confirmed' && rec.status !== 'discarded'" size="small"
                   @click="editing = editing === rec.id ? null : rec.id">
          {{ editing === rec.id ? '收起' : '修正' }}
        </el-button>
        <el-button v-if="rec.status !== 'confirmed' && rec.status !== 'discarded'" size="small" type="danger" plain
                   @click="discard(rec)">丢弃</el-button>
        <el-button v-if="rec.vul_id" size="small" type="success" link
                   @click="router.push(`/vulns/${rec.vul_id}`)">查看漏洞</el-button>
      </div>

      <template v-if="editing === rec.id">
        <el-form label-width="80px" size="small">
          <el-form-item label="漏洞名称">
            <el-input v-model="rec.title" />
          </el-form-item>
          <div class="grid grid-cols-2">
            <el-form-item label="等级">
              <el-select v-model="rec.level" class="w-full">
                <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="rec.vul_type" filterable class="w-full">
                <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="影响URL">
            <el-input v-model="rec.affected_url" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="small" @click="saveRecord(rec)">保存修正</el-button>
          </el-form-item>
        </el-form>
      </template>
      <template v-else>
        <div class="font-semibold text-gray-800">{{ rec.title || '（未识别标题）' }}</div>
        <div class="flex gap-2 mt-1 text-sm text-gray-500">
          <el-tag :type="levelTag(rec.level)" size="small" effect="dark">{{ meta?.vul_level?.[rec.level] }}</el-tag>
          <span>{{ meta?.vul_type?.[rec.vul_type] }}</span>
          <span v-if="rec.affected_url" class="truncate">{{ rec.affected_url }}</span>
        </div>
        <el-collapse class="mt-2">
          <el-collapse-item title="内容预览">
            <div class="rich-content text-sm">
              <h4 v-if="rec.description_html">漏洞描述</h4>
              <div v-html="rec.description_html" />
              <h4 v-if="rec.reproduce_html">复现步骤</h4>
              <div v-html="rec.reproduce_html" />
              <h4 v-if="rec.solution_html">修复建议</h4>
              <div v-html="rec.solution_html" />
            </div>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-card>

    <el-empty v-if="!records.length" description="该批次没有解析出漏洞记录，请检查文档是否符合模板" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const batch = ref<any>(null)
const records = ref<any[]>([])
const apps = ref<any[]>([])
const appId = ref<number | null>(null)
const meta = ref<any>(null)
const editing = ref<number | null>(null)
const checked = reactive<Record<number, boolean>>({})

const selected = computed(() =>
  records.value.filter((r) => r.status === 'parsed' && checked[r.id]).map((r) => r.id),
)

const levelTag = (lv: number) => (lv === 10 ? 'danger' : lv === 20 ? 'warning' : lv === 30 ? 'primary' : 'success')
const recName = (s: string) =>
  ({ parsed: '待确认', error: '解析异常', confirmed: '已入库', discarded: '已丢弃' })[s] ?? s
const recTag = (s: string) =>
  ({ parsed: 'primary', error: 'warning', confirmed: 'success', discarded: 'info' })[s] ?? 'info'

async function load() {
  const { data } = await client.get(`/imports/${route.params.id}`)
  batch.value = data.batch
  records.value = data.records
  for (const r of data.records) if (r.status === 'parsed' && checked[r.id] === undefined) checked[r.id] = true
}

async function saveRecord(rec: any) {
  await client.put(`/imports/records/${rec.id}`, {
    title: rec.title, level: rec.level, vul_type: rec.vul_type, affected_url: rec.affected_url,
  })
  ElMessage.success('修正已保存')
  editing.value = null
  await load()
}

async function discard(rec: any) {
  await client.post(`/imports/records/${rec.id}/discard`)
  checked[rec.id] = false
  await load()
}

async function confirm() {
  const { data } = await client.post(`/imports/${route.params.id}/confirm`, {
    record_ids: selected.value, app_id: appId.value,
  })
  ElMessage.success(data.msg)
  await load()
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  const { data } = await client.get('/apps', { params: { size: 100 } })
  apps.value = data.items
  await load()
})
</script>
