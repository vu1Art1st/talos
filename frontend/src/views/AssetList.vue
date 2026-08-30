<template>
  <div class="space-y-3">
    <FilterToolbar>
      <div class="tl-search-field">
        <el-input v-model="search" placeholder="搜索系统 / 子系统 / 部门 / URL" clearable
                  @keyup.enter="load(1)" @clear="load(1)">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <template #actions>
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
        <el-button type="primary" class="btn-min" @click="openEdit()">
          <el-icon class="mr-1"><Plus /></el-icon>新建资产
        </el-button>
      </template>
    </FilterToolbar>

    <el-card shadow="never" body-style="padding: 0 0 12px">
    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="64"
                       :index="(i: number) => (page - 1) * size + i + 1" />
      <el-table-column prop="name" label="系统命名" min-width="150" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="sub_system" label="子系统" min-width="110" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="department" label="部门" min-width="110" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="system_type" label="系统类型" min-width="120" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.system_type || '-' }}</template>
      </el-table-column>
      <el-table-column label="公网URL" min-width="200">
        <template #default="{ row }">
          <div v-for="(u, i) in (row.public_urls ?? []).slice(0, 2)" :key="i" class="flex items-center gap-1 min-w-0">
            <span class="truncate min-w-0 flex-1" :title="u.url">{{ u.url }}</span>
            <span class="ktag flex-none">{{ urlTagMeta(u.tag).label }}</span>
          </div>
          <el-popover v-if="(row.public_urls ?? []).length > 2" placement="right" :width="320" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link class="!p-0">等 {{ row.public_urls.length }} 条</el-button>
            </template>
            <div class="flex flex-col gap-1">
              <div v-for="(u, i) in row.public_urls" :key="i" class="flex items-center gap-1 min-w-0">
                <span class="truncate min-w-0 flex-1 text-xs" :title="u.url">{{ u.url }}</span>
                <span class="ktag flex-none">{{ urlTagMeta(u.tag).label }}</span>
              </div>
            </div>
          </el-popover>
        </template>
      </el-table-column>
      <el-table-column label="负责人" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          {{ (row.owners ?? []).map((o: any) => o.name).join('、') || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90" sortable="custom">
        <template #default="{ row }">
          <span class="dot-tag" :style="dotStyle(assetStatusMeta(row.status).color)">
            <i></i>{{ assetStatusMeta(row.status).label }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right" class-name="op-col">
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

    <div class="px-4">
      <TlPagination v-model:page="page" v-model:size="size" :total="total"
                    @page-change="load" @size-change="onSizeChange" />
    </div>
  </el-card>
  </div>

  <AssetFormDialog v-model:visible="dialogVisible" :asset="editing" @saved="load()" />
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Search, Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import AssetFormDialog from '../components/AssetFormDialog.vue'
import FilterToolbar from '../components/FilterToolbar.vue'
import TlPagination from '../components/TlPagination.vue'
import { useListPage } from '../composables/useListPage'
import { useAuthStore } from '../stores/auth'
import { saveBlob } from '../utils/download'
import { assetStatusMeta, dotStyle, urlTagMeta } from '../utils/colors'

const auth = useAuthStore()
const meta = ref<any>(null)
const { items, total, page, size, search, loading, load, onSizeChange, onSortChange } = useListPage('/assets')
const importing = ref(false)
const dialogVisible = ref(false)
const editing = ref<any>(null)

function openEdit(row?: any) {
  editing.value = row ?? null
  dialogVisible.value = true
}

async function remove(id: number) {
  await client.delete(`/assets/${id}`)
  ElMessage.success('删除成功')
  await load()
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
