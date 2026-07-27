<template>
  <div v-if="vul" class="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
    <div class="space-y-4">
      <el-card shadow="never" class="!rounded-lg">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-xl font-semibold text-gray-800">{{ vul.title }}</div>
            <div class="flex items-center gap-2 mt-2">
              <el-tag :color="levelColor(vul.level)" effect="dark" size="small" class="!border-0">
                {{ meta?.vul_level?.[vul.level] }}
              </el-tag>
              <el-tag size="small">{{ meta?.vul_type?.[vul.vul_type] }}</el-tag>
              <el-tag :color="statusColor(vul.status)" effect="dark" size="small" class="!border-0">
                {{ meta?.vul_status?.[vul.status] }}
              </el-tag>
              <el-tag type="info" size="small" effect="plain">来源：{{ meta?.vul_source?.[vul.source] }}</el-tag>
            </div>
          </div>
          <el-button @click="router.push(`/vulns/${vul.id}/edit`)">编辑</el-button>
        </div>
        <el-descriptions :column="2" border class="mt-4" size="small">
          <el-descriptions-item label="影响URL" :span="2">{{ vul.affected_url || '-' }}</el-descriptions-item>
          <el-descriptions-item label="所属应用">{{ vul.app_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="风险评分">{{ vul.risk_score }}</el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ fmt(vul.submit_time) }}</el-descriptions-item>
          <el-descriptions-item label="审核时间">{{ fmt(vul.audit_time) }}</el-descriptions-item>
          <el-descriptions-item label="通知时间">{{ fmt(vul.notice_time) }}</el-descriptions-item>
          <el-descriptions-item label="闭环时间">{{ fmt(vul.fix_time) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card v-for="sec in richSections" :key="sec.title" shadow="never" class="!rounded-lg">
        <template #header>{{ sec.title }}</template>
        <div class="rich-content" v-html="sec.html" />
      </el-card>
    </div>

    <div class="space-y-4">
      <el-card v-if="auth.hasPerm('vuln:audit')" shadow="never" class="!rounded-lg">
        <template #header>状态流转</template>
        <el-empty v-if="!transitions.length" description="当前状态没有可执行的流转" :image-size="60" />
        <div v-else class="space-y-2">
          <el-input v-model="comment" type="textarea" :rows="2" placeholder="处理意见（可选）" />
          <div class="flex flex-wrap gap-2">
            <el-button v-for="t in transitions" :key="t.status" size="small"
                       :type="t.status === 60 ? 'success' : t.status === 40 ? 'primary' : t.status === 30 ? 'danger' : ''"
                       @click="doTransition(t.status)">
              {{ t.name }}
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="!rounded-lg">
        <template #header>操作日志</template>
        <el-timeline class="!pl-1">
          <el-timeline-item v-for="log in logs" :key="log.id" :timestamp="fmt(log.create_time)" size="small">
            <div class="text-sm"><b>{{ log.username }}</b> {{ log.action }}</div>
            <div v-if="log.content" class="text-xs text-gray-400 mt-0.5">{{ log.content }}</div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelColor, statusColor } from '../utils/colors'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const vul = ref<any>(null)
const logs = ref<any[]>([])
const transitions = ref<any[]>([])
const comment = ref('')
const meta = ref<any>(null)

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

const richSections = computed(() =>
  [
    { title: '漏洞描述', html: vul.value?.description_html },
    { title: '复现步骤', html: vul.value?.reproduce_html },
    { title: '修复建议', html: vul.value?.solution_html },
  ].filter((s) => s.html),
)

async function load() {
  const id = route.params.id
  const [v, l, t] = await Promise.all([
    client.get(`/vulns/${id}`),
    client.get(`/vulns/${id}/logs`),
    client.get(`/vulns/${id}/transitions`),
  ])
  vul.value = v.data
  logs.value = l.data
  transitions.value = t.data
}

async function doTransition(status: number) {
  await client.post(`/vulns/${route.params.id}/transition`, { status, comment: comment.value })
  ElMessage.success('状态更新成功')
  comment.value = ''
  await load()
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load()
})
</script>
