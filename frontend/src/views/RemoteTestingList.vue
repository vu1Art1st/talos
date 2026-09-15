<template>
  <div class="space-y-3">
    <FilterToolbar>
      <div class="tl-search-field">
        <el-input v-model="search" placeholder="搜索系统 / 部门 / 资产归属 / 被通报单位 / 漏洞名称" clearable
                  @keyup.enter="load(1)" @clear="load(1)">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
      <template #actions>
        <el-button type="primary" class="btn-min" @click="openDialog()">
          <el-icon class="mr-1"><Plus /></el-icon>新增远程检测
        </el-button>
      </template>
    </FilterToolbar>

    <el-card shadow="never" body-style="padding: 0 0 12px">
    <el-table v-loading="loading" :data="items" stripe @sort-change="onSortChange">
      <el-table-column type="index" label="序号" width="64"
                       :index="(i: number) => (page - 1) * size + i + 1" />
      <el-table-column prop="notice_time" label="通报时间" width="110" sortable="custom">
        <template #default="{ row }"><span class="num">{{ row.notice_time }}</span></template>
      </el-table-column>
      <el-table-column prop="system_name" label="系统名称" width="150" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="department" label="部门" width="120" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.department || '-' }}</template>
      </el-table-column>
      <el-table-column prop="asset_belong" label="资产归属" width="130" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">{{ row.asset_belong || '-' }}</template>
      </el-table-column>
      <el-table-column prop="notified_unit" label="被通报单位" width="150" show-overflow-tooltip />
      <el-table-column prop="is_external" label="外部项目" width="110" sortable="custom">
        <template #default="{ row }">
          <span class="dot-tag" :style="dotStyle(row.is_external ? STAT_CARD_COLORS.blue : STAT_CARD_COLORS.gray)">
            <i></i>{{ row.is_external ? '是' : '否' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="vuln_name" label="漏洞名称" min-width="180" show-overflow-tooltip sortable="custom">
        <template #default="{ row }">
          <el-button v-if="row.vuln" size="small" type="primary" link class="!p-0"
                     @click="openVulnDetail(row.vuln.id)">{{ row.vuln.title }}</el-button>
          <span v-else-if="row.vuln_name">{{ row.vuln_name }}</span>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column label="漏洞类型" width="130" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.vuln">{{ vulTypeName(row.vuln.vul_type) }}</span>
          <span v-else-if="row.vuln_type">{{ vulTypeName(row.vuln_type) }}</span>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="appeal_status" label="申诉状态" width="110" sortable="custom">
        <template #default="{ row }">
          <span class="dot-tag" :style="dotStyle(appealStatusColor(row.appeal_status))">
            <i></i>{{ appealStatusLabel(row.appeal_status) }}
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
      <el-table-column label="操作" width="120" fixed="right" class-name="op-col">
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

    <div class="px-4">
      <TlPagination v-model:page="page" v-model:size="size" :total="total"
                    @page-change="load" @size-change="onSizeChange" />
    </div>
  </el-card>
  </div>

  <el-dialog
         :close-on-click-modal="false" v-model="dialogVisible" :title="form.id ? '编辑远程检测' : '新增远程检测'" width="640px">
    <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
      <el-form-item label="关联资产">
        <div class="w-full flex gap-2">
          <el-select v-model="form.asset_id" filterable remote clearable :remote-method="onAssetSearch"
                     :loading="assetLoading" placeholder="输入资产名称搜索并选择，选择后自动带出系统名称与部门"
                     class="flex-1" @change="onAssetChange">
            <el-option v-for="a in assetOptions" :key="a.id" :label="a.label" :value="a.id" />
            <template #empty>
              <div class="p-3 text-center">
                <p class="text-sm text-gray-400 mb-2">未找到匹配的资产</p>
                <el-button size="small" type="primary" @click="openCreateAsset">
                  <el-icon class="mr-1"><Plus /></el-icon>新建资产{{ assetKeyword ? `「${assetKeyword}」` : '' }}
                </el-button>
              </div>
            </template>
          </el-select>
          <el-button type="primary" plain @click="openCreateAsset">
            <el-icon class="mr-1"><Plus /></el-icon>新增资产
          </el-button>
        </div>
      </el-form-item>
      <el-form-item label="系统名称" prop="system_name">
        <el-input v-model="form.system_name" placeholder="被检系统名称，选择资产后自动带出" />
      </el-form-item>
      <div class="grid grid-cols-2 gap-x-4">
        <el-form-item label="通报时间">
          <el-date-picker v-model="form.notice_time" type="month" value-format="YYYY-MM"
                          placeholder="选择通报月份" class="!w-full" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="form.department" placeholder="选择资产后自动带出，可修改" />
        </el-form-item>
        <el-form-item label="资产归属">
          <el-input v-model="form.asset_belong" placeholder="该系统的资产归属" />
        </el-form-item>
        <el-form-item label="被通报单位">
          <el-input v-model="form.notified_unit" />
        </el-form-item>
        <el-form-item label="是否外部项目">
          <el-switch v-model="form.is_external" active-text="是" inactive-text="否" />
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
      <el-form-item label="新增漏洞">
        <div class="w-full">
          <div v-if="linkedVuln" class="flex items-center gap-2 rounded-md border border-gray-200 px-3 py-2">
            <span class="tl-tag" :style="levelSoftStyle(linkedVuln.level)">{{ levelName(linkedVuln.level) }}</span>
            <el-button v-if="linkedVuln.id" type="primary" link class="!p-0"
                       @click="openVulnDetail(linkedVuln.id)">{{ linkedVuln.title }}</el-button>
            <span v-else class="text-sm">{{ linkedVuln.title }}</span>
            <span class="tl-tag" :style="vulTypeSoftStyle(linkedVuln.vul_type)">
              {{ meta?.vul_type?.[linkedVuln.vul_type] ?? linkedVuln.vul_type }}
            </span>
            <div class="flex-1" />
            <el-button size="small" type="danger" link @click="clearLinkedVuln">移除</el-button>
          </div>
          <el-card v-else-if="quickAddVisible" shadow="never" class="!rounded-md">
            <el-form ref="quickFormRef" :model="quickForm" :rules="quickRules" label-width="80px">
              <el-form-item label="漏洞名称" prop="title">
                <el-input v-model="quickForm.title" placeholder="例如：后台登录接口存在SQL注入" />
              </el-form-item>
              <div class="grid grid-cols-2 gap-x-4">
                <el-form-item label="漏洞等级">
                  <el-select v-model="quickForm.level" class="w-full">
                    <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
                  </el-select>
                </el-form-item>
                <el-form-item label="漏洞类型">
                  <el-select v-model="quickForm.vul_type" filterable class="w-full">
                    <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
                  </el-select>
                </el-form-item>
              </div>
              <el-form-item label="漏洞来源">
                <el-select v-model="quickForm.source" clearable placeholder="未选择" class="w-full">
                  <el-option v-for="(name, code) in meta?.vul_source" :key="code" :label="name" :value="Number(code)" />
                </el-select>
              </el-form-item>
              <el-form-item label=" ">
                <div class="w-full flex justify-end">
                  <el-button size="small" @click="quickAddVisible = false">取消</el-button>
                  <el-button size="small" type="primary" @click="confirmQuickVul">确定新增</el-button>
                </div>
              </el-form-item>
            </el-form>
          </el-card>
          <div v-else>
            <el-button size="small" plain @click="toggleQuickAdd">
              <el-icon class="mr-1"><Plus /></el-icon>新增漏洞
            </el-button>
            <span class="text-xs text-gray-400 ml-2">录入的漏洞将随保存创建并关联到历史漏洞库</span>
          </div>
        </div>
      </el-form-item>
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
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <!-- 资产新增：与工单流程同一入口，保存后自动选中并带出系统名称/部门 -->
  <AssetFormDialog v-model:visible="assetDialogVisible" :asset="null" @saved="onAssetSaved" />

  <!-- 漏洞详情：录入/关联的漏洞名称可点击查看，交互与渗透测试工单一致 -->
  <VulnDetailDialog v-model:visible="vulnDetailVisible" :vuln-id="vulnDetailId" />
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Document, Plus, Search, Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import AssetFormDialog from '../components/AssetFormDialog.vue'
import FilterToolbar from '../components/FilterToolbar.vue'
import TlPagination from '../components/TlPagination.vue'
import VulnDetailDialog from '../components/VulnDetailDialog.vue'
import { useAssetSelect } from '../composables/useAssetSelect'
import { useCrudDialog } from '../composables/useCrudDialog'
import { useListPage } from '../composables/useListPage'
import { useAuthStore } from '../stores/auth'
import { saveBlob } from '../utils/download'
import { dotStyle, levelName, levelSoftStyle, STAT_CARD_COLORS, vulTypeSoftStyle } from '../utils/colors'

const auth = useAuthStore()
const meta = ref<any>(null)
const { items, total, page, size, search, loading, load, onSizeChange, onSortChange } = useListPage('/remote-testings')

const emptyForm = () => ({
  id: null as number | null,
  system_name: '',
  notice_time: '',
  department: '',
  asset_belong: '',
  asset_id: null as number | null,
  notified_unit: '',
  is_external: false,
  vuln_name: '',
  vuln_type: '',
  vuln_id: null as number | null,
  appeal_status: '',
  appeal_method: '',
  appeal_file_name: '',
  appeal_file_path: '',
  appeal_file_size: 0,
})
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  system_name: [{ required: true, whitespace: true, message: '请填写系统名称', trigger: 'blur' }],
}

// 表单内当前关联漏洞（编辑回显或本次新增草稿预览）与待创建草稿
const linkedVuln = ref<any>(null)
const pendingVul = ref<any>(null)

const { dialogVisible, saving, form, openDialog: openCrud, submit: saveForm } = useCrudDialog({
  empty: emptyForm,
  save: async (f) => {
    const body: any = { ...f, new_vul: pendingVul.value }
    if (f.id) {
      await client.put(`/remote-testings/${f.id}`, body)
    } else {
      await client.post('/remote-testings', body)
    }
  },
  afterSave: () => load(),
})

function openDialog(row?: any) {
  openCrud(row ?? null)
  linkedVuln.value = row?.vuln ?? null
  pendingVul.value = null
  quickAddVisible.value = false
  resetQuickForm()
  // 编辑进入时回显关联资产标签（下拉默认只有选项不含标签）
  if (row?.asset_id) loadAssetLabels([row.asset_id])
}

async function save() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  await saveForm()
}

// ---------- 关联资产：远程搜索 + 现场新增资产 ----------
const {
  assetOptions, assetLoading, assetCache, searchAssets, loadAssetLabels, cacheAsset,
} = useAssetSelect()
const assetDialogVisible = ref(false)
const assetKeyword = ref('')

// 包装远程搜索：记录关键词，供空态「新建资产「关键词」」入口取用
async function onAssetSearch(keyword = '') {
  assetKeyword.value = keyword
  await searchAssets(keyword)
}

function openCreateAsset() {
  assetDialogVisible.value = true
}

// 选中资产后带出系统名称与部门（用户已明确选择，允许覆盖手工值）
function onAssetChange(id: number | null) {
  const asset = id ? assetCache.value[id] : null
  if (!asset) return
  if (asset.name) form.value.system_name = asset.name
  if (asset.department) form.value.department = asset.department
}

function onAssetSaved(asset: any) {
  cacheAsset(asset)
  form.value.asset_id = asset.id
  onAssetChange(asset.id)
}

// ---------- 新增漏洞：表单内录入，随保存创建并关联 ----------
const quickAddVisible = ref(false)
const quickFormRef = ref<FormInstance>()
const quickForm = ref({ title: '', level: 30, vul_type: 75, source: 0 })
const quickRules: FormRules = {
  title: [{ required: true, whitespace: true, message: '请填写漏洞名称', trigger: 'blur' }],
}

function resetQuickForm() {
  quickForm.value = { title: '', level: 30, vul_type: 75, source: 0 }
}

function toggleQuickAdd() {
  resetQuickForm()
  quickAddVisible.value = true
}

async function confirmQuickVul() {
  const valid = await quickFormRef.value?.validate().catch(() => false)
  if (!valid) return
  pendingVul.value = { ...quickForm.value }
  linkedVuln.value = { ...quickForm.value }
  form.value.vuln_id = null
  quickAddVisible.value = false
}

function clearLinkedVuln() {
  linkedVuln.value = null
  pendingVul.value = null
  form.value.vuln_id = null
  form.value.vuln_name = ''
  form.value.vuln_type = ''
}

// ---------- 漏洞详情 ----------
const vulnDetailVisible = ref(false)
const vulnDetailId = ref<number | null>(null)

function openVulnDetail(id: number) {
  vulnDetailId.value = id
  vulnDetailVisible.value = true
}

// 漏洞类型名称：关联漏洞存字典码，历史文本直接展示
function vulTypeName(t: number | string) {
  return meta.value?.vul_type?.[Number(t)] ?? String(t)
}

const appealStatusLabel = (s: string) =>
  s === 'success' ? '申诉成功' : s === 'fail' ? '申诉失败' : '未申诉'
const appealStatusColor = (s: string) =>
  s === 'success' ? STAT_CARD_COLORS.green
    : s === 'fail' ? STAT_CARD_COLORS.red : STAT_CARD_COLORS.gray

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
  saveBlob(data, row.appeal_file_name || 'appeal')
}

async function remove(row: any) {
  await client.delete(`/remote-testings/${row.id}`)
  await load()
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load(1)
})
</script>
