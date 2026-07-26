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
            <el-input v-model="report.title" @input="markDirty" />
          </el-form-item>
          <div class="grid grid-cols-1 md:grid-cols-2">
            <el-form-item label="项目名称">
              <el-input v-model="report.project_name" @input="markDirty" />
            </el-form-item>
            <el-form-item label="委托单位">
              <el-input v-model="report.customer" @input="markDirty" />
            </el-form-item>
            <el-form-item label="报告作者">
              <el-input v-model="report.author" @input="markDirty" />
            </el-form-item>
            <el-form-item label="测试周期">
              <div class="flex items-center gap-1 w-full">
                <el-input v-model="report.test_start" placeholder="2025-01-01" @input="markDirty" />
                <span>至</span>
                <el-input v-model="report.test_end" placeholder="2025-01-15" @input="markDirty" />
              </div>
            </el-form-item>
          </div>
        </el-form>
      </el-card>

      <el-card shadow="never" class="!rounded-lg">
        <template #header>测试结论 / 摘要</template>
        <RichEditor v-model="report.summary_html"
                    @update:modelValue="markDirty"
                    @update:json="(j: any) => { report.summary_json = j; markDirty() }" />
      </el-card>

      <el-card v-for="(sec, i) in report.sections" :key="sec.id ?? `n${i}`" shadow="never" class="!rounded-lg">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="text-gray-400">{{ i + 1 }}.</span>
            <el-input v-model="sec.title" placeholder="章节标题" class="!w-80" size="small" @input="markDirty" />
            <el-tag v-if="sec.vul_id" size="small" type="info" effect="plain">关联漏洞 #{{ sec.vul_id }}</el-tag>
            <div class="flex-1" />
            <el-button size="small" :disabled="i === 0" @click="move(i, -1)">上移</el-button>
            <el-button size="small" :disabled="i === report.sections.length - 1" @click="move(i, 1)">下移</el-button>
            <el-button size="small" type="danger" plain @click="removeSection(i)">删除</el-button>
          </div>
        </template>
        <RichEditor v-model="sec.content_html"
                    @update:modelValue="markDirty"
                    @update:json="(j: any) => { sec.content_json = j; markDirty() }" />
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

const route = useRoute()
const report = ref<any>(null)
const jobs = ref<any[]>([])
const saving = ref(false)
const saveState = ref('已保存')
const insertVulnVisible = ref(false)
const insertVulIds = ref<number[]>([])
const vulns = ref<any[]>([])
let saveTimer: number | undefined
let jobTimer: number | undefined

function markDirty() {
  saveState.value = '有未保存修改'
  // 防抖自动保存草稿
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => save(true), 3000)
}

async function load() {
  const { data } = await client.get(`/reports/${route.params.id}`)
  data.sections.sort((a: any, b: any) => a.order - b.order)
  report.value = data
  await loadJobs()
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
    saveState.value = '已保存'
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
  jobTimer = window.setInterval(() => {
    if (jobs.value.some((j) => j.status === 'pending' || j.status === 'running')) loadJobs()
  }, 2000)
})

onBeforeUnmount(() => {
  window.clearTimeout(saveTimer)
  window.clearInterval(jobTimer)
})
</script>
