<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索系统 / 资产归属 / 被通报单位 / 漏洞名称" clearable class="!w-72"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button type="primary" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增远程检测
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="70"
                       :index="(i: number) => (page - 1) * 20 + i + 1" />
      <el-table-column prop="notice_time" label="通报时间" width="110" sortable="custom" />
      <el-table-column prop="system_name" label="系统名称" width="150" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="department" label="资产归属" width="130" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="notified_unit" label="被通报单位" width="150" show-overflow-tooltip />
      <el-table-column prop="is_external" label="外部项目" width="90" sortable="custom">
        <template #default="{ row }">
          <span class="tl-tag" :style="row.is_external ? softStyle(STAT_CARD_COLORS.blue) : softStyle(STAT_CARD_COLORS.gray)">
            {{ row.is_external ? '是' : '否' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="vuln_name" label="漏洞名称" min-width="180" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="vuln_type" label="漏洞类型" width="120" show-overflow-tooltip />
      <el-table-column prop="appeal_status" label="申诉状态" width="100" sortable="custom">
        <template #default="{ row }">
          <span class="tl-tag" :style="appealStatusStyle(row.appeal_status)">
            {{ appealStatusLabel(row.appeal_status) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="申诉报告" width="90">
        <template #default="{ row }">
          <el-button v-if="row.appeal_file_name" size="small" type="primary" link @click="downloadAppeal(row)">
            下载
          </el-button>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="appeal_method" label="申诉方式" width="130" show-overflow-tooltip />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该记录？" @confirm="remove(row)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无远程检测记录，点击「新增远程检测」创建" :image-size="80" />
      </template>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑远程检测' : '新增远程检测'" width="620px">
    <el-form :model="form" label-width="100px">
      <el-form-item label="系统名称" required>
        <el-input v-model="form.system_name" placeholder="被检系统名称" />
      </el-form-item>
      <div class="grid grid-cols-2 gap-x-4">
        <el-form-item label="通报时间">
          <el-date-picker v-model="form.notice_time" type="month" value-format="YYYY-MM"
                          placeholder="选择通报月份" class="w-full" />
        </el-form-item>
        <el-form-item label="资产归属">
          <el-input v-model="form.department" />
        </el-form-item>
        <el-form-item label="被通报单位">
          <el-input v-model="form.notified_unit" />
        </el-form-item>
        <el-form-item label="是否外部项目">
          <el-switch v-model="form.is_external" active-text="是" inactive-text="否" />
        </el-form-item>
        <el-form-item label="漏洞名称">
          <el-input v-model="form.vuln_name" />
        </el-form-item>
        <el-form-item label="漏洞类型">
          <el-input v-model="form.vuln_type" />
        </el-form-item>
        <el-form-item label="申诉状态">
          <el-select v-model="form.appeal_status" clearable placeholder="未申诉" class="w-full">
            <el-option label="申诉成功" value="success" />
            <el-option label="申诉失败" value="fail" />
          </el-select>
        </el-form-item>
        <el-form-item label="申诉方式">
          <el-input v-model="form.appeal_method" />
        </el-form-item>
      </div>
      <el-form-item label="申诉报告">
        <div class="w-full flex flex-col gap-2">
          <div v-if="form.appeal_file_name" class="flex items-center gap-2">
            <el-button v-if="form.id" size="small" type="primary" link @click="downloadAppeal(form)">
              <el-icon class="mr-1"><Document /></el-icon>{{ form.appeal_file_name }}
            </el-button>
            <span v-else class="text-sm">{{ form.appeal_file_name }}</span>
            <el-button size="small" type="danger" link @click="clearAppeal">移除</el-button>
          </div>
          <el-upload :http-request="uploadAppeal" :show-file-list="false"
                     accept=".pdf,.doc,.docx,.xls,.xlsx,.zip,.rar,.jpg,.jpeg,.png">
            <el-button size="small" plain>
              <el-icon class="mr-1"><Upload /></el-icon>上传申诉报告
            </el-button>
          </el-upload>
          <span class="text-xs text-gray-400">支持 Word / PDF / 图片 / 压缩包，不超过 20MB</span>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!form.system_name" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Plus, Search, Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import { STAT_CARD_COLORS, softStyle } from '../utils/colors'

const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const sort = reactive<{ prop: string; order: string }>({ prop: '', order: '' })
const loading = ref(false)
const dialogVisible = ref(false)

const emptyForm = () => ({
  id: null as number | null,
  system_name: '',
  notice_time: '',
  department: '',
  notified_unit: '',
  is_external: false,
  vuln_name: '',
  vuln_type: '',
  appeal_status: '',
  appeal_method: '',
  appeal_file_name: '',
  appeal_file_path: '',
  appeal_file_size: 0,
})
const form = ref(emptyForm())

const appealStatusLabel = (s: string) =>
  s === 'success' ? '申诉成功' : s === 'fail' ? '申诉失败' : '未申诉'
const appealStatusStyle = (s: string) =>
  s === 'success' ? softStyle(STAT_CARD_COLORS.green)
    : s === 'fail' ? softStyle(STAT_CARD_COLORS.red) : softStyle(STAT_CARD_COLORS.gray)

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/remote-testings', {
      params: { search: search.value, page: p, size: 20, sort: sort.prop, order: sort.order },
    })
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

async function openDialog(row?: any) {
  form.value = row ? { ...emptyForm(), ...row } : emptyForm()
  dialogVisible.value = true
}

async function uploadAppeal(options: any) {
  const fd = new FormData()
  fd.append('file', options.file)
  const { data } = await client.post('/remote-testings/upload-appeal', fd)
  form.value.appeal_file_name = data.name
  form.value.appeal_file_path = data.path
  form.value.appeal_file_size = data.size
  ElMessage.success('附件上传成功')
}

function clearAppeal() {
  form.value.appeal_file_name = ''
  form.value.appeal_file_path = ''
  form.value.appeal_file_size = 0
}

async function downloadAppeal(row: any) {
  const { data } = await client.get(`/remote-testings/${row.id}/appeal`, { responseType: 'blob' })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = row.appeal_file_name || 'appeal'
  a.click()
  URL.revokeObjectURL(url)
}

async function save() {
  const body = { ...form.value }
  if (form.value.id) {
    await client.put(`/remote-testings/${form.value.id}`, body)
  } else {
    await client.post('/remote-testings', body)
  }
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await load()
}

async function remove(row: any) {
  await client.delete(`/remote-testings/${row.id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(() => load(1))
</script>
