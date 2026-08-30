<template>
  <div class="space-y-3">
    <FilterToolbar>
      <div class="tl-search-field">
        <el-input v-model="search" placeholder="搜索报告编号 / 系统 / 公文文号" clearable
                  @keyup.enter="load(1)" @clear="load(1)">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <template #actions>
        <el-button type="primary" class="btn-min" @click="openDialog()">
          <el-icon class="mr-1"><Plus /></el-icon>新增春耕行动
        </el-button>
      </template>
    </FilterToolbar>

    <el-card shadow="never" body-style="padding: 0 0 12px">
    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="64"
                       :index="(i: number) => (page - 1) * size + i + 1" />
      <el-table-column prop="report_no" label="报告编号" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column label="原始报告" width="90">
        <template #default="{ row }">
          <el-button v-if="row.report_file_name" size="small" type="primary" link
                     @click="downloadReport(row)">下载</el-button>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="system_name" label="对应系统" min-width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="year" label="年度" width="90" sortable="custom">
        <template #default="{ row }">{{ row.year || '-' }}</template>
      </el-table-column>
      <el-table-column prop="phase" label="阶段" width="110" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.phase || '-' }}</template>
      </el-table-column>
      <el-table-column label="网络层级" width="130">
        <template #default="{ row }">
          <template v-if="row.vuls?.length">
            <span v-for="code in uniqVulValues(row, 'layer').slice(0, 1)" :key="code" class="ktag mr-1">{{ layerName(code) }}</span>
            <el-popover v-if="uniqVulValues(row, 'layer').length > 1" placement="left" :width="220" trigger="hover">
              <template #reference>
                <el-button size="small" type="primary" link class="!p-0">+{{ uniqVulValues(row, 'layer').length - 1 }}</el-button>
              </template>
              <div class="flex flex-wrap gap-1">
                <span v-for="code in uniqVulValues(row, 'layer')" :key="code" class="ktag">{{ layerName(code) }}</span>
              </div>
            </el-popover>
          </template>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="危害程度" width="120">
        <template #default="{ row }">
          <template v-if="row.vuls?.length">
            <span v-for="code in uniqVulValues(row, 'level').slice(0, 2)" :key="code" class="dot-tag mr-2"
                  :style="levelDotStyle(code)"><i></i>{{ levelName(code) }}</span>
            <el-popover v-if="uniqVulValues(row, 'level').length > 2" placement="left" :width="220" trigger="hover">
              <template #reference>
                <el-button size="small" type="primary" link class="!p-0">+{{ uniqVulValues(row, 'level').length - 2 }}</el-button>
              </template>
              <div class="flex flex-col gap-1">
                <span v-for="code in uniqVulValues(row, 'level')" :key="code" class="dot-tag"
                      :style="levelDotStyle(code)"><i></i>{{ levelName(code) }}</span>
              </div>
            </el-popover>
          </template>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="涉及漏洞" width="110">
        <template #default="{ row }">
          <el-popover v-if="row.vuls?.length" placement="right" width="360" trigger="hover">
            <template #reference>
              <el-button size="small" type="primary" link>{{ row.vuls.length }} 个</el-button>
            </template>
            <div class="flex flex-col gap-1 max-h-64 overflow-auto">
              <div v-for="v in row.vuls" :key="v.id" class="flex items-center gap-2">
                <span class="tl-tag" :style="levelSoftStyle(v.level)">
                  {{ levelName(v.level) }}
                </span>
                <el-button size="small" type="primary" link class="!p-0"
                           @click="router.push(`/vulns/${v.id}`)">{{ v.title }}</el-button>
              </div>
            </div>
          </el-popover>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="asset_reason" label="资产认定原因" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="appeal_success" label="申诉结果" width="110" sortable="custom">
        <template #default="{ row }">
          <span class="dot-tag" :style="dotStyle(row.appeal_success ? STAT_CARD_COLORS.green : STAT_CARD_COLORS.gray)">
            <i></i>{{ row.appeal_success ? '申诉成功' : '未申诉/失败' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="est_score_deduction" label="预估扣分" width="110" sortable="custom">
        <template #default="{ row }">{{ row.est_score_deduction }}</template>
      </el-table-column>
      <el-table-column prop="score_deduction" label="最终扣分" width="110" sortable="custom">
        <template #default="{ row }">{{ row.score_deduction }}</template>
      </el-table-column>
      <el-table-column prop="doc_no" label="公文文号" width="160" show-overflow-tooltip sortable="custom" />
      <el-table-column label="操作" width="120" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该记录？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无春耕行动记录，点击「新增春耕行动」创建" :image-size="80" />
      </template>
    </el-table>

    <div class="px-4">
      <TlPagination v-model:page="page" v-model:size="size" :total="total"
                    @page-change="load" @size-change="onSizeChange" />
    </div>
  </el-card>
  </div>

  <el-dialog
             :close-on-click-modal="false" v-model="dialogVisible" :title="form.id ? '编辑春耕行动' : '新增春耕行动'" width="640px">
    <el-form :model="form" label-width="90px">
      <el-form-item label="报告编号" required>
        <el-input v-model="form.report_no" placeholder="原始报告编号" />
      </el-form-item>
      <el-form-item label="原始报告">
        <div class="w-full flex flex-col gap-2">
          <div v-if="form.report_file_name" class="flex items-center gap-2">
            <el-button v-if="form.id" size="small" type="primary" link @click="downloadReport(form)">
              <el-icon class="mr-1"><Document /></el-icon>{{ form.report_file_name }}
            </el-button>
            <span v-else class="text-sm">{{ form.report_file_name }}</span>
            <el-button size="small" type="danger" link @click="clearReport">移除</el-button>
          </div>
          <el-upload :http-request="uploadReport" :show-file-list="false" accept=".docx">
            <el-button size="small" plain :loading="uploading">
              <el-icon class="mr-1"><Upload /></el-icon>上传原始报告
            </el-button>
          </el-upload>
          <span class="text-xs text-gray-400">
            上传原始报告 Word 文档（.docx，不超过 50MB），自动解析系统名称、年度与漏洞供勾选导入
          </span>
          <div v-if="parsedVuls.length" class="rounded border border-gray-200 p-3">
            <div class="text-xs text-gray-500 mb-2">
              报告解析到 {{ parsedVuls.length }} 个漏洞，勾选后将随保存导入并关联：
            </div>
            <el-checkbox v-model="importAll" :indeterminate="importIndeterminate" class="mb-1">全选</el-checkbox>
            <el-checkbox-group v-model="importIdx">
              <div v-for="(v, i) in parsedVuls" :key="i" class="flex items-center">
                <el-checkbox :value="i">
                  <span class="tl-tag" :style="levelSoftStyle(v.level)">{{ levelName(v.level) }}</span>
                  {{ v.title }}
                </el-checkbox>
              </div>
            </el-checkbox-group>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="对应系统">
        <el-input v-model="form.system_name" />
      </el-form-item>
      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="年度">
          <el-date-picker v-model="form.year" type="year" value-format="YYYY" placeholder="选择年度" class="!w-full" />
        </el-form-item>
        <el-form-item label="阶段">
          <el-input v-model="form.phase" placeholder="如：第一阶段" />
        </el-form-item>
      </div>
      <el-form-item label="涉及漏洞">
        <div class="w-full">
          <el-select v-model="form.vul_ids" multiple filterable class="w-full"
                     placeholder="可多选，或直接新增漏洞">
            <el-option v-for="v in vulns" :key="v.id" :label="v.title" :value="v.id" />
          </el-select>
          <div class="mt-2">
            <el-button size="small" plain @click="toggleQuickAdd">
              <el-icon class="mr-1"><Plus /></el-icon>直接新增漏洞
            </el-button>
            <el-card v-if="quickAddVisible" shadow="never" class="!rounded-md mt-2">
              <el-form ref="quickFormRef" :model="quickForm" :rules="quickRules" label-width="80px">
                <el-form-item label="漏洞名称" prop="title">
                  <el-input v-model="quickForm.title" placeholder="例如：后台登录接口存在SQL注入" />
                </el-form-item>
                <div class="grid grid-cols-1 md:grid-cols-2">
                  <el-form-item label="漏洞等级">
                    <el-select v-model="quickForm.level" class="w-full">
                      <el-option v-for="(name, code) in quickMeta?.vul_level" :key="code"
                                 :label="name" :value="Number(code)" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="漏洞类型">
                    <el-select v-model="quickForm.vul_type" filterable class="w-full">
                      <el-option v-for="(name, code) in quickMeta?.vul_type" :key="code"
                                 :label="name" :value="Number(code)" />
                    </el-select>
                  </el-form-item>
                </div>
                <el-form-item label=" ">
                  <div class="w-full flex justify-end">
                    <el-button size="small" @click="quickAddVisible = false">取消</el-button>
                    <el-button size="small" type="primary" :loading="quickSaving" @click="createVul">
                      新增并关联
                    </el-button>
                  </div>
                </el-form-item>
              </el-form>
            </el-card>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="资产认定原因">
        <el-input v-model="form.asset_reason" maxlength="255" placeholder="记录对应系统资产归属的认定依据" />
      </el-form-item>
      <el-form-item label="申诉成功">
        <el-switch v-model="form.appeal_success" />
      </el-form-item>
      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="预估扣分">
          <el-input-number v-model="form.est_score_deduction" :min="0" :step="0.5" class="!w-full" />
        </el-form-item>
        <el-form-item label="最终扣分">
          <el-input-number v-model="form.score_deduction" :min="0" :step="0.5" class="!w-full" />
        </el-form-item>
      </div>
      <el-form-item label="公文文号">
        <el-input v-model="form.doc_no" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" :disabled="!form.report_no" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useRouter } from 'vue-router'
import client from '../api/client'
import FilterToolbar from '../components/FilterToolbar.vue'
import TlPagination from '../components/TlPagination.vue'
import { useCrudDialog } from '../composables/useCrudDialog'
import { useListPage } from '../composables/useListPage'
import { useAuthStore } from '../stores/auth'
import { saveBlob } from '../utils/download'
import { levelName, levelSoftStyle, levelDotStyle, dotStyle, STAT_CARD_COLORS } from '../utils/colors'

const router = useRouter()
const auth = useAuthStore()
const { items, total, page, size, search, loading, load, onSizeChange, onSortChange } = useListPage('/spring-actions')
const vulns = ref<any[]>([])

const { dialogVisible, saving, form, openDialog: openCrud, submit: save } = useCrudDialog({
  empty: () => ({
    id: null as number | null,
    report_no: '',
    system_name: '',
    year: '',
    phase: '',
    asset_reason: '',
    appeal_success: false,
    est_score_deduction: 0,
    score_deduction: 0,
    doc_no: '',
    vul_ids: [] as number[],
    report_file_name: '',
    report_file_path: '',
    report_file_size: 0,
  }),
  save: async (f) => {
    const body = { ...f }
    delete (body as any).vuls
    // 勾选的报告漏洞草稿随保存提交，由后端创建并关联
    ;(body as any).new_vuls = parsedVuls.value.filter((_, i) => importIdx.value.includes(i))
    if (f.id) {
      await client.put(`/spring-actions/${f.id}`, body)
    } else {
      await client.post('/spring-actions', body)
    }
    // 保存成功后清理解析态，避免重复导入
    parsedVuls.value = []
    importIdx.value = []
  },
  afterSave: () => load(),
})

async function openDialog(row?: any) {
  openCrud(row ? { ...row, vul_ids: row.vuls?.map((v: any) => v.id) ?? [] } : null)
  parsedVuls.value = []
  importIdx.value = []
  if (!vulns.value.length) {
    const { data } = await client.get('/vulns', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
    vulns.value = data.items
  }
}

// ---------- 原始报告上传导入：解析回填系统/年度，漏洞草稿勾选后随保存创建 ----------
const uploading = ref(false)
const parsedVuls = ref<any[]>([])
const importIdx = ref<number[]>([])

const importAll = computed({
  get: () => parsedVuls.value.length > 0 && importIdx.value.length === parsedVuls.value.length,
  set: (v: boolean) => { importIdx.value = v ? parsedVuls.value.map((_, i) => i) : [] },
})
const importIndeterminate = computed(() =>
  importIdx.value.length > 0 && importIdx.value.length < parsedVuls.value.length)

async function uploadReport(options: any) {
  const fd = new FormData()
  fd.append('file', options.file)
  uploading.value = true
  try {
    const { data } = await client.post('/spring-actions/upload-report', fd)
    form.value.report_file_name = data.name
    form.value.report_file_path = data.path
    form.value.report_file_size = data.size
    // 已填字段不覆盖，仅回填空缺项
    if (!form.value.system_name && data.system_name) form.value.system_name = data.system_name
    if (!form.value.year && data.report_date) form.value.year = data.report_date.slice(0, 4)
    parsedVuls.value = data.vuls ?? []
    importIdx.value = parsedVuls.value.map((_, i) => i)
    ElMessage.success(parsedVuls.value.length
      ? `解析完成，报告含 ${parsedVuls.value.length} 个漏洞`
      : '附件上传成功，未解析到漏洞')
  } finally {
    uploading.value = false
  }
}

function clearReport() {
  form.value.report_file_name = ''
  form.value.report_file_path = ''
  form.value.report_file_size = 0
  parsedVuls.value = []
  importIdx.value = []
}

async function downloadReport(row: any) {
  const { data } = await client.get(`/spring-actions/${row.id}/report`, { responseType: 'blob' })
  saveBlob(data, row.report_file_name || '原始报告.docx')
}

// ---------- 涉及漏洞：内联直接新增（避免弹窗嵌套，保存后自动选中） ----------
const quickAddVisible = ref(false)
const quickSaving = ref(false)
const quickFormRef = ref<FormInstance>()
const quickMeta = ref<Record<string, Record<string, string>>>({})
const quickForm = reactive({ title: '', level: 30, vul_type: 75 })
const quickRules: FormRules = {
  title: [{ required: true, whitespace: true, message: '请填写漏洞名称', trigger: 'blur' }],
}

async function toggleQuickAdd() {
  quickAddVisible.value = !quickAddVisible.value
  if (quickAddVisible.value && !Object.keys(quickMeta.value).length) {
    quickMeta.value = await auth.fetchMeta()
  }
}

async function createVul() {
  const valid = await quickFormRef.value?.validate().catch(() => false)
  if (!valid) return
  quickSaving.value = true
  try {
    // 单独录入且来自春耕行动：来源固定为「春耕行动」（VUL_SOURCE 20）
    const { data } = await client.post('/vulns', { ...quickForm, source: 20 })
    vulns.value = [data, ...vulns.value]
    form.value.vul_ids = [...form.value.vul_ids, data.id]
    ElMessage.success('漏洞已新增并关联')
    quickForm.title = ''
    quickAddVisible.value = false
  } finally {
    quickSaving.value = false
  }
}

// ---------- 网络层级 / 危害程度：按关联漏洞聚合去重展示 ----------
const layerMap = ref<Record<string, string>>({})
const layerName = (code: number) => layerMap.value[code] ?? String(code)

function uniqVulValues(row: any, field: 'layer' | 'level'): number[] {
  return [...new Set((row.vuls ?? []).map((v: any) => v[field]))].sort((a, b) => a - b)
}

async function remove(id: number) {
  await client.delete(`/spring-actions/${id}`)
  await load()
}

onMounted(async () => {
  load(1)
  layerMap.value = (await auth.fetchMeta()).vul_layer ?? {}
})
</script>
