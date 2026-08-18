<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-3">
      <el-upload ref="uploadRef" :auto-upload="false" multiple accept=".docx" :on-change="onFileChange"
                 :on-remove="onFileRemove" :on-exceed="onFileExceed" :limit="20" :file-list="fileList"
                 drag class="!flex-1">
        <el-icon class="mr-1"><Upload /></el-icon>选择报告文件（可多选）
        <template #tip>
          <div class="text-xs text-gray-400">支持一次选择多份 .docx（标准模板或平台导出的渗透测试/复测报告），选好后点「开始上传」批量入库解析</div>
        </template>
      </el-upload>
      <div class="flex flex-col gap-1">
        <el-button type="primary" :disabled="!fileList.length || uploading" @click="doUpload" :loading="uploading">
          <el-icon class="mr-1"><Upload /></el-icon>{{ uploading ? `上传中 ${uploaded}/${fileList.length}` : `开始上传（${fileList.length} 份）` }}
        </el-button>
        <el-button @click="downloadTemplate" :disabled="uploading">
          <el-icon class="mr-1"><Download /></el-icon>下载导入模板
        </el-button>
      </div>
    </div>
    <div class="mb-4 text-gray-400 text-sm">
      支持标准导入模板及平台导出的渗透测试（复测）报告 .docx，上传后自动解析；复测报告确认入库时将自动生成渗透测试工单。同一工单下相同名称的漏洞将自动去重合并。
    </div>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="80"
                       :index="(i: number) => (query.page - 1) * query.size + i + 1" />
      <el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="status" label="状态" width="120" sortable="custom">
        <template #default="{ row }">
          <span class="tl-tag" :style="softStyle(importStatusMeta(row.status).color)">{{ importStatusMeta(row.status).label }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="total" label="解析条数" width="100" sortable="custom" />
      <el-table-column label="失败原因" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.error || '-' }}</template>
      </el-table-column>
      <el-table-column prop="create_time" label="上传时间" width="170" sortable="custom">
        <template #default="{ row }">{{ fmtDateTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link :disabled="row.status === 'parsing' || row.status === 'pending'"
                     @click="router.push(`/reports/imports/${row.id}`)">预览确认</el-button>
          <el-button size="small" type="primary" link @click="previewRef?.open(`/imports/${row.id}/preview`, row.filename)">预览</el-button>
          <el-popconfirm title="确认删除该批次？" @confirm="removeBatch(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无导入记录，上传 Word 文档开始解析" :image-size="80" />
      </template>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="query.size" :current-page="query.page" @current-change="load" />
    </div>
  </el-card>

  <PdfPreviewDialog ref="previewRef" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import PdfPreviewDialog from '../components/PdfPreviewDialog.vue'
import { importStatusMeta, softStyle } from '../utils/colors'
import { fmtDateTime } from '../utils/format'

const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const previewRef = ref<InstanceType<typeof PdfPreviewDialog>>()
const query = reactive({ page: 1, size: 20, sort: '', order: '' })
const uploadRef = ref()
const fileList = ref<any[]>([])
const uploading = ref(false)
const uploaded = ref(0)
let timer: number | undefined



async function load(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const { data } = await client.get('/imports', { params: { ...query } })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSortChange({ prop, order }: any) {
  query.sort = order ? prop : ''
  query.order = order === 'ascending' ? 'asc' : order === 'descending' ? 'desc' : ''
  load(1)
}

function onFileChange(file: any) {
  if (file.status === 'ready') fileList.value.push(file)
}

function onFileRemove(file: any) {
  fileList.value = fileList.value.filter((f) => f.uid !== file.uid)
}

function onFileExceed() {
  ElMessage.warning('单次最多上传 20 份报告')
}

async function doUpload() {
  if (!fileList.value.length || uploading.value) return
  uploading.value = true
  uploaded.value = 0
  const total = fileList.value.length
  let failed = 0
  try {
    for (const f of fileList.value) {
      const form = new FormData()
      form.append('file', f.raw)
      try {
        await client.post('/imports', form)
      } catch (e: any) {
        failed++
        ElMessage.error(`「${f.name}」上传失败：${e?.response?.data?.detail || e?.message || '未知错误'}`)
      }
      uploaded.value++
    }
    if (failed) {
      ElMessage.warning(`上传完成：成功 ${total - failed} 份，失败 ${failed} 份`)
    } else {
      ElMessage.success(`成功上传 ${total} 份报告，后台解析中`)
    }
    fileList.value = []
    uploadRef.value?.clearFiles()
    await load(1)
  } finally {
    uploading.value = false
    uploaded.value = 0
  }
}

async function downloadTemplate() {
  const resp = await client.get('/imports/template', { responseType: 'blob' })
  const url = URL.createObjectURL(resp.data)
  const a = document.createElement('a')
  a.href = url
  a.download = '漏洞导入模板.docx'
  a.click()
  URL.revokeObjectURL(url)
}

async function removeBatch(id: number) {
  await client.delete(`/imports/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(async () => {
  await load(1)
  // 有批次在解析时自动刷新
  timer = window.setInterval(() => {
    if (items.value.some((b) => b.status === 'pending' || b.status === 'parsing')) load()
  }, 2000)
})

onBeforeUnmount(() => window.clearInterval(timer))
</script>
