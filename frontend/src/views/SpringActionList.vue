<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <el-input v-model="search" placeholder="搜索报告编号 / 系统 / 公文文号" clearable class="!w-64"
                @keyup.enter="load(1)" @clear="load(1)">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="flex-1" />
      <el-button type="primary" @click="openDialog()">
        <el-icon class="mr-1"><Plus /></el-icon>新增春耕行动
      </el-button>
    </div>

    <el-table v-loading="loading" :data="items" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="report_no" label="报告编号" width="160" show-overflow-tooltip />
      <el-table-column prop="system_name" label="对应系统" min-width="160" show-overflow-tooltip />
      <el-table-column label="年度" width="90">
        <template #default="{ row }">{{ row.year || '-' }}</template>
      </el-table-column>
      <el-table-column label="阶段" width="110" show-overflow-tooltip>
        <template #default="{ row }">{{ row.phase || '-' }}</template>
      </el-table-column>
      <el-table-column label="涉及漏洞" width="110">
        <template #default="{ row }">
          <el-popover v-if="row.vuls?.length" placement="right" width="360" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.vuls.length }} 个</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="v in row.vuls" :key="v.id" class="flex items-center gap-2">
                <el-tag size="small" :color="levelColor(v.level)" style="color:#fff;border:none">
                  {{ levelName(v.level) }}
                </el-tag>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/vulns/${v.id}`)">#{{ v.id }} {{ v.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="申诉结果" width="100">
        <template #default="{ row }">
          <el-tag :type="row.appeal_success ? 'success' : 'info'" size="small">
            {{ row.appeal_success ? '申诉成功' : '未申诉/失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最终扣分" width="100">
        <template #default="{ row }">{{ row.score_deduction }}</template>
      </el-table-column>
      <el-table-column prop="doc_no" label="公文文号" width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该记录？" @confirm="remove(row.id)">
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

  <el-dialog v-model="dialogVisible" :title="form.id ? '编辑春耕行动' : '新增春耕行动'" width="600px">
    <el-form :model="form" label-width="100px">
      <el-form-item label="报告编号" required>
        <el-input v-model="form.report_no" placeholder="原始报告编号" />
      </el-form-item>
      <el-form-item label="对应系统">
        <el-input v-model="form.system_name" />
      </el-form-item>
      <div class="grid grid-cols-2">
        <el-form-item label="年度">
          <el-date-picker v-model="form.year" type="year" value-format="YYYY" placeholder="选择年度" class="!w-full" />
        </el-form-item>
        <el-form-item label="阶段">
          <el-input v-model="form.phase" placeholder="如：第一阶段" />
        </el-form-item>
      </div>
      <el-form-item label="涉及漏洞">
        <el-select v-model="form.vul_ids" multiple filterable class="w-full" placeholder="可多选">
          <el-option v-for="v in vulns" :key="v.id" :label="`#${v.id} ${v.title}`" :value="v.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="申诉成功">
        <el-switch v-model="form.appeal_success" />
      </el-form-item>
      <el-form-item label="最终扣分">
        <el-input-number v-model="form.score_deduction" :min="0" :step="0.5" class="!w-full" />
      </el-form-item>
      <el-form-item label="公文文号">
        <el-input v-model="form.doc_no" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="!form.report_no" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import { levelColor } from '../utils/colors'

const router = useRouter()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const search = ref('')
const loading = ref(false)
const dialogVisible = ref(false)
const vulns = ref<any[]>([])

const levelName = (lv: number) =>
  ({ 10: '严重', 20: '高危', 30: '中危', 40: '低危', 50: '安全' } as Record<number, string>)[lv] ?? lv

const emptyForm = () => ({
  id: null as number | null,
  report_no: '',
  system_name: '',
  year: '',
  phase: '',
  appeal_success: false,
  score_deduction: 0,
  doc_no: '',
  vul_ids: [] as number[],
})
const form = ref(emptyForm())

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get('/spring-actions', { params: { search: search.value, page: p, size: 20 } })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function openDialog(row?: any) {
  form.value = row
    ? { ...emptyForm(), ...row, vul_ids: row.vuls?.map((v: any) => v.id) ?? [] }
    : emptyForm()
  dialogVisible.value = true
  if (!vulns.value.length) {
    const { data } = await client.get('/vulns', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
    vulns.value = data.items
  }
}

async function save() {
  const body = { ...form.value }
  delete (body as any).vuls
  if (form.value.id) {
    await client.put(`/spring-actions/${form.value.id}`, body)
  } else {
    await client.post('/spring-actions', body)
  }
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await load()
}

async function remove(id: number) {
  await client.delete(`/spring-actions/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(() => load(1))
</script>
