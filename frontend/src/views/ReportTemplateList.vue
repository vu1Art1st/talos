<template>
  <div class="flex flex-col gap-4">
    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold">报告模板中心</span>
          <span class="text-xs text-gray-400">
            模板按名称 + 版本管理；同一名称同时只有一个启用版本，回滚＝重新启用旧版本
          </span>
          <div class="flex-1" />
          <el-select v-model="filterType" placeholder="全部类型" clearable class="!w-[150px]" @change="load">
            <el-option v-for="o in typeOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-button type="primary" class="btn-min" @click="openUpload">
            <el-icon class="mr-1"><Upload /></el-icon>上传模板
          </el-button>
        </div>
      </template>

      <el-empty v-if="!items.length" description="暂无模板，导出将使用系统内置默认模板" :image-size="70" />
      <el-table v-else :data="items" stripe>
        <el-table-column prop="name" label="模板名称" min-width="200" />
        <el-table-column label="适用类型" width="140">
          <template #default="{ row }">{{ reportTemplateTypeName(row.report_type) }}</template>
        </el-table-column>
        <el-table-column label="版本" width="90">
          <template #default="{ row }"><span class="num">v{{ row.version }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <span class="dot-tag" :style="dotStyle(row.is_active ? STAT_CARD_COLORS.green : STAT_CARD_COLORS.gray)">
              <i></i>{{ row.is_active ? '启用中' : '未启用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="锚点校验" width="120">
          <template #default="{ row }">
            <el-popover v-if="row.anchors?.length" placement="top" width="280" trigger="hover">
              <template #reference>
                <span class="text-xs" style="color: var(--tl-brand-mint)">{{ row.anchors.length }} 个锚点</span>
              </template>
              <div v-for="a in row.anchors" :key="a.index" class="text-xs">{{ a.index }}. {{ a.desc }}</div>
            </el-popover>
            <span v-else class="text-xs text-gray-400">-</span>
          </template>
        </el-table-column>
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }"><span class="num">{{ fmtDateTime(row.create_time) }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="290" fixed="right" class-name="op-col">
          <template #default="{ row }">
            <el-button size="small" type="primary" link v-if="!row.is_active" @click="activate(row)">
              {{ row.version > 1 ? '回滚启用' : '启用' }}
            </el-button>
            <el-button size="small" link @click="validate(row)">校验</el-button>
            <el-button size="small" link @click="preview(row)">试生成</el-button>
            <el-button size="small" link @click="download(row)">下载</el-button>
            <el-popconfirm v-if="!row.is_active" title="删除该模板版本？" @confirm="remove(row)">
              <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <TlPagination v-model:page="page" v-model:size="size" :total="total"
                    @page-change="load" @size-change="onSizeChange" />
    </el-card>

    <el-dialog v-model="uploadVisible" title="上传报告模板" width="560px" :close-on-click-modal="false">
      <el-alert type="info" :closable="false" show-icon class="mb-3"
                title="模板需保持固定表序结构（封面 / 版本记录 / 适用性 / 目录 / 测试目标 / 时间与人员 / 风险问题汇总），否则发布会被阻止" />
      <el-form :model="uploadForm" label-width="100px">
        <el-form-item label="模板名称" required>
          <el-input v-model="uploadForm.name" maxlength="128" placeholder="同名将创建新版本" />
        </el-form-item>
        <el-form-item label="适用类型" required>
          <el-select v-model="uploadForm.report_type" class="w-full">
            <el-option v-for="o in typeOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="模板文件" required>
          <el-upload :auto-upload="false" :limit="1" accept=".docx" :on-change="onFileChange"
                     :on-remove="() => (uploadFile = null)" :file-list="fileList">
            <el-button>选择 .docx 文件</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadForm.remark" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
        <el-form-item label="立即发布">
          <el-switch v-model="uploadForm.publish" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="doUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import TlPagination from '../components/TlPagination.vue'
import { useAuthStore } from '../stores/auth'
import { dotStyle, reportTemplateTypeName, reportTemplateTypeOptions, STAT_CARD_COLORS } from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import { saveBlob } from '../utils/download'
import type { ReportTemplate } from '../types'

const auth = useAuthStore()
const items = ref<ReportTemplate[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const loading = ref(false)
const filterType = ref('')

const uploadVisible = ref(false)
const uploading = ref(false)
const uploadFile = ref<File | null>(null)
const fileList = ref<{ name: string }[]>([])
const uploadForm = reactive({ name: '', report_type: 'penetration', remark: '', publish: true })

const typeOptions = computed(() => reportTemplateTypeOptions())

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/report-templates', {
      params: { page: p, size: size.value, report_type: filterType.value || undefined },
    })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSizeChange(n: number) {
  size.value = n
  void load(1)
}

function openUpload() {
  uploadForm.name = ''
  uploadForm.report_type = 'penetration'
  uploadForm.remark = ''
  uploadForm.publish = true
  uploadFile.value = null
  fileList.value = []
  uploadVisible.value = true
}

function onFileChange(file: { raw?: File; name: string }) {
  uploadFile.value = file.raw ?? null
  fileList.value = [{ name: file.name }]
}

async function doUpload() {
  if (!uploadForm.name.trim()) return ElMessage.warning('请填写模板名称')
  if (!uploadFile.value) return ElMessage.warning('请选择 .docx 模板文件')
  const fd = new FormData()
  fd.append('file', uploadFile.value)
  fd.append('name', uploadForm.name.trim())
  fd.append('report_type', uploadForm.report_type)
  fd.append('remark', uploadForm.remark)
  fd.append('publish', String(uploadForm.publish))
  uploading.value = true
  try {
    await client.post('/report-templates', fd)
    uploadVisible.value = false
    ElMessage.success('模板已上传')
    await load(1)
  } finally {
    uploading.value = false
  }
}

async function activate(row: ReportTemplate) {
  await ElMessageBox.confirm(
    `启用「${row.name} v${row.version}」将停用同名的其他版本，确认继续？`, '启用模板版本', { type: 'warning' },
  )
  await client.post(`/report-templates/${row.id}/activate`)
  ElMessage.success('已启用')
  await load()
}

async function validate(row: ReportTemplate) {
  const { data } = await client.post(`/report-templates/${row.id}/validate`)
  if (data.ok) ElMessage.success(`占位符校验通过（${data.anchors.length} 个锚点）`)
  else ElMessage.error(`占位符缺失：${(data.missing ?? []).join('；')}`)
}

async function preview(row: ReportTemplate) {
  const { data } = await client.post(`/report-templates/${row.id}/preview`)
  const blob = (await client.get(data.url, { responseType: 'blob' })).data
  saveBlob(blob, `${row.name}-v${row.version}-试生成.docx`)
  ElMessage.success(data.msg || '示例报告已生成')
}

async function download(row: ReportTemplate) {
  const blob = (await client.get(`/report-templates/${row.id}/download`, { responseType: 'blob' })).data
  saveBlob(blob, row.original_filename || `${row.name}-v${row.version}.docx`)
}

async function remove(row: ReportTemplate) {
  await client.delete(`/report-templates/${row.id}`)
  ElMessage.success('已删除')
  await load()
}

onMounted(async () => {
  await auth.fetchMeta()
  await load()
})
</script>
