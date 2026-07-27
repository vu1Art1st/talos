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
      <el-button v-if="auth.hasPerm('vuln:submit')" type="primary" @click="router.push('/vulns/new')">
        <el-icon class="mr-1"><Plus /></el-icon>提交漏洞
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe @row-click="(row: any) => router.push(`/vulns/${row.id}`)"
              class="cursor-pointer">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="漏洞名称" min-width="240" show-overflow-tooltip />
      <el-table-column label="等级" width="90">
        <template #default="{ row }">
          <el-tag :color="levelColor(row.level)" effect="dark" size="small" class="!border-0">
            {{ meta?.vul_level?.[row.level] ?? row.level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="150">
        <template #default="{ row }">{{ meta?.vul_type?.[row.vul_type] ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :color="statusColor(row.status)" effect="dark" size="small" class="!border-0">
            {{ meta?.vul_status?.[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="app_name" label="所属应用" width="150" show-overflow-tooltip />
      <el-table-column label="来源" width="100">
        <template #default="{ row }">{{ meta?.vul_source?.[row.source] ?? '-' }}</template>
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
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { levelColor, statusColor } from '../utils/colors'

const auth = useAuthStore()
const router = useRouter()
const meta = ref<any>(null)
const items = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
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

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load(1)
})
</script>
