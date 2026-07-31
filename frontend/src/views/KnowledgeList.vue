<template>
  <el-card shadow="never" class="!rounded-lg">
    <div class="flex items-center gap-2 mb-4">
      <span class="text-gray-400 text-sm">按漏洞名称沉淀标准描述 / 危害说明 / 修复建议，提交漏洞与 Word 导入时可自动套用</span>
      <div class="flex-1" />
      <template v-if="auth.hasPerm('vuln:manage')">
        <el-button type="danger" plain :disabled="!selected.length" @click="removeBatch">
          <el-icon class="mr-1"><Delete /></el-icon>批量删除{{ selected.length ? `(${selected.length})` : '' }}
        </el-button>
        <el-button @click="importVisible = true">
          <el-icon class="mr-1"><Upload /></el-icon>批量导入
        </el-button>
        <el-button type="primary" @click="openDialog()">
          <el-icon class="mr-1"><Plus /></el-icon>新建条目
        </el-button>
      </template>
    </div>

    <el-table v-loading="loading" :data="items" stripe @selection-change="(rows: any[]) => (selected = rows)">
      <el-table-column v-if="auth.hasPerm('vuln:manage')" type="selection" width="44" />
      <el-table-column prop="vulnerability_name" label="漏洞名称" min-width="200" show-overflow-tooltip />
      <el-table-column label="漏洞类型" width="140">
        <template #default="{ row }">
          <el-tag size="small">{{ meta?.vul_type?.[row.vul_type] ?? row.vul_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="危害等级" width="90">
        <template #default="{ row }">
          <span class="tl-tag" :style="levelSoftStyle(row.severity_level)">
            {{ meta?.vul_level?.[row.severity_level] ?? row.severity_level }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="标准描述" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ plainText(row.description_html) || '-' }}</template>
      </el-table-column>
      <el-table-column label="修复建议" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ plainText(row.solution_html) || '-' }}</template>
      </el-table-column>
      <el-table-column label="参考链接" width="90">
        <template #default="{ row }">{{ (row.references ?? []).length || '-' }}</template>
      </el-table-column>
      <el-table-column prop="username" label="维护人" width="110">
        <template #default="{ row }">{{ row.username || '-' }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ (row.update_time ?? '').replace('T', ' ').slice(0, 19) || '-' }}</template>
      </el-table-column>
      <el-table-column v-if="auth.hasPerm('vuln:manage')" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除该条目？" @confirm="remove(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-dialog v-model="dialogVisible" :title="editing ? '编辑条目' : '新建条目'" width="860px" top="4vh">
    <el-form label-width="90px">
      <el-form-item label="漏洞名称" required>
        <el-input v-model="form.vulnerability_name" maxlength="255" placeholder="例如 SQL注入、SSRF服务器端请求伪造" class="!w-96" />
      </el-form-item>
      <el-form-item label="漏洞类型" required>
        <el-select v-model="form.vul_type" filterable class="!w-64">
          <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
        </el-select>
      </el-form-item>
      <el-form-item label="危害等级" required>
        <el-select v-model="form.severity_level" class="!w-64">
          <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
        </el-select>
      </el-form-item>
      <el-form-item label="标准描述">
        <RichEditor v-model="form.description_html" class="w-full"
                    @update:json="(j: any) => (form.description_json = j)" />
      </el-form-item>
      <el-form-item label="危害说明">
        <RichEditor v-model="form.harm_html" class="w-full"
                    @update:json="(j: any) => (form.harm_json = j)" />
      </el-form-item>
      <el-form-item label="修复建议">
        <RichEditor v-model="form.solution_html" class="w-full"
                    @update:json="(j: any) => (form.solution_json = j)" />
      </el-form-item>
      <el-form-item label="参考链接">
        <el-input v-model="referencesText" type="textarea" :rows="3"
                  placeholder="每行一个链接，例如 https://owasp.org/Top10/" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="importVisible" title="批量导入知识库条目" width="720px" top="6vh">
    <div class="text-gray-400 text-xs mb-2 leading-5">
      粘贴或选择 JSON 文件，格式为条目数组；按「漏洞名称」匹配，已存在则覆盖，单次至多 500 条。<br>
      必填：vulnerability_name（漏洞名称）、vul_type（类型码）、severity_level（等级码）；
      可选：description_html / harm_html / solution_html / references
    </div>
    <div class="flex items-center gap-2 mb-2">
      <el-button size="small" @click="fileInput?.click()">选择 JSON 文件</el-button>
      <el-button size="small" link type="primary" @click="downloadTemplate">下载示例模板</el-button>
      <input ref="fileInput" type="file" accept=".json,application/json" class="hidden" @change="onFileChange">
    </div>
    <el-input v-model="importText" type="textarea" :rows="12"
              placeholder='[{"vulnerability_name": "SQL注入", "vul_type": 10, "severity_level": 10, "description_html": "<p>...</p>"}]' />
    <template #footer>
      <el-button @click="importVisible = false">取消</el-button>
      <el-button type="primary" :loading="importing" @click="doImport">导入</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Plus, Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import RichEditor from '../components/RichEditor.vue'
import { useAuthStore } from '../stores/auth'
import { levelSoftStyle } from '../utils/colors'

const auth = useAuthStore()
const meta = ref<any>(null)
const items = ref<any[]>([])
const selected = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref(false)
const referencesText = ref('')
const importVisible = ref(false)
const importing = ref(false)
const importText = ref('')
const fileInput = ref<HTMLInputElement>()

const emptyForm = () => ({
  id: null as number | null,
  vulnerability_name: '',
  vul_type: 75, severity_level: 30,
  description_html: '', description_json: null,
  harm_html: '', harm_json: null,
  solution_html: '', solution_json: null,
})
const form = reactive<any>(emptyForm())

function plainText(html: string) {
  // DOMParser 解析不挂载到页面，仅提取纯文本用于表格预览
  const doc = new DOMParser().parseFromString(html || '', 'text/html')
  return (doc.body.textContent ?? '').trim()
}

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/knowledge')
    items.value = data
  } finally {
    loading.value = false
  }
}

function openDialog(row?: any) {
  editing.value = !!row
  Object.assign(form, emptyForm(), JSON.parse(JSON.stringify(row ?? {})))
  referencesText.value = (row?.references ?? []).join('\n')
  dialogVisible.value = true
}

async function save() {
  if (!form.vulnerability_name.trim()) {
    ElMessage.warning('请填写漏洞名称')
    return
  }
  saving.value = true
  try {
    const body = {
      ...form,
      vulnerability_name: form.vulnerability_name.trim(),
      references: referencesText.value.split('\n').map((s) => s.trim()).filter(Boolean),
    }
    // 编辑按 ID 更新（可改名）；新建走 upsert
    if (editing.value && form.id) await client.put(`/knowledge/${form.id}`, body)
    else await client.post('/knowledge', body)
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(id: number) {
  await client.delete(`/knowledge/${id}`)
  ElMessage.success('删除成功')
  await load()
}

async function removeBatch() {
  await ElMessageBox.confirm(`确认删除选中的 ${selected.value.length} 条知识库条目？`, '批量删除', { type: 'warning' })
  const { data } = await client.post('/knowledge/batch-delete', { ids: selected.value.map((r) => r.id) })
  ElMessage.success(`已删除 ${data.deleted} 条`)
  await load()
}

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    importText.value = String(reader.result ?? '')
  }
  reader.readAsText(file)
  ;(e.target as HTMLInputElement).value = ''
}

function downloadTemplate() {
  const sample = [{
    vulnerability_name: 'SQL注入',
    vul_type: 10,
    severity_level: 10,
    description_html: '<p>应用程序未对用户输入做有效过滤，攻击者可构造恶意 SQL 语句操纵数据库查询。</p>',
    harm_html: '<p>可导致数据库信息泄露、数据被篡改甚至服务器被控制。</p>',
    solution_html: '<p>使用参数化查询（预编译语句），并对输入做白名单校验。</p>',
    references: ['https://owasp.org/Top10/'],
  }]
  const blob = new Blob([JSON.stringify(sample, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'knowledge-import-template.json'
  a.click()
  URL.revokeObjectURL(a.href)
}

async function doImport() {
  let parsed: any
  try {
    parsed = JSON.parse(importText.value)
  } catch {
    ElMessage.error('JSON 格式错误，请检查后重试')
    return
  }
  if (!Array.isArray(parsed) || !parsed.length) {
    ElMessage.error('导入数据必须是非空的条目数组')
    return
  }
  importing.value = true
  try {
    const { data } = await client.post('/knowledge/batch-import', { items: parsed })
    ElMessage.success(`导入完成：新增 ${data.created} 条，更新 ${data.updated} 条`)
    importVisible.value = false
    importText.value = ''
    await load()
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await load()
})
</script>
