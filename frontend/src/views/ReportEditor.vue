<template>
  <!-- 需求4：小屏内容滚动与页面滚动分离 —— 页面整体不滚动，内容区/侧栏各自滚动 -->
  <div v-if="report" class="flex h-full min-h-0 flex-col xl:flex-row gap-4">
    <div class="flex-1 min-h-0 overflow-y-auto space-y-4 pr-1">
      <el-card shadow="never" class="!rounded-lg">
        <template #header>
          <div class="flex items-center justify-between">
            <span>报告信息</span>
            <span class="text-xs text-gray-400">
              版本 v{{ report.version }} · {{ saveState }}
            </span>
          </div>
        </template>
        <el-form label-width="90px" size="default">
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
              <el-date-picker v-model="testRange" type="daterange" value-format="YYYY-MM-DD"
                              range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期"
                              unlink-panels class="!w-full" />
            </el-form-item>
            <el-form-item label="实际人天">
              <span class="text-sm">{{ actualMandays }} 天</span>
            </el-form-item>
            <el-form-item label="被测系统IP">
              <el-input v-model="report.target_ip" placeholder="导出时填入测试目标表" @input="markDirty" />
            </el-form-item>
          </div>
        </el-form>
      </el-card>

      <el-card v-for="(sec, i) in report.sections" :key="sec.id ?? `n${i}`" :id="`section-${i}`"
               shadow="never" class="!rounded-lg scroll-mt-4">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="text-gray-400">{{ i + 1 }}.</span>
            <el-input v-model="sec.title" placeholder="章节标题" class="!w-80" size="small" @input="markDirty" />
            <el-tag v-if="sec.vul_id" size="small" type="info" effect="plain">关联漏洞</el-tag>
            <div class="flex-1" />
            <el-button size="small" :disabled="i === 0" @click="move(i, -1)">上移</el-button>
            <el-button size="small" :disabled="i === report.sections.length - 1" @click="move(i, 1)">下移</el-button>
            <el-button size="small" type="danger" plain @click="removeSection(i)">删除</el-button>
          </div>
        </template>
        <!-- 关联漏洞字段：与漏洞编辑页一致的固定下拉框，修改即时保存到漏洞记录 -->
        <el-form v-if="sec.vul_id && vulnStates[sec.vul_id]" label-width="90px" class="mb-3">
          <div class="grid grid-cols-1 md:grid-cols-3">
            <el-form-item label="漏洞类型">
              <el-select :model-value="vulnStates[sec.vul_id].vul_type" filterable class="w-full"
                         @change="(v: number) => changeVulnField(sec.vul_id!, 'vul_type', v)">
                <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
            <el-form-item label="漏洞等级">
              <!-- 需求5：已有漏洞等级时不可修改（漏洞创建默认即有等级，基本恒为只读） -->
              <el-select :model-value="vulnStates[sec.vul_id].level" class="w-full"
                         :disabled="vulnStates[sec.vul_id].level != null"
                         @change="(v: number) => changeVulnField(sec.vul_id!, 'level', v)">
                <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)">
                  <span class="flex items-center gap-1.5">
                    <span class="inline-block w-2 h-2 rounded-full" :style="{ background: levelColor(Number(code)) }" />
                    <span :style="{ color: levelColor(Number(code)) }">{{ name }}</span>
                  </span>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item label="漏洞状态">
              <el-select :model-value="vulnStates[sec.vul_id].status" class="w-full" placeholder="选择漏洞状态"
                         @change="(v: number) => changeVulnField(sec.vul_id!, 'status', v)">
                <el-option v-for="(name, code) in meta?.vul_status" :key="code" :label="name" :value="Number(code)">
                  <span class="flex items-center gap-1.5">
                    <span class="inline-block w-2 h-2 rounded-full" :style="{ background: statusColor(Number(code)) }" />
                    <span :style="{ color: statusColor(Number(code)) }">{{ name }}</span>
                  </span>
                </el-option>
              </el-select>
            </el-form-item>
          </div>
        </el-form>
        <RichEditor v-model="sec.content_html"
                    @update:modelValue="markDirty"
                    @update:json="(j: any) => { sec.content_json = j; markDirty() }" />

        <!-- 复测处理：复用 VulnRetestPanel（与渗透测试工单流程抽屉一致），支持结构化复测记录 -->
        <div v-if="sec.vul_id" class="mt-4">
          <VulnRetestPanel :vul-id="sec.vul_id" @changed="onRetestChanged" />
        </div>
      </el-card>

    </div>

    <!-- 侧栏：小屏时置于底部且独立滚动，大屏固定右侧随内容区独立滚动 -->
    <div class="xl:w-[300px] xl:shrink-0 space-y-4 max-h-[45vh] xl:max-h-none xl:h-full xl:min-h-0 xl:overflow-y-auto">
      <!-- 章节导航：点击快速跳转到对应漏洞编辑区域 -->
      <el-card shadow="never" class="!rounded-lg">
        <template #header>章节导航</template>
        <el-empty v-if="!report.sections.length" description="暂无章节" :image-size="80" />
        <div v-else ref="navScrollRef" class="max-h-72 overflow-y-auto -mx-1" @dragend="onDragEnd">
          <template v-for="(sec, i) in report.sections" :key="sec.id ?? `n${i}`">
            <!-- 拖拽指示线：标记目标插入位置 -->
            <div v-if="dropLineIndex === i" class="mx-2 h-0.5 rounded-full bg-blue-500"></div>
            <div class="flex items-center gap-2 px-2 py-1.5 rounded text-sm select-none"
                 :class="{
                   'bg-blue-50 text-blue-600': activeSection === i && dragIndex !== i,
                   'text-gray-600': activeSection !== i || dragIndex === i,
                   'cursor-pointer': dragIndex !== i,
                   'cursor-grabbing opacity-40': dragIndex === i,
                   'bg-gray-100': overIndex === i && dragIndex !== i && dragIndex !== null,
                 }"
                 :draggable="dragIndex === null || dragIndex === i"
                 @click="scrollToSection(i)"
                 @dragstart="onDragStart(i, $event)"
                 @dragover.prevent="onDragOver(i, $event)"
                 @dragenter="onDragEnter(i)"
                 @dragleave="onDragLeave(i, $event)"
                 @drop.prevent="onDrop(i)">
              <span class="shrink-0" :class="dragIndex !== null ? 'text-gray-300' : 'text-gray-400'">{{ i + 1 }}.</span>
              <el-icon v-if="dragIndex !== null" class="shrink-0 text-gray-300" :size="12"><Rank /></el-icon>
              <span class="truncate flex-1" :title="sec.title">{{ sec.title || '未命名章节' }}</span>
              <span v-if="sec.vul_id && vulnStates[sec.vul_id]" class="tl-tag shrink-0"
                    :style="statusSoftStyle(vulnStates[sec.vul_id].status)">
                {{ statusName(vulnStates[sec.vul_id].status) }}
              </span>
            </div>
          </template>
          <div v-if="dropLineIndex === report.sections.length" class="mx-2 h-0.5 rounded-full bg-blue-500"></div>
        </div>
      </el-card>

      <el-card shadow="never" class="!rounded-lg">
        <template #header>操作</template>
        <div class="space-y-2">
          <el-button type="primary" class="w-full" :loading="saving" @click="save()">保存报告</el-button>
          <el-button type="success" class="w-full !ml-0" @click="vulnFormVisible = true">录入漏洞</el-button>
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
        <el-empty v-if="!jobs.length" description="暂无导出" :image-size="80" />
        <div v-for="job in jobs" :key="job.id" class="py-2 text-sm border-b border-gray-100 last:border-0">
          <div class="truncate text-gray-700" :title="job.title || report.title">
            {{ job.title || report.title }}
          </div>
          <div class="flex items-center gap-2 mt-1">
            <span class="uppercase font-mono text-xs text-gray-400">{{ job.fmt }}</span>
            <span class="tl-tag" :style="exportJobSoftStyle(job.status)">{{ exportJobName(job.status) }}</span>
            <el-tooltip v-if="job.status === 'failed'" :content="job.error || '生成失败'">
              <el-icon :color="EXPORT_JOB_META.failed.color"><WarningFilled /></el-icon>
            </el-tooltip>
            <div class="flex-1" />
            <el-button v-if="job.status === 'done'" size="small" type="primary" link
                       @click="previewRef?.open(`/reports/exports/${job.id}/preview`, job.title || report.title)">预览</el-button>
            <el-button v-if="job.status === 'done'" size="small" type="primary" link class="!ml-0" @click="download(job)">下载</el-button>
            <el-popconfirm v-if="job.status === 'done' || job.status === 'failed'"
                           title="确认删除该导出记录及报告文件？" @confirm="removeJob(job)">
              <template #reference>
                <el-button size="small" type="danger" link class="!ml-0">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </el-card>
    </div>
  </div>

  <PdfPreviewDialog ref="previewRef" />

  <el-dialog v-model="vulnFormVisible" title="录入漏洞" width="780px" top="6vh">
    <VulnFormPanel :plan-id="report?.testing_plan_id ?? null" @saved="onVulnFormSaved" />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'
import RichEditor from '../components/RichEditor.vue'
import PdfPreviewDialog from '../components/PdfPreviewDialog.vue'
import VulnFormPanel from '../components/VulnFormPanel.vue'
import VulnRetestPanel from '../components/VulnRetestPanel.vue'
import { useAuthStore } from '../stores/auth'
import { showTocNotice } from '../utils/tocNotice'
import {
  EXPORT_JOB_META,
  exportJobName,
  exportJobSoftStyle,
  levelColor,
  statusColor,
  statusName,
  statusSoftStyle,
} from '../utils/colors'
import { fmtDateTime } from '../utils/format'

// 报告编辑页漏洞字段下拉框的中文名（提示消息用）
const FIELD_LABELS: Record<string, string> = {
  status: '漏洞状态', level: '漏洞等级', vul_type: '漏洞类型',
}

const auth = useAuthStore()
const route = useRoute()
const report = ref<any>(null)
const meta = ref<any>(null)
const jobs = ref<any[]>([])
const saving = ref(false)
const saveState = ref('已保存')
const previewRef = ref<InstanceType<typeof PdfPreviewDialog>>()
// 报告编辑页「录入漏洞」：与测试流程录入漏洞完全一致（VulnFormPanel），预关联本报告测试计划
const vulnFormVisible = ref(false)
// 系统内启用用户选项与已选作者（author 字段以、拼接存储）
const userOptions = ref<{ id: number; name: string }[]>([])
const authorNames = ref<string[]>([])
// 关联漏洞状态与复测详情，key 为 vul_id
const vulnStates = ref<Record<number, any>>({})
let saveTimer: number | undefined
let jobTimer: number | undefined

// 测试周期：日期范围选择器与 test_start / test_end 字符串字段互转
const testRange = computed<[string, string] | null>({
  get: () => (report.value?.test_start || report.value?.test_end)
    ? [report.value.test_start, report.value.test_end]
    : null,
  set: (v) => {
    report.value.test_start = v?.[0] ?? ''
    report.value.test_end = v?.[1] ?? ''
    markDirty()
  },
})

// 实际人天：结束日期 - 开始日期 + 1（含首尾；系统自动计算，随用户手动修改的时间联动）
const actualMandays = computed(() => {
  const start = report.value?.test_start
  const end = report.value?.test_end
  if (!start || !end) return 0
  const diff = dayjs(end).diff(dayjs(start), 'day')
  return diff >= 0 ? diff + 1 : 0
})

function markDirty() {
  saveState.value = '有未保存修改'
  // 防抖自动保存草稿
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => save(true), 3000)
}

async function loadVulnStates() {
  const { data } = await client.get(`/reports/${route.params.id}/vuln-states`)
  const map: Record<number, any> = {}
  for (const v of data) {
    map[v.vul_id] = { ...v }
  }
  vulnStates.value = map
}

// 报告编辑页下拉框直接调整关联漏洞字段（状态/等级/类型/所在层），修改即时保存
const FIELD_META_KEYS: Record<string, string> = { level: 'vul_level', vul_type: 'vul_type' }

async function changeVulnField(vulId: number, field: string, value: number) {
  await client.patch(`/vulns/${vulId}/fields`, { [field]: value })
  const label = field === 'status' ? statusName(value) : (meta.value?.[FIELD_META_KEYS[field]]?.[value] ?? value)
  ElMessage.success(`${FIELD_LABELS[field]}已更新为「${label}」`)
  await loadVulnStates()
}

// 章节导航：点击跳转到对应章节编辑区域
const activeSection = ref<number | null>(null)
// 拖拽排序状态：当前拖拽项索引 / 悬停目标项索引 / 指示线插入位置 / 拖拽结束抑制一次点击
const dragIndex = ref<number | null>(null)
const overIndex = ref<number | null>(null)
const dropLineIndex = ref<number | null>(null)
const navScrollRef = ref<HTMLElement | null>(null)
let suppressClick = false

function scrollToSection(i: number) {
  // 拖拽结束瞬间浏览器可能补发 click，丢弃以免误跳转
  if (suppressClick) { suppressClick = false; return }
  activeSection.value = i
  document.getElementById(`section-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onDragStart(i: number, e: DragEvent) {
  dragIndex.value = i
  overIndex.value = null
  dropLineIndex.value = null
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(i))
  }
}

function onDragOver(i: number, e: DragEvent) {
  if (dragIndex.value === null || dragIndex.value === i) return
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  // 落在目标项上半则插到其前，否则插到其后；并换算为移除拖拽项后的数组位置
  let line = e.clientY < rect.top + rect.height / 2 ? i : i + 1
  if (dragIndex.value < line) line -= 1
  dropLineIndex.value = line
  // 靠近导航列表上下边缘时自动滚动，便于把章节拖到列表两端之外的位置
  const sc = navScrollRef.value
  if (sc) {
    const scRect = sc.getBoundingClientRect()
    if (e.clientY < scRect.top + 24) sc.scrollTop -= 8
    else if (e.clientY > scRect.bottom - 24) sc.scrollTop += 8
  }
}

function onDragEnter(i: number) {
  if (dragIndex.value === null || dragIndex.value === i) return
  overIndex.value = i
}

function onDragLeave(i: number, e: DragEvent) {
  // dragleave 在子元素间移动会频繁触发，仅当真正离开当前项时清除高亮
  const to = e.relatedTarget as Node | null
  if (!to || !(e.currentTarget as HTMLElement).contains(to)) {
    if (overIndex.value === i) overIndex.value = null
  }
}

function onDrop() {
  const from = dragIndex.value
  const line = dropLineIndex.value
  if (from !== null && line !== null && line !== from) {
    const arr = report.value.sections
    const [item] = arr.splice(from, 1)
    // 插入到 line 处（deleteCount=0），仅移动不删除任何其他章节
    arr.splice(line, 0, item)
    // 同步修正章节导航高亮索引，使其仍指向原章节
    const a = activeSection.value
    if (a !== null) {
      if (a === from) {
        activeSection.value = line
      } else {
        let na = a
        if (from < na) na -= 1
        if (line <= na) na += 1
        activeSection.value = na
      }
    }
    markDirty()
  }
  onDragEnd()
}

function onDragEnd() {
  dragIndex.value = null
  overIndex.value = null
  dropLineIndex.value = null
  suppressClick = true
  window.setTimeout(() => { suppressClick = false }, 0)
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

async function removeJob(job: any) {
  await client.delete(`/reports/exports/${job.id}`)
  ElMessage.success('导出记录已删除')
  await loadJobs()
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

function removeSection(i: number) {
  report.value.sections.splice(i, 1)
  // 同步修正导航高亮索引，保持与拖拽排序共用同一套索引
  const a = activeSection.value
  if (a === i) activeSection.value = null
  else if (a !== null && a > i) activeSection.value = a - 1
  markDirty()
}

function move(i: number, dir: number) {
  const arr = report.value.sections
  ;[arr[i], arr[i + dir]] = [arr[i + dir], arr[i]]
  // 同步修正导航高亮索引
  const a = activeSection.value
  if (a === i) activeSection.value = i + dir
  else if (a === i + dir) activeSection.value = i
  markDirty()
}

// 复测记录变更（新增/编辑/删除/状态调整）后刷新漏洞状态，保持侧栏状态标签与字段下拉框同步
async function onRetestChanged() {
  await loadVulnStates()
}

async function onVulnFormSaved() {
  vulnFormVisible.value = false
  ElMessage.success('漏洞已录入')
}

async function doExport(fmt: string) {
  if (saveState.value !== '已保存') await save(true)
  // 重复导出检测：报告内容与最近一次同格式导出完全一致时，确认后仍可继续
  try {
    const { data } = await client.post(`/reports/${route.params.id}/export-check`, { fmt })
    if (data.duplicate) {
      const lastStatusName = data.last_status === 'done' ? '已完成' : data.last_status || ''
      const sizeText = data.last_file_size != null ? `（${(data.last_file_size / 1024).toFixed(1)} KB）` : ''
      const message =
        `检测到该报告已有相同的导出记录：\n` +
        `· 报告：《${data.report_title || report.value.title}》\n` +
        `· 导出格式：${(data.fmt || fmt).toUpperCase()}\n` +
        `· 导出版本：v${data.last_version ?? ''}\n` +
        `· 已存在记录：${fmtDateTime(data.last_time)}（${lastStatusName}）\n` +
        `· 导出文件：${data.last_file_name || '-'}${sizeText}\n\n` +
        `是否仍要继续导出？`
      const ok = await ElMessageBox.confirm(message, '检测到重复导出', {
        confirmButtonText: '继续导出',
        cancelButtonText: '取消',
        type: 'warning',
        width: 460,
      }).then(() => true).catch(() => false)
      if (!ok) return
    }
  } catch {
    // 检查接口异常时不阻断导出
  }
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
    a.download = `${job.title || report.value.title}.${job.fmt}`
    a.click()
    URL.revokeObjectURL(url)
    // 目录域为占位：提示用户手动更新域或打开 WPS/Word 自动更新（可勾选不再显示）
    if (job.fmt === 'docx' && !job.toc_auto_updated) {
      showTocNotice()
    }
  })
}

onMounted(async () => {
  await load()
  meta.value = await auth.fetchMeta()
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
