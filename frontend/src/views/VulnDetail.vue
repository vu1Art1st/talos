<template>
  <!-- 正文与侧栏滚动分离：页面整体不滚动，左侧正文/右侧（状态流转+操作日志）各自独立滚动 -->
  <div v-if="vul" class="flex h-full min-h-0 flex-col xl:flex-row gap-4">
    <div class="flex-1 min-h-0 overflow-y-auto space-y-4 pr-1">
      <el-card shadow="never">
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="text-xl font-semibold text-gray-800">{{ vul.title }}</div>
            <div class="flex items-center gap-2 mt-2">
              <span class="tl-tag" :style="levelSoftStyle(vul.level)">
                {{ meta?.vul_level?.[vul.level] }}
              </span>
              <span class="tl-tag" :style="vulTypeSoftStyle(vul.vul_type)">{{ meta?.vul_type?.[vul.vul_type ?? 0] ?? vul.vul_type }}</span>
              <span class="tl-tag" :style="statusSoftStyleWithRetest(vul.status, vul.is_retest)">
                {{ statusLabel(vul.status, vul.is_retest, meta?.vul_status) }}
              </span>
              <span v-if="vul.score" class="tl-tag" :style="levelSoftStyle(vul.level)" :title="vul.cvss_vector ?? ''">
                CVSS {{ vul.score.toFixed(1) }}
              </span>
              <span class="tl-tag" :style="softStyle(STAT_CARD_COLORS.gray)">
                来源：{{ vul.testing_plan_id ? '渗透测试工单' : (meta?.vul_source?.[vul.source ?? 0] ?? '-') }}
              </span>
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
            {{ (vul.assets ?? []).map((a) => a.name).join('、') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="渗透测试工单">
            <el-link v-if="vul.testing_plan_id" type="primary"
                     @click="router.push('/testing-plans')">已关联计划</el-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="提交时间">{{ fmtDateTime(vul.submit_time) }}</el-descriptions-item>
          <el-descriptions-item label="通知时间">{{ fmtDateTime(vul.notice_time) }}</el-descriptions-item>
          <el-descriptions-item label="闭环时间">{{ fmtDateTime(vul.fix_time) }}</el-descriptions-item>
          <el-descriptions-item label="修复时限">
            <div v-if="vul.due_at" class="flex items-center gap-2">
              <span class="num">{{ fmtDateTime(vul.due_at) }}</span>
              <span class="tl-tag" :style="slaStateSoftStyle(vul.sla_state)">
                {{ slaStateMeta(vul.sla_state).label }} · {{ fmtSlaRemaining(vul.sla_remaining_hours) }}
              </span>
            </div>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="SLA 延期">
            <el-button v-if="vul.due_at && canExtend" size="small" link type="primary" @click="openExtend">
              延期申请
            </el-button>
            <el-link v-if="extensions.length" class="ml-2" type="info" @click="extVisible = true">
              {{ extensions.length }} 条记录
            </el-link>
            <span v-if="!vul.due_at && !extensions.length">-</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card v-for="sec in richSections" :key="sec.title" shadow="never">
        <template #header>{{ sec.title }}</template>
        <div class="rich-content" v-html="safeHtml(sec.html)" />
      </el-card>
    </div>

    <div class="space-y-4 max-h-[45vh] xl:max-h-none xl:h-full xl:min-h-0 xl:overflow-y-auto xl:w-[320px] xl:shrink-0">
      <el-card v-if="auth.hasPerm('vuln:audit')" shadow="never">
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

      <el-card shadow="never">
        <template #header>操作日志</template>
        <el-timeline class="!pl-1">
          <el-timeline-item v-for="log in logs" :key="log.id" :timestamp="fmtDateTime(log.create_time)" size="small">
            <div class="text-sm"><b>{{ log.realname || log.username }}</b> {{ log.action }}</div>
            <div v-if="log.content" class="text-xs text-gray-400 mt-0.5">{{ log.content }}</div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>
  </div>
<!-- 首屏加载占位：避免数据未到时的空白闪现 -->
  <div v-else v-loading="true" class="h-64" element-loading-text="加载中..." />

  <!-- P1-1 SLA 延期：记录原/新到期时间与原因，不允许无痕改期 -->
  <el-dialog v-model="extendVisible" title="SLA 延期申请" width="480px" :close-on-click-modal="false">
    <el-form :model="extendForm" label-width="110px">
      <el-form-item label="当前到期时间">{{ fmtDateTime(vul?.due_at) }}</el-form-item>
      <el-form-item label="延期方式">
        <el-radio-group v-model="extendForm.mode">
          <el-radio-button value="days">顺延天数</el-radio-button>
          <el-radio-button value="date">指定日期</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="extendForm.mode === 'days'" label="顺延天数" required>
        <el-input-number v-model="extendForm.extend_days" :min="1" :max="365" />
      </el-form-item>
      <el-form-item v-else label="新到期时间" required>
        <el-date-picker v-model="extendForm.new_due_at" type="datetime" value-format="YYYY-MM-DD HH:mm"
                        format="YYYY-MM-DD HH:mm" placeholder="选择新的到期时间" />
      </el-form-item>
      <el-form-item label="延期原因" required>
        <el-input v-model="extendForm.reason" type="textarea" :rows="3" maxlength="500" show-word-limit />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="extendVisible = false">取消</el-button>
      <el-button type="primary" :loading="extending" @click="submitExtend">提交</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="extVisible" title="SLA 延期记录" width="640px">
    <el-table :data="extensions" stripe>
      <el-table-column label="原到期时间" width="170">
        <template #default="{ row }"><span class="num">{{ fmtDateTime(row.old_due_at) }}</span></template>
      </el-table-column>
      <el-table-column label="新到期时间" width="170">
        <template #default="{ row }"><span class="num">{{ fmtDateTime(row.new_due_at) }}</span></template>
      </el-table-column>
      <el-table-column prop="reason" label="原因" min-width="180" show-overflow-tooltip />
      <el-table-column prop="username" label="操作人" width="110" />
      <el-table-column label="时间" width="170">
        <template #default="{ row }"><span class="num">{{ fmtDateTime(row.create_time) }}</span></template>
      </el-table-column>
      <template #empty><el-empty description="暂无延期记录" :image-size="80" /></template>
    </el-table>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import {
  levelSoftStyle, slaStateMeta, slaStateSoftStyle, softStyle, STAT_CARD_COLORS,
  statusLabel, statusSoftStyleWithRetest, vulTypeSoftStyle,
} from '../utils/colors'
import { fmtDateTime, fmtSlaRemaining } from '../utils/format'
import { safeHtml } from '../utils/html'
import type { SlaExtension, TestingPlan, UserBrief, Vuln, VulnLog, VulnTransition } from '../types'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const vul = ref<Vuln | null>(null)
const logs = ref<VulnLog[]>([])
const transitions = ref<VulnTransition[]>([])
const comment = ref('')
const meta = ref<Record<string, Record<number, string>> | null>(null)

// ---------- P1-1 SLA 延期 ----------
const extensions = ref<SlaExtension[]>([])
const extendVisible = ref(false)
const extVisible = ref(false)
const extending = ref(false)
const extendForm = reactive({ mode: 'days', extend_days: 3, new_due_at: '', reason: '' })
const canExtend = computed(() => auth.hasPerm('vuln:manage') && vul.value?.sla_state !== 'closed')

function openExtend() {
  extendForm.mode = 'days'
  extendForm.extend_days = 3
  extendForm.new_due_at = ''
  extendForm.reason = ''
  extendVisible.value = true
}

async function loadExtensions() {
  const id = route.params.id
  extensions.value = (await client.get<SlaExtension[]>(`/sla/vulns/${id}/extensions`)).data
}

async function submitExtend() {
  if (!extendForm.reason.trim()) return ElMessage.warning('请填写延期原因')
  if (extendForm.mode === 'date' && !extendForm.new_due_at) return ElMessage.warning('请选择新的到期时间')
  extending.value = true
  try {
    await client.post(`/sla/vulns/${route.params.id}/extend`, {
      reason: extendForm.reason.trim(),
      extend_days: extendForm.mode === 'days' ? extendForm.extend_days : null,
      new_due_at: extendForm.mode === 'date' ? extendForm.new_due_at : null,
    })
    extendVisible.value = false
    ElMessage.success('延期已提交并留痕')
    await Promise.all([load(), loadExtensions()])
  } finally {
    extending.value = false
  }
}

// 影响URL 多值（后端换行分隔存储）逐行展示
const affectedUrls = computed<string[]>(() =>
  (vul.value?.affected_url ?? '').split('\n').map((u: string) => u.trim()).filter(Boolean))

// 复测中打回修复中时，按业务语义显示为「复测未通过」
function transitionLabel(t: { status: number; name: string }) {
  if (vul.value?.status === 55 && t.status === 50) return '复测未通过'
  return t.name
}

// 编辑权限：已关联测试计划的漏洞仅已认领该计划的账号可编辑；未关联计划由提交人或漏洞管理员编辑
const planTesters = ref<UserBrief[]>([])
const canEdit = computed(() => {
  const v = vul.value
  if (!v) return false
  if (v.testing_plan_id) {
    return planTesters.value.some((u) => u.id === auth.user?.id)
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
    client.get<Vuln>(`/vulns/${id}`),
    client.get<VulnLog[]>(`/vulns/${id}/logs`),
    client.get<VulnTransition[]>(`/vulns/${id}/transitions`),
  ])
  vul.value = v.data
  logs.value = l.data
  transitions.value = t.data
  // 已关联计划时加载计划认领者，用于判定编辑权限
  if (vul.value?.testing_plan_id) {
    try {
      const planResp = await client.get<TestingPlan>(`/testing-plans/${vul.value.testing_plan_id}`)
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
  const v = vul.value
  if (!v) return
  const vulTypeName = meta.value?.vul_type?.[v.vul_type ?? 0] ?? v.vul_type
  try {
    await ElMessageBox.confirm(`将覆盖类型「${vulTypeName}」已有的知识库模板，是否继续？`, '存为模板', { type: 'warning' })
  } catch {
    return
  }
  await client.post(`/knowledge/from-vul/${v.id}`)
  ElMessage.success('已存入漏洞模板库')
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load()
  await loadExtensions()
})
</script>
