<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索报告标题 / 项目" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button :disabled="!selected.length" :loading="batchDownloading" @click="batchDownload">
        <el-icon class="mr-1"><Download /></el-icon>批量下载（{{ selected.length }}）
      </el-button>
      <el-button v-if="auth.hasPerm('import:manage')" @click="router.push('/reports/imports')">
        <el-icon class="mr-1"><Upload /></el-icon>Word 导入
      </el-button>
      <el-button type="primary" @click="fromVulnsVisible = true">
        <el-icon class="mr-1"><MagicStick /></el-icon>从漏洞生成
      </el-button>
      <el-button @click="createBlank">
        <el-icon class="mr-1"><Plus /></el-icon>新建空白报告
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange"
              @selection-change="onSelectionChange" @expand-change="onExpandChange"
              row-key="id">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="px-6 py-2">
            <div v-if="exportJobs[row.id]?.length" class="flex flex-col gap-1">
              <div v-for="job in exportJobs[row.id]" :key="job.id" class="flex items-center gap-2 text-xs">
                <span class="uppercase font-mono text-gray-400">{{ job.fmt }}</span>
                <el-tag size="small"
                        :type="job.status === 'done' ? 'success' : job.status === 'failed' ? 'danger' : 'warning'">
                  {{ job.status === 'done' ? '已完成' : job.status === 'failed' ? '失败' : '生成中' }}
                </el-tag>
                <el-tooltip v-if="job.status === 'failed'" :content="job.error || '生成失败'">
                  <el-icon color="#F56C6C"><WarningFilled /></el-icon>
                </el-tooltip>
                <span class="text-gray-500 truncate">{{ job.title || row.title }}</span>
                <span class="text-gray-400">{{ fmt(job.create_time) }}</span>
                <div class="flex-1" />
                <el-button v-if="job.status === 'done'" size="small" type="primary" link
                           @click="downloadJob(job)">下载</el-button>
                <el-popconfirm v-if="job.status !== 'pending' && job.status !== 'running'"
                               title="确认删除该导出记录？文件将一并移除" width="240"
                               @confirm="removeExportJob(row, job)">
                  <template #reference>
                    <el-button size="small" type="danger" link>删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </div>
            <div v-else class="text-xs text-gray-400">
              {{ exportLoading[row.id] ? '加载中…' : '暂无导出记录' }}
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column type="index" label="序号" width="70"
                       :index="(i: number) => (page - 1) * 20 + i + 1" />
      <el-table-column prop="title" label="报告标题" min-width="240" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="project_name" label="项目" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="author" label="作者" width="120" sortable="custom" />
      <el-table-column prop="status" label="状态" width="90" sortable="custom">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusName(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="70" sortable="custom" />
      <el-table-column prop="create_time" label="生成时间" width="170" sortable="custom">
        <template #default="{ row }">{{ fmt(row.create_time) }}</template>
      </el-table-column>
      <el-table-column prop="update_time" label="更新时间" width="170" sortable="custom">
        <template #default="{ row }">{{ fmt(row.update_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="190" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="router.push(`/reports/${row.id}`)">编辑</el-button>
          <el-button size="small" type="warning" link @click="retest(row.id)">
            复测
          </el-button>
          <el-popconfirm title="确认删除该报告？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>

  <el-dialog v-model="fromVulnsVisible" title="从漏洞记录生成报告" width="640px">
    <el-form label-width="100px">
      <el-form-item label="关联渗透测试计划">
        <el-select v-model="genPlanId" clearable filterable class="w-full"
                   placeholder="可选，关联后联动计划状态" @change="onPlanChange">
          <el-option v-for="p in plans" :key="p.id" :label="p.system_name" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="报告标题">
        <el-input v-model="genTitle" placeholder="例如：XX系统渗透测试报告" />
      </el-form-item>
      <el-form-item label="选择漏洞">
        <el-select v-model="genVulIds" multiple filterable class="w-full" placeholder="可多选">
          <el-option v-for="v in vulns" :key="v.id" :label="v.title" :value="v.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="fromVulnsVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!genTitle || !genVulIds.length" @click="generate">生成</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { showTocNotice } from '../utils/tocNotice'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const sort = reactive<{ prop: string; order: string }>({ prop: '', order: '' })
const loading = ref(false)
const fromVulnsVisible = ref(false)
const genTitle = ref('')
const genVulIds = ref<number[]>([])
const genPlanId = ref<number | null>(null)
const vulns = ref<any[]>([])
const plans = ref<any[]>([])
const selected = ref<any[]>([])
const batchDownloading = ref(false)
// 报告导出版本历史（展开行懒加载）：{reportId: ExportJob[]}
const exportJobs = ref<Record<number, any[]>>({})
const exportLoading = ref<Record<number, boolean>>({})

function onSelectionChange(rows: any[]) {
  selected.value = rows
}

// 懒加载该报告的导出历史版本列表（展开行时调用，已有缓存则跳过）
async function loadExportJobs(reportId: number) {
  if (exportJobs.value[reportId]?.length) return
  exportLoading.value[reportId] = true
  try {
    const { data } = await client.get(`/reports/${reportId}/exports`)
    exportJobs.value[reportId] = data
  } finally {
    exportLoading.value[reportId] = false
  }
}

async function onExpandChange(row: any, expandedRows: any[]) {
  if (expandedRows.some((r) => r.id === row.id)) await loadExportJobs(row.id)
}

async function removeExportJob(row: any, job: any) {
  await client.delete(`/reports/exports/${job.id}`)
  ElMessage.success('导出记录已删除')
  exportJobs.value[row.id] = (exportJobs.value[row.id] || []).filter((j: any) => j.id !== job.id)
}

async function downloadJob(job: any) {
  const resp = await client.get(`/reports/exports/${job.id}/download`, { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `${job.title || 'report'}.${job.fmt}`
  a.click()
  URL.revokeObjectURL(url)
  // 目录域为占位：提示用户手动更新域或打开 WPS/Word 自动更新（可勾选不再显示）
  if (job.fmt === 'docx' && !job.toc_auto_updated) {
    showTocNotice()
  }
}

async function fetchJobStatus(jobIds: string) {
  const { data } = await client.get('/reports/export-jobs/status', { params: { job_ids: jobIds } })
  return data
}

async function downloadZip(jobIds: string) {
  const resp = await client.get('/reports/batch-download', {
    params: { job_ids: jobIds }, responseType: 'blob',
  })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = '测试报告批量下载.zip'
  a.click()
  URL.revokeObjectURL(url)
}

async function batchDownload() {
  const ids = selected.value.map((r) => r.id)
  if (!ids.length) return
  batchDownloading.value = true
  try {
    const { data } = await client.post('/reports/batch-export', { report_ids: ids, fmt: 'docx' })
    if (!data.length) {
      ElMessage.warning('未找到可导出的报告')
      return
    }
    const jobIds = data.map((j: any) => j.job_id).join(',')
    for (let i = 0; i < 120; i++) {
      const all: any[] = await fetchJobStatus(jobIds)
      if (all.some((j: any) => j.status === 'pending' || j.status === 'running')) {
        await new Promise((r) => setTimeout(r, 1500))
        continue
      }
      const done = all.filter((j: any) => j.status === 'done')
      if (done.length < all.length) {
        ElMessage.warning(`部分报告导出失败（${all.length - done.length} 份），已跳过失败项`)
      }
      if (done.length) {
        await downloadZip(jobIds)
        // 目录域为占位：提示用户手动更新域或打开 WPS/Word 自动更新（可勾选不再显示）
        if (done.some((j: any) => j.fmt === 'docx' && !j.toc_auto_updated)) {
          showTocNotice()
        }
      } else ElMessage.error('所选报告均导出失败，请检查后重试')
      return
    }
    ElMessage.error('导出超时，请稍后重试')
  } finally {
    batchDownloading.value = false
  }
}

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

const statusName = (s: string) => (s === 'final' ? '已定稿' : '草稿')
const statusTag = (s: string) => (s === 'final' ? 'primary' : 'info')

async function retest(id: number) {
  const { data } = await client.post(`/reports/${id}/retest`)
  ElMessage.success('已发起复测，已自动生成复测报告')
  router.push(`/reports/${data.id}`)
}

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/reports', { params: { search: search.value, page: p, size: 20, sort: sort.prop, order: sort.order } })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSortChange({ prop, order }: any) {
  sort.prop = order ? prop : ''
  sort.order = order === 'ascending' ? 'asc' : order === 'descending' ? 'desc' : ''
  load(1)
}

async function createBlank() {
  const { data } = await client.post('/reports', { title: '未命名报告', sections: [] })
  router.push(`/reports/${data.id}`)
}

async function generate() {
  // 相似性检查：基础信息与所选漏洞最后编辑时间与历史报告完全一致时，需用户确认继续
  try {
    const { data } = await client.post('/reports/similarity-check', {
      title: genTitle.value,
      vul_ids: genVulIds.value,
      testing_plan_id: genPlanId.value,
    })
    if (data.similar) {
      const ok = await ElMessageBox.confirm(
        `检测到与历史报告《${genTitle.value}》高度相似（标题、所选漏洞及漏洞最后编辑时间均未变化），是否仍要继续生成？`,
        '生成高度相似报告',
        { confirmButtonText: '仍要生成', cancelButtonText: '取消', type: 'warning' },
      ).then(() => true).catch(() => false)
      if (!ok) return
    }
  } catch {
    // 检查接口异常时不阻断生成流程
  }
  const resp = await client.post('/reports/from-vulns', {
    title: genTitle.value,
    vul_ids: genVulIds.value,
    testing_plan_id: genPlanId.value,
  })
  ElMessage.success('报告已生成')
  fromVulnsVisible.value = false
  router.push(`/reports/${resp.data.id}`)
}

async function remove(id: number) {
  await client.delete(`/reports/${id}`)
  ElMessage.success('删除成功')
  await load()
}

// 选中计划后：漏洞列表改为该计划关联漏洞并默认全选，标题预填
async function onPlanChange(planId: number | null) {
  if (!planId) {
    const { data } = await client.get('/vulns', { params: { size: 100 } })
    vulns.value = data.items
    return
  }
  const { data } = await client.get('/vulns', { params: { testing_plan_id: planId, size: 100 } })
  vulns.value = data.items
  genVulIds.value = data.items.map((v: any) => v.id)
  const plan = plans.value.find((p) => p.id === planId)
  // 需求8：自动命名「yyyymmdd+测试系统名称+渗透测试报告」
  if (plan && !genTitle.value) genTitle.value = `${dayjs().format('YYYYMMDD')}${plan.system_name}渗透测试报告`
}

watch(fromVulnsVisible, async (v) => {
  if (!v) return
  if (!vulns.value.length) {
    const { data } = await client.get('/vulns', { params: { size: 100 } })
    vulns.value = data.items
  }
  if (!plans.value.length) {
    const { data } = await client.get('/testing-plans', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
    plans.value = data.items
  }
})

onMounted(async () => {
  await load(1)
  // 从测试计划「生成报告」进入：自动打开对话框并预选计划
  const genPlan = Number(route.query.gen_plan)
  if (genPlan) {
    fromVulnsVisible.value = true
    const { data } = await client.get('/testing-plans', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
    plans.value = data.items
    genPlanId.value = genPlan
    await onPlanChange(genPlan)
  }
})
</script>
