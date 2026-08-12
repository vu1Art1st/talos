<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4 flex-wrap">
      <el-input v-model="search" placeholder="搜索系统 / 子系统 / 部门 / URL" clearable class="!w-72"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button @click="downloadTemplate">
        <el-icon class="mr-1"><Download /></el-icon>下载模板
      </el-button>
      <el-upload :show-file-list="false" accept=".xlsx" :http-request="importExcel">
        <el-button :loading="importing">
          <el-icon class="mr-1"><Upload /></el-icon>导入Excel
        </el-button>
      </el-upload>
      <el-button @click="exportExcel">
        <el-icon class="mr-1"><Download /></el-icon>导出Excel
      </el-button>
      <el-button type="primary" @click="openEdit()">
        <el-icon class="mr-1"><Plus /></el-icon>新建资产
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="70"
                       :index="(i: number) => (page - 1) * 20 + i + 1" />
      <el-table-column prop="name" label="系统命名" min-width="150" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="sub_system" label="子系统" min-width="110" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="department" label="部门" min-width="110" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="system_type" label="系统类型" min-width="120" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.system_type || '-' }}</template>
      </el-table-column>
      <el-table-column label="公网URL" min-width="200">
        <template #default="{ row }">
          <div v-for="(u, i) in (row.public_urls ?? []).slice(0, 2)" :key="i" class="flex items-center gap-1">
            <span class="truncate">{{ u.url }}</span>
            <span class="tl-tag" :style="softStyle(urlTagMeta(u.tag).color)">{{ urlTagMeta(u.tag).label }}</span>
          </div>
          <span v-if="(row.public_urls ?? []).length > 2" class="text-xs text-gray-400">
            等 {{ row.public_urls.length }} 条
          </span>
        </template>
      </el-table-column>
      <el-table-column label="负责人" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          {{ (row.owners ?? []).map((o: any) => o.name).join('、') || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90" sortable="custom">
        <template #default="{ row }">
          <span class="tl-tag" :style="softStyle(assetStatusMeta(row.status).color)">{{ assetStatusMeta(row.status).label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确认删除该资产？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无资产记录，可下载模板后导入或直接新建" :image-size="80" />
      </template>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>

  <AssetFormDialog v-model:visible="dialogVisible" :asset="editing" @saved="load()" />
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search, Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import AssetFormDialog from '../components/AssetFormDialog.vue'
import { useAuthStore } from '../stores/auth'
import { assetStatusMeta, softStyle, urlTagMeta } from '../utils/colors'

const auth = useAuthStore()
const meta = ref<any>(null)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const sort = reactive<{ prop: string; order: string }>({ prop: '', order: '' })
const loading = ref(false)
const importing = ref(false)
const dialogVisible = ref(false)
const editing = ref<any>(null)

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/assets', { params: { search: search.value, page: p, size: 20, sort: sort.prop, order: sort.order } })
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

function openEdit(row?: any) {
  editing.value = row ?? null
  dialogVisible.value = true
}

async function remove(id: number) {
  await client.delete(`/assets/${id}`)
  ElMessage.success('删除成功')
  await load()
}

function saveBlob(data: Blob, filename: string) {
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function downloadTemplate() {
  const { data } = await client.get('/assets/import/template', { responseType: 'blob' })
  saveBlob(data, '资产导入模板.xlsx')
}

async function exportExcel() {
  const { data } = await client.get('/assets/export', {
    params: { search: search.value }, responseType: 'blob',
  })
  saveBlob(data, '资产导出.xlsx')
}

async function importExcel(options: any) {
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', options.file)
    const { data } = await client.post('/assets/import', fd)
    if (data.failed > 0) {
      await ElMessageBox.alert(
        `共 ${data.total} 行，成功 ${data.success} 行，失败 ${data.failed} 行：<br/>${data.errors.join('<br/>')}`,
        '导入结果', { dangerouslyUseHTMLString: true },
      )
    } else {
      ElMessage.success(`成功导入 ${data.success} 条资产`)
    }
    await load(1)
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load(1)
})
</script>
