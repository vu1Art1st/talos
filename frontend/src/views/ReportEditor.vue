<template>
  <div v-if="report" class="grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-4">
    <div class="space-y-4">
      <el-card shadow="never" class="!rounded-lg">
        <template #header>
          <div class="flex items-center justify-between">
            <span>报告信息</span>
            <span class="text-xs text-gray-400">
              版本 v{{ report.version }} · {{ saveState }}
            </span>
          </div>
        </template>
        <el-form label-width="80px" size="default">
          <el-form-item label="报告标题">
            <el-input v-model="report.title" placeholder="标准名称（邮件、台账）-系统名称（网页）" @input="markDirty" />
          </el-form-item>
          <div class="grid grid-cols-1 md:grid-cols-2">
            <el-form-item label="系统名称">
              <el-input v-model="report.project_name" @input="markDirty" />
            </el-form-item>
            <el-form-item label="归属单位">
              <el-input v-model="report.customer" placeholder="默认留空，如为非集成系统在此输入被测单位名称" @input="markDirty" />
            </el-form-item>
            <el-form-item label="报告作者">
              <el-select v-model="authorNames" multiple filterable allow-create default-first-option
                         placeholder="选择系统内人员，可多选" class="w-full" @change="onAuthorChange">
                <el-option v-for="u in userOptions" :key="u.id" :label="u.name" :value="u.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="测试周期">
              <div class="flex items-center gap-1 w-full">
                <el-input v-model="report.test_start" placeholder="2025-01-01" @input="markDirty" />
                <span>至</span>
                <el-input v-model="report.test_end" placeholder="2025-01-15" @input="markDirty" />
              </div>
            </el-form-item>
            <el-form-item label="被测系统IP">
              <el-input v-model="report.target_ip" placeholder="导出时填入测试目标表" @input="markDirty" />
            </el-form-item>
          </div>
        </el-form>
      </el-card>

      <el-card v-for="(sec, i) in report.sections" :key="sec.id ?? `n${i}`" shadow="never" class="!rounded-lg">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="text-gray-400">{{ i + 1 }}.</span>
            <el-input v-model="sec.title" placeholder="章节标题" class="!w-80" size="small" @input="markDirty" />
            <el-tag v-if="sec.vul_id" size="small" type="info" effect="plain">关联漏洞 #{{ sec.vul_id }}</el-tag>
            <el-tag v-if="sec.vul_id && vulnStates[sec.vul_id]" size="small" effect="dark"
                    :color="statusColor(vulnStates[sec.vul_id].status)" class="!border-0">
              {{ statusName(vulnStates[sec.vul_id].status) }}
            </el-tag>
            <div class="flex-1" />
            <el-button size="small" :disabled="i === 0" @click="move(i, -1)">上移</el-button>
            <el-button size="small" :disabled="i === report.sections.length - 1" @click="move(i, 1)">下移</el-button>
            <el-button size="small" type="danger" plain @click="removeSection(i)">删除</el-button>
          </div>
        </template>
        <RichEditor v-model="sec.content_html"
                    @update:modelValue="markDirty"
                    @update:json="(j: any) => { sec.content_json = j; markDirty() }" />

        <!-- 复测处理面板：漏洞处于复测中时逐条填写复测详情并提交结论 -->
        <div v-if="sec.vul_id && vulnStates[sec.vul_id]?.status === 55"
             class="mt-4 border border-orange-200 bg-orange-50/40 rounded-lg p-3">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-sm font-medium text-orange-600">复测处理</span>
            <span class="text-xs text-gray-400">填写复测详情并选择结论提交</span>
          </div>
          <RichEditor v-model="vulnStates[sec.vul_id].retest_html"
                      @update:json="(j: any) => { vulnStates[sec.vul_id!].retest_json = j }" />
          <div class="flex items-center gap-2 mt-2">
            <el-select v-model="vulnStates[sec.vul_id].next_status" placeholder="选择复测结论" class="!w-44" size="small">
              <el-option label="已修复" :value="60" />
              <el-option label="复测未通过" :value="50" />
              <el-option label="已忽略" :value="20" />
              <el-option label="暂不处理" :value="35" />
            </el-select>
            <el-button type="primary" size="small"
                       :disabled="!vulnStates[sec.vul_id].next_status"
                       :loading="retestSubmitting === sec.vul_id"
                       @click="submitRetest(sec.vul_id)">
              提交复测结论
            </el-button>
          </div>
        </div>
        <!-- 已有复测详情且不在复测中：只读展示 -->
        <div v-else-if="sec.vul_id && vulnStates[sec.vul_id]?.retest_html"
             class="mt-4 border border-gray-200 rounded-lg p-3">
          <div class="text-sm font-medium text-gray-600 mb-2">复测详情</div>
          <div class="text-sm prose max-w-none" v-html="vulnStates[sec.vul_id].retest_html" />
        </div>
      </el-card>

      <div class="flex gap-2">
        <el-button @click="addSection">
          <el-icon class="mr-1"><Plus /></el-icon>添加章节
        </el-button>
        <el-button @click="insertVulnVisible = true">
          <el-icon class="mr-1"><Link /></el-icon>插入漏洞章节
        </el-button>
      </div>
    </div>

    <div class="space-y-4">
      <el-card shadow="never" class="!rounded-lg">
        <template #header>操作</template>
        <div class="space-y-2">
          <el-button type="primary" class="w-full" :loading="saving" @click="save()">保存报告</el-button>
          <el-select v-model="report.status" class="w-full" @change="markDirty">
            <el-option label="草稿" value="draft" />
            <el-option label="已定稿" value="final" />
          </el-select>
          <el-divider class="!my-3" />
          <el-button class="w-full" @click="doExport('docx')">
            <el-icon class="mr-1"><Document /></el-icon>导出 Word
          </el-button>
          <el-button class="w-full !ml-0" @click="doExport('pdf')">
            <el-icon class="mr-1"><Printer /></el-icon>导出 PDF
          </el-button>
        </div>
      </el-card>

      <el-card shadow="never" class="!rounded-lg">
        <template #header>导出记录</template>
        <el-empty v-if="!jobs.length" description="暂无导出" :image-size="50" />
        <div v-for="job in jobs" :key="job.id" class="flex items-center justify-between py-1.5 text-sm border-b border-gray-100 last:border-0">
          <span class="uppercase font-mono">{{ job.fmt }}</span>
          <el-tag size="small" :type="job.status === 'done' ? 'success' : job.status === 'failed' ? 'danger' : 'warning'">
            {{ { pending: '排队中', running: '生成中', done: '完成', failed: '失败' }[job.status as string] ?? job.status }}
          </el-tag>
          <el-button v-if="job.status === 'done'" size="small" type="primary" link @click="download(job)">下载</el-button>
          <el-tooltip v-else-if="job.status === 'failed'" :content="job.error || '生成失败'">
            <el-icon color="#F56C6C"><WarningFilled /></el-icon>
          </el-tooltip>
          <span v-else class="w-10" />
        </div>
      </el-card>
    </div>
  </div>

  <el-dialog v-model="insertVulnVisible" title="插入漏洞章节" width="600px">
    <el-select v-model="insertVulIds" multiple filterable class="w-full" placeholder="选择漏洞记录">
      <el-option v-for="v in vulns" :key="v.id" :label="`#${v.id} ${v.title}`" :value="v.id" />
    </el-select>
    <template #footer>
      <el-button @click="insertVulnVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!insertVulIds.length" @click="insertVulns">插入</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import RichEditor from '../components/RichEditor.vue'
import { statusColor } from '../utils/colors'

const STATUS_NAMES: Record<number, string> = {
  10: '未修复', 20: '已忽略', 35: '暂不处理', 50: '修复中', 55: '复测中', 60: '已修复',
}
const statusName = (s: number) => STATUS_NAMES[s] ?? String(s)

const route = useRoute()
const report = ref<any>(null)
const jobs = ref<any[]>([])
const saving = ref(false)
const saveState = ref('已保存')
const insertVulnVisible = ref(false)
const insertVulIds = ref<number[]>([])
const vulns = ref<any[]>([])
// 系统内启用用户选项与已选作者（author 字段以、拼接存储）
const userOptions = ref<{ id: number; name: string }[]>([])
const authorNames = ref<string[]>([])
// 关联漏洞状态与复测详情，key 为 vul_id
const vulnStates = ref<Record<number, any>>({})
const retestSubmitting = ref<number | null>(null)
let saveTimer: number | undefined
let jobTimer: number | undefined

function markDirty() {
  saveState.value = '有未保存修改'
  // 防抖自动保存草稿
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => save(true), 3000)
}

async function loadVulnStates() {
  const { data } = await client.get(`/reports/${route.params.id}/vuln-states`)
  const map: Record<number, any> = {}
  for (const v of data) map[v.vul_id] = { ...v, next_status: null }
  vulnStates.value = map
}

function syncAuthorNames() {
  authorNames.value = report.value?.author
    ? report.value.author.split(/[、,，]+/).filter(Boolean)
    : []
}

function onAuthorChange() {
  report.value.author = authorNames.value.join('、')
  markDirty()
}

async function load() {
  const { data } = await client.get(`/reports/${route.params.id}`)
  data.sections.sort((a: any, b: any) => a.order - b.order)
  report.value = data
  syncAuthorNames()
  await Promise.all([loadJobs(), loadVulnStates()])
}

async function loadJobs() {
  const { data } = await client.get(`/reports/${route.params.id}/exports`)
  jobs.value = data
}

async function save(auto = false) {
  if (!report.value) return
  window.clearTimeout(saveTimer)
  saving.value = true
  try {
    const body = {
      ...report.value,
      sections: report.value.sections.map((s: any, i: number) => ({ ...s, order: i })),
    }
    const { data } = await client.put(`/reports/${report.value.id}`, body)
    data.sections.sort((a: any, b: any) => a.order - b.order)
    report.value = data
    syncAuthorNames()
    saveState.value = '已保存'
    // 保存可能触发新关联漏洞自动进入修复中，同步刷新状态
    await loadVulnStates()
    if (!auto) ElMessage.success('保存成功')
  } catch (e: any) {
    if (e?.response?.status === 409) {
      await ElMessageBox.confirm('报告已被他人修改，是否加载最新版本？（当前未保存修改将丢失）', '版本冲突', {
        confirmButtonText: '加载最新',
        cancelButtonText: '继续编辑',
        type: 'warning',
      }).then(load).catch(() => undefined)
    }
  } finally {
    saving.value = false
  }
}

function addSection() {
  report.value.sections.push({ order: report.value.sections.length, title: '', content_html: '', content_json: null, vul_id: null })
  markDirty()
}

function removeSection(i: number) {
  report.value.sections.splice(i, 1)
  markDirty()
}

function move(i: number, dir: number) {
  const arr = report.value.sections
  ;[arr[i], arr[i + dir]] = [arr[i + dir], arr[i]]
  markDirty()
}

// 提交单个漏洞的复测详情与结论（复测中 → 已修复/复测未通过/已忽略/暂不处理）
async function submitRetest(vulId: number) {
  const state = vulnStates.value[vulId]
  if (!state?.next_status) return
  retestSubmitting.value = vulId
  try {
    await client.post(`/vulns/${vulId}/transition`, {
      status: state.next_status,
      retest_html: state.retest_html || '',
      retest_json: state.retest_json ?? null,
    })
    ElMessage.success(`漏洞 #${vulId} 复测结论已提交`)
    await loadVulnStates()
  } finally {
    retestSubmitting.value = null
  }
}

async function insertVulns() {
  for (const id of insertVulIds.value) {
    const { data: v } = await client.get(`/vulns/${id}`)
    const html = [
      v.description_html && `<h3>漏洞描述</h3>${v.description_html}`,
      v.reproduce_html && `<h3>复现步骤</h3>${v.reproduce_html}`,
      v.solution_html && `<h3>修复建议</h3>${v.solution_html}`,
    ].filter(Boolean).join('')
    report.value.sections.push({
      order: report.value.sections.length, title: v.title,
      content_html: html || '<p></p>', content_json: null, vul_id: v.id,
    })
  }
  insertVulnVisible.value = false
  insertVulIds.value = []
  markDirty()
}

async function doExport(fmt: string) {
  if (saveState.value !== '已保存') await save(true)
  await client.post(`/reports/${route.params.id}/export`, { fmt })
  ElMessage.success('导出任务已提交，请稍候在导出记录中下载')
  await loadJobs()
}

function download(job: any) {
  // 带鉴权下载
  client.get(`/reports/exports/${job.id}/download`, { responseType: 'blob' }).then((resp) => {
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `${report.value.title}.${job.fmt}`
    a.click()
    URL.revokeObjectURL(url)
  })
}

watch(insertVulnVisible, async (v) => {
  if (v && !vulns.value.length) {
    const { data } = await client.get('/vulns', { params: { size: 100 } })
    vulns.value = data.items
  }
})

onMounted(async () => {
  await load()
  client.get('/users/options').then(({ data }) => { userOptions.value = data })
  jobTimer = window.setInterval(() => {
    if (jobs.value.some((j) => j.status === 'pending' || j.status === 'running')) loadJobs()
  }, 2000)
})

onBeforeUnmount(() => {
  window.clearTimeout(saveTimer)
  window.clearInterval(jobTimer)
})
</script>
