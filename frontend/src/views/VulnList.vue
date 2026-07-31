<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex flex-wrap items-center gap-2 mb-4">
      <el-input v-model="query.search" placeholder="搜索标题 / URL" clearable class="!w-60"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="query.status" placeholder="状态" clearable class="!w-32" @change="load(1)">
        <el-option v-for="(name, code) in meta?.vul_status" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-select v-model="query.level" placeholder="等级" clearable class="!w-28" @change="load(1)">
        <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-select v-model="query.vul_type" placeholder="类型" clearable filterable class="!w-44" @change="load(1)">
        <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-checkbox v-model="query.mine" @change="load(1)">只看我提交的</el-checkbox>
      <div class="flex-1" />
      <el-button v-if="auth.hasPerm('vuln:manage') && selected.length" type="danger" @click="batchRemove">
        <el-icon class="mr-1"><Delete /></el-icon>删除选中 ({{ selected.length }})
      </el-button>
      <el-button v-if="auth.hasPerm('vuln:submit')" type="primary" @click="router.push('/vulns/new')">
        <el-icon class="mr-1"><Plus /></el-icon>提交漏洞
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe @row-click="(row: any) => router.push(`/vulns/${row.id}`)"
              class="cursor-pointer" @selection-change="(rows: any[]) => (selected = rows)">
      <el-table-column v-if="auth.hasPerm('vuln:manage')" type="selection" width="42" />
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="漏洞名称" min-width="240" show-overflow-tooltip />
      <el-table-column label="等级" width="90">
        <template #default="{ row }">
          <span class="tl-tag" :style="levelSoftStyle(row.level)">
            {{ meta?.vul_level?.[row.level] ?? row.level }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="150">
        <template #default="{ row }">{{ meta?.vul_type?.[row.vul_type] ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <span class="tl-tag" :style="statusSoftStyleEx(row.status, row.is_retest)">
            {{ statusLabel(row.status, row.is_retest, meta?.vul_status) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="关联资产" width="150" show-overflow-tooltip>
        <template #default="{ row }">
          {{ (row.assets ?? []).map((a: any) => a.name).join('、') || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="归属部门" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.department || '-' }}</template>
      </el-table-column>
      <el-table-column label="提交时间" width="170">
        <template #default="{ row }">{{ fmt(row.submit_time) }}</template>
      </el-table-column>
    </el-table>

    <div class="flex justify-end mt-4">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="query.size" :current-page="query.page"
                     @current-change="load" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle, statusLabel, statusSoftStyleEx } from '../utils/colors'

const auth = useAuthStore()
const router = useRouter()
const meta = ref<any>(null)
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const selected = ref<any[]>([])
const query = reactive({
  search: '', status: undefined, level: undefined, vul_type: undefined,
  mine: false, page: 1, size: 20,
})

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

async function load(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const { data } = await client.get('/vulns', { params: { ...query } })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function batchRemove() {
  const ids = selected.value.map((v) => v.id)
  await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 个漏洞？删除后不可恢复`, '批量删除', {
    type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger',
  })
  await client.post('/vulns/batch-delete', { ids })
  ElMessage.success(`已删除 ${ids.length} 个漏洞`)
  // 当前页被删空时回退一页
  const remainPages = Math.max(1, Math.ceil((total.value - ids.length) / query.size))
  await load(Math.min(query.page, remainPages))
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load(1)
})
</script>
