<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索报告标题 / 项目" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
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

    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column prop="id" label="ID" width="70" sortable="custom" />
      <el-table-column prop="title" label="报告标题" min-width="240" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="project_name" label="项目" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="author" label="作者" width="120" sortable="custom" />
      <el-table-column prop="status" label="状态" width="90" sortable="custom">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small">{{ statusName(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="70" sortable="custom" />
      <el-table-column prop="update_time" label="更新时间" width="170" sortable="custom">
        <template #default="{ row }">{{ fmt(row.update_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="190" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="router.push(`/reports/${row.id}`)">编辑</el-button>
          <el-button v-if="row.status !== 'completed'" size="small" type="warning" link @click="retest(row.id)">
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
      <el-form-item label="关联测试计划">
        <el-select v-model="genPlanId" clearable filterable class="w-full"
                   placeholder="可选，关联后联动计划状态" @change="onPlanChange">
          <el-option v-for="p in plans" :key="p.id" :label="`#${p.id} ${p.system_name}`" :value="p.id" />
        </el-select>
      </el-form-item>
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
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

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

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

const statusName = (s: string) =>
  s === 'completed' ? '已完成' : s === 'final' ? '已定稿' : '草稿'
const statusTag = (s: string) =>
  s === 'completed' ? 'success' : s === 'final' ? 'primary' : 'info'

async function retest(id: number) {
  await client.post(`/reports/${id}/retest`)
  ElMessage.success('已发起复测，关联漏洞进入复测中')
  router.push(`/reports/${id}`)
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
  const { data } = await client.post('/reports/from-vulns', {
    title: genTitle.value,
    vul_ids: genVulIds.value,
    testing_plan_id: genPlanId.value,
  })
  ElMessage.success('报告已生成')
  fromVulnsVisible.value = false
  router.push(`/reports/${data.id}`)
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
  if (plan && !genTitle.value) genTitle.value = `${plan.system_name}渗透测试报告`
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
