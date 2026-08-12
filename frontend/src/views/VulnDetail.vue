<template>
  <div v-if="vul" class="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
    <div class="space-y-4">
      <el-card shadow="never" class="!rounded-lg">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-xl font-semibold text-gray-800">{{ vul.title }}</div>
            <div class="flex items-center gap-2 mt-2">
              <span class="tl-tag" :style="levelSoftStyle(vul.level)">
                {{ meta?.vul_level?.[vul.level] }}
              </span>
              <span class="tl-tag" :style="softStyle(STAT_CARD_COLORS.blue)">{{ meta?.vul_type?.[vul.vul_type] }}</span>
              <span class="tl-tag" :style="statusSoftStyleEx(vul.status, vul.is_retest)">
                {{ statusLabel(vul.status, vul.is_retest, meta?.vul_status) }}
              </span>
              <span class="tl-tag" :style="softStyle(STAT_CARD_COLORS.gray)">来源：{{ meta?.vul_source?.[vul.source] }}</span>
            </div>
          </div>
          <div class="flex gap-2">
            <el-tooltip v-if="auth.hasPerm('vuln:manage')" content="将本漏洞的描述与修复建议存入知识库，作为该类型的标准模板" placement="top">
              <el-button plain @click="saveAsTemplate">存为模板</el-button>
            </el-tooltip>
            <el-tooltip v-if="!canEdit" content="仅已认领该渗透测试工单的账号可编辑该漏洞" placement="top">
              <span>
                <el-button :disabled="true" @click="router.push(`/vulns/${vul.id}/edit`)">编辑</el-button>
              </span>
            </el-tooltip>
            <el-button v-else @click="router.push(`/vulns/${vul.id}/edit`)">编辑</el-button>
          </div>
        </div>
        <el-descriptions :column="2" border class="mt-4" size="small">
          <el-descriptions-item label="影响URL" :span="2">
            <div v-if="affectedUrls.length" class="flex flex-col gap-0.5">
              <span v-for="(u, i) in affectedUrls" :key="i">{{ u }}</span>
            </div>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="关联资产">
            {{ (vul.assets ?? []).map((a: any) => a.name).join('、') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="渗透测试工单">
            <el-link v-if="vul.testing_plan_id" type="primary"
                     @click="router.push('/testing-plans')">已关联计划</el-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ fmtDateTime(vul.submit_time) }}</el-descriptions-item>
          <el-descriptions-item label="通知时间">{{ fmtDateTime(vul.notice_time) }}</el-descriptions-item>
          <el-descriptions-item label="闭环时间">{{ fmtDateTime(vul.fix_time) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card v-for="sec in richSections" :key="sec.title" shadow="never" class="!rounded-lg">
        <template #header>{{ sec.title }}</template>
        <div class="rich-content" v-html="safeHtml(sec.html)" />
      </el-card>
    </div>

    <div class="space-y-4">
      <el-card v-if="auth.hasPerm('vuln:audit')" shadow="never" class="!rounded-lg">
        <template #header>状态流转</template>
        <el-empty v-if="!transitions.length" description="当前状态没有可执行的流转" :image-size="80" />
        <div v-else class="space-y-2">
          <el-input v-model="comment" type="textarea" :rows="2" placeholder="处理意见（可选）" />
          <div class="flex flex-wrap gap-2">
            <el-button v-for="t in transitions" :key="t.status" size="small"
                       :type="t.status === 60 ? 'success' : t.status === 50 ? 'warning' : t.status === 55 ? 'primary' : ''"
                       @click="doTransition(t.status)">
              {{ transitionLabel(t) }}
            </el-button>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="!rounded-lg">
        <template #header>操作日志</template>
        <el-timeline class="!pl-1">
          <el-timeline-item v-for="log in logs" :key="log.id" :timestamp="fmtDateTime(log.create_time)" size="small">
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
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle, softStyle, STAT_CARD_COLORS, statusLabel, statusSoftStyleEx } from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import { safeHtml } from '../utils/html'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const vul = ref<any>(null)
const logs = ref<any[]>([])
const transitions = ref<any[]>([])
const comment = ref('')
const meta = ref<any>(null)

// 影响URL 多值（后端换行分隔存储）逐行展示
const affectedUrls = computed<string[]>(() =>
  (vul.value?.affected_url ?? '').split('\n').map((u: string) => u.trim()).filter(Boolean))

// 复测中打回修复中时，按业务语义显示为「复测未通过」
function transitionLabel(t: { status: number; name: string }) {
  if (vul.value?.status === 55 && t.status === 50) return '复测未通过'
  return t.name
}

// 编辑权限：已关联测试计划的漏洞仅已认领该计划的账号可编辑；未关联计划由提交人或漏洞管理员编辑
const planTesters = ref<any[]>([])
const canEdit = computed(() => {
  const v = vul.value
  if (!v) return false
  if (v.testing_plan_id) {
    return planTesters.value.some((u: any) => u.id === auth.user?.id)
  }
  const me = auth.user
  return auth.hasPerm('vuln:manage') || v.submitter_id === me?.id
})

const richSections = computed(() =>
  [
    { title: '漏洞描述', html: vul.value?.description_html },
    { title: '复现步骤', html: vul.value?.reproduce_html },
    { title: '修复建议', html: vul.value?.solution_html },
    { title: '复测详情', html: vul.value?.retest_html },
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
  // 已关联计划时加载计划认领者，用于判定编辑权限
  if (vul.value?.testing_plan_id) {
    try {
      const planResp = await client.get(`/testing-plans/${vul.value.testing_plan_id}`)
      planTesters.value = planResp.data?.testers ?? []
    } catch {
      // 计划不存在/无权限时降级为空认领者，不阻断详情加载（错误提示由拦截器统一处理）
      planTesters.value = []
    }
  } else {
    planTesters.value = []
  }
}

async function doTransition(status: number) {
  await client.post(`/vulns/${route.params.id}/transition`, { status, comment: comment.value })
  ElMessage.success('状态更新成功')
  comment.value = ''
  await load()
}

// 将当前漏洞的描述/修复建议沉淀为该类型的知识库模板（存在则覆盖）
async function saveAsTemplate() {
  const typeName = meta.value?.vul_type?.[vul.value.vul_type] ?? vul.value.vul_type
  try {
    await ElMessageBox.confirm(`将覆盖类型「${typeName}」已有的知识库模板，是否继续？`, '存为模板', { type: 'warning' })
  } catch {
    return
  }
  await client.post(`/knowledge/from-vul/${vul.value.id}`)
  ElMessage.success('已存入漏洞模板库')
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load()
})
</script>
