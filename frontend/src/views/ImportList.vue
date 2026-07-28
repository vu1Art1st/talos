<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-upload :show-file-list="false" accept=".docx" :http-request="doUpload">
        <el-button type="primary">
          <el-icon class="mr-1"><Upload /></el-icon>上传 Word 文档
        </el-button>
      </el-upload>
      <el-button @click="downloadTemplate">
        <el-icon class="mr-1"><Download /></el-icon>下载导入模板
      </el-button>
      <span class="text-gray-400 text-sm">仅支持按固定模板编写的 .docx 文档，上传后自动解析</span>
    </div>

    <el-table v-loading="loading" :data="items" stripe>
      <el-table-column prop="id" label="批次" width="80" />
      <el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip />
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusName(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_count" label="解析条数" width="100" />
      <el-table-column label="失败原因" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.error || '-' }}</template>
      </el-table-column>
      <el-table-column label="上传时间" width="170">
        <template #default="{ row }">{{ fmt(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link :disabled="row.status === 'parsing' || row.status === 'pending'"
                     @click="router.push(`/reports/imports/${row.id}`)">预览确认</el-button>
          <el-popconfirm title="确认删除该批次？" @confirm="removeBatch(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="query.size" :current-page="query.page" @current-change="load" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'

const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, size: 20 })
let timer: number | undefined

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')
const statusName = (s: string) =>
  ({ pending: '排队中', parsing: '解析中', parsed: '待确认', confirmed: '已入库', failed: '解析失败' })[s] ?? s
const statusTag = (s: string) =>
  ({ pending: 'info', parsing: 'warning', parsed: 'primary', confirmed: 'success', failed: 'danger' })[s] ?? 'info'

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

async function doUpload(opt: any) {
  const form = new FormData()
  form.append('file', opt.file)
  await client.post('/imports', form)
  ElMessage.success('上传成功，后台解析中')
  await load(1)
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
