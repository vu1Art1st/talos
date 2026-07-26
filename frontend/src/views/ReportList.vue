<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索报告标题 / 项目" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button type="primary" @click="fromVulnsVisible = true">
        <el-icon class="mr-1"><MagicStick /></el-icon>从漏洞生成
      </el-button>
      <el-button @click="createBlank">
        <el-icon class="mr-1"><Plus /></el-icon>新建空白报告
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="报告标题" min-width="240" show-overflow-tooltip />
      <el-table-column prop="project_name" label="项目" width="160" show-overflow-tooltip />
      <el-table-column prop="author" label="作者" width="120" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'final' ? 'success' : 'info'" size="small">
            {{ row.status === 'final' ? '已定稿' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="70" />
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ fmt(row.update_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="router.push(`/reports/${row.id}`)">编辑</el-button>
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
    <el-form label-width="80px">
      <el-form-item label="报告标题">
        <el-input v-model="genTitle" placeholder="例如：XX系统渗透测试报告" />
      </el-form-item>
      <el-form-item label="选择漏洞">
        <el-select v-model="genVulIds" multiple filterable class="w-full" placeholder="可多选">
          <el-option v-for="v in vulns" :key="v.id" :label="`#${v.id} ${v.title}`" :value="v.id" />
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
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'

const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const loading = ref(false)
const fromVulnsVisible = ref(false)
const genTitle = ref('')
const genVulIds = ref<number[]>([])
const vulns = ref<any[]>([])

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/reports', { params: { search: search.value, page: p, size: 20 } })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function createBlank() {
  const { data } = await client.post('/reports', { title: '未命名报告', sections: [] })
  router.push(`/reports/${data.id}`)
}

async function generate() {
  const { data } = await client.post('/reports/from-vulns', { title: genTitle.value, vul_ids: genVulIds.value })
  ElMessage.success('报告已生成')
  fromVulnsVisible.value = false
  router.push(`/reports/${data.id}`)
}

async function remove(id: number) {
  await client.delete(`/reports/${id}`)
  ElMessage.success('删除成功')
  await load()
}

watch(fromVulnsVisible, async (v) => {
  if (v && !vulns.value.length) {
    const { data } = await client.get('/vulns', { params: { size: 100 } })
    vulns.value = data.items
  }
})

onMounted(() => load(1))
</script>
