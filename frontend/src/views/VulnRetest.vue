<template>
  <div v-if="vul" class="max-w-5xl space-y-4">
    <el-card shadow="never" class="!rounded-lg">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="text-xl font-semibold text-gray-800">{{ vul.title }}</div>
          <div class="flex items-center gap-2 mt-2">
            <span class="tl-tag" :style="levelSoftStyle(vul.level)">
              {{ meta?.vul_level?.[vul.level] }}
            </span>
            <span class="tl-tag" :style="statusSoftStyleEx(vul.status, vul.is_retest)">
              {{ statusLabel(vul.status, vul.is_retest, meta?.vul_status) }}
            </span>
            <span class="text-xs text-gray-400">共 {{ records.length }} 条复测记录</span>
          </div>
        </div>
        <el-button @click="router.push(`/vulns/${vulId}/edit`)">返回编辑</el-button>
      </div>
    </el-card>

    <el-empty v-if="!records.length" description="暂无复测记录，点击下方按钮新增" :image-size="80" />

    <el-card v-for="(rec, i) in records" :key="rec.id" shadow="never" class="!rounded-lg">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="font-medium">复测记录 #{{ i + 1 }}</span>
          <span class="text-xs text-gray-400">{{ rec.username }} · {{ fmt(rec.create_time) }}</span>
          <div class="flex-1" />
          <el-button size="small" type="primary" :loading="savingId === rec.id" @click="saveRecord(rec)">
            保存
          </el-button>
          <el-popconfirm title="确认删除该复测记录？" @confirm="removeRecord(rec)">
            <template #reference>
              <el-button size="small" type="danger" plain>删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </template>
      <div class="text-sm font-medium text-gray-600 mb-2">漏洞修复</div>
      <RichEditor v-model="rec.content_html"
                  @update:json="(j: any) => (rec.content_json = j)" />
    </el-card>

    <div class="flex items-center gap-2 pb-6">
      <el-button type="primary" plain :loading="adding" @click="addRecord">
        <el-icon class="mr-1"><Plus /></el-icon>新增复测记录
      </el-button>
      <div class="flex-1" />
      <el-button @click="router.back()">返回</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import client from '../api/client'
import RichEditor from '../components/RichEditor.vue'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle, statusLabel, statusSoftStyleEx } from '../utils/colors'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const vulId = Number(route.params.id)
const vul = ref<any>(null)
const meta = ref<any>(null)
const records = ref<any[]>([])
const adding = ref(false)
const savingId = ref<number | null>(null)

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

async function load() {
  const [v, r] = await Promise.all([
    client.get(`/vulns/${vulId}`),
    client.get(`/vulns/${vulId}/retests`),
  ])
  vul.value = v.data
  records.value = r.data
}

// 新增复测记录：后端创建空记录后追加到列表，生成新的富文本编辑框
async function addRecord() {
  adding.value = true
  try {
    const { data } = await client.post(`/vulns/${vulId}/retests`, { content_html: '', content_json: null })
    records.value.push(data)
    ElMessage.success('已新增复测记录，请填写漏洞修复内容')
  } finally {
    adding.value = false
  }
}

async function saveRecord(rec: any) {
  savingId.value = rec.id
  try {
    const { data } = await client.put(`/vulns/${vulId}/retests/${rec.id}`, {
      content_html: rec.content_html || '',
      content_json: rec.content_json ?? null,
    })
    Object.assign(rec, data)
    ElMessage.success('复测记录已保存')
  } finally {
    savingId.value = null
  }
}

async function removeRecord(rec: any) {
  await client.delete(`/vulns/${vulId}/retests/${rec.id}`)
  records.value = records.value.filter((r) => r.id !== rec.id)
  ElMessage.success('复测记录已删除')
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load()
})
</script>
