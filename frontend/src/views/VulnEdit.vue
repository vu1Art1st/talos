<template>
  <div v-if="planId" class="max-w-5xl mb-3">
    <el-tag type="warning" effect="plain">
      本次录入将关联测试计划 #{{ planId }}{{ planName ? `（${planName}）` : '' }}
    </el-tag>
  </div>
  <el-card shadow="never" class="!rounded-lg max-w-5xl mb-4">
    <el-form label-width="90px">
      <el-form-item label="测试目标" required>
        <div class="w-full flex items-start gap-2">
        <el-select v-model="assetIds" multiple filterable remote :remote-method="searchAssets"
                   :loading="assetLoading" placeholder="搜索并选择资产（系统）" class="flex-1"
                   @change="onAssetChange">
          <el-option v-for="a in assetOptions" :key="a.id" :value="a.id"
                     :label="a.sub_system ? `${a.name} / ${a.sub_system}` : a.name">
            <div class="flex justify-between">
              <span>{{ a.sub_system ? `${a.name} / ${a.sub_system}` : a.name }}</span>
              <span class="text-xs text-gray-400">{{ a.department }}</span>
            </div>
          </el-option>
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
      <el-form-item v-if="selectedAssets.length" label=" ">
        <div class="text-xs text-gray-500 leading-6">
          <div v-for="a in selectedAssets" :key="a.id">
            {{ a.name }}：部门 {{ a.department || '-' }}；
            负责人 {{ (a.owners ?? []).map((o: any) => o.name).join('、') || '-' }}；
            URL {{ (a.public_urls ?? [])[0]?.url || (a.internal_urls ?? [])[0] || '-' }}
          </div>
        </div>
      </el-form-item>
    </el-form>
  </el-card>

  <el-card v-for="(vul, idx) in vulns" :key="idx" shadow="never" class="!rounded-lg max-w-5xl mb-4">
    <template #header>
      <div class="flex items-center">
        <span class="font-medium">{{ editId ? '编辑漏洞' : `漏洞 #${idx + 1}` }}</span>
        <div class="flex-1" />
        <el-button v-if="!editId && vulns.length > 1" type="danger" link @click="vulns.splice(idx, 1)">
          删除此漏洞
        </el-button>
      </div>
    </template>
    <el-form :model="vul" label-width="90px">
      <el-form-item label="漏洞名称" required>
        <el-input v-model="vul.title" placeholder="例如：后台登录接口存在SQL注入" />
      </el-form-item>
      <div class="grid grid-cols-1 md:grid-cols-2">
        <el-form-item label="漏洞等级">
          <el-select v-model="vul.level" class="w-full">
            <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="漏洞类型">
          <div class="w-full flex items-center gap-2">
            <el-select v-model="vul.vul_type" filterable class="flex-1">
              <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
            </el-select>
            <el-tooltip content="从漏洞知识库套用该类型的标准描述与修复建议" placement="top">
              <el-button plain @click="applyTemplate(vul)">套用模板</el-button>
            </el-tooltip>
          </div>
        </el-form-item>
        <el-form-item label="所在层">
          <el-select v-model="vul.layer" class="w-full">
            <el-option v-for="(name, code) in meta?.vul_layer" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editId" label="漏洞状态">
          <el-select v-model="vul.status" class="w-full" placeholder="选择漏洞状态">
            <el-option v-for="(name, code) in meta?.vul_status" :key="code" :label="name" :value="Number(code)" />
          </el-select>
        </el-form-item>
        <el-form-item label="影响URL">
          <div class="w-full flex flex-col gap-2">
            <div v-for="(_, uidx) in vul.affected_urls" :key="uidx" class="flex items-center gap-2">
              <el-input v-model="vul.affected_urls[uidx]" placeholder="https://..." class="flex-1" />
              <el-button v-if="vul.affected_urls.length > 1" type="danger" link
                         @click="vul.affected_urls.splice(uidx, 1)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <div>
              <el-button size="small" plain @click="vul.affected_urls.push('')">
                <el-icon class="mr-1"><Plus /></el-icon>添加URL
              </el-button>
            </div>
          </div>
        </el-form-item>
      </div>
      <el-form-item label="漏洞描述">
        <RichEditor v-model="vul.description_html" class="w-full"
                    @update:json="(j: any) => (vul.description_json = j)" />
      </el-form-item>
      <el-form-item label="复现步骤">
        <RichEditor v-model="vul.reproduce_html" class="w-full"
                    @update:json="(j: any) => (vul.reproduce_json = j)" />
      </el-form-item>
      <el-form-item label="修复建议">
        <RichEditor v-model="vul.solution_html" class="w-full"
                    @update:json="(j: any) => (vul.solution_json = j)" />
      </el-form-item>
    </el-form>
  </el-card>

  <div class="max-w-5xl flex items-center gap-2 mb-6">
    <el-button v-if="!editId" @click="addVuln">
      <el-icon class="mr-1"><Plus /></el-icon>新增漏洞
    </el-button>
    <el-button v-if="editId" type="warning" plain @click="router.push(`/vulns/${editId}/retest`)">
      复测
    </el-button>
    <div class="flex-1" />
    <el-button @click="router.back()">取消</el-button>
    <el-button type="primary" :loading="saving" @click="save">
      {{ editId ? '保存' : `提交 ${vulns.length} 个漏洞` }}
    </el-button>
  </div>

  <AssetFormDialog v-model:visible="assetDialogVisible" :asset="assetPrefill" @saved="onAssetCreated" />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import client from '../api/client'
import RichEditor from '../components/RichEditor.vue'
import AssetFormDialog from '../components/AssetFormDialog.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const meta = ref<any>(null)
const saving = ref(false)
const editId = route.name === 'vuln-edit' ? Number(route.params.id) : null
// 从测试计划「录入漏洞」进入时预关联计划
const planId = !editId && route.query.plan_id ? Number(route.query.plan_id) : null
const planName = ref('')

// ---------- 资产选择 ----------
const assetIds = ref<number[]>([])
const assetOptions = ref<any[]>([])
const assetCache = ref<Record<number, any>>({})
const assetLoading = ref(false)
const assetKeyword = ref('')
const assetDialogVisible = ref(false)
const assetPrefill = ref<any>(null)

const selectedAssets = computed(() => assetIds.value.map((id) => assetCache.value[id]).filter(Boolean))

async function searchAssets(keyword = '') {
  assetKeyword.value = keyword
  assetLoading.value = true
  try {
    const { data } = await client.get('/assets', { params: { search: keyword, size: 50 } })
    assetOptions.value = data.items
    for (const a of data.items) assetCache.value[a.id] = a
  } finally {
    assetLoading.value = false
  }
}

function openCreateAsset() {
  assetPrefill.value = assetKeyword.value ? { name: assetKeyword.value } : null
  assetDialogVisible.value = true
}

function onAssetCreated(asset: any) {
  assetCache.value[asset.id] = asset
  assetOptions.value = [asset, ...assetOptions.value.filter((a) => a.id !== asset.id)]
  assetIds.value = [...assetIds.value, asset.id]
  onAssetChange()
}

function onAssetChange() {
  // 自动填充：影响URL 为空时，取首个选中资产的公网/内网URL
  const first = selectedAssets.value[0]
  if (!first) return
  const url = (first.public_urls ?? [])[0]?.url || (first.internal_urls ?? [])[0] || ''
  if (!url) return
  for (const vul of vulns.value) {
    if (!vul.affected_urls.some((u: string) => u.trim())) vul.affected_urls = [url]
  }
}

// ---------- 漏洞表单（新建支持多块，编辑单块） ----------
const emptyVul = () => ({
  title: '', level: 30, vul_type: 75, layer: 10, affected_urls: [''],
  description_html: '', description_json: null,
  reproduce_html: '', reproduce_json: null,
  solution_html: '', solution_json: null,
  source: 10, score: 0, risk_score: 0, left_risk_score: 0, asset_level: 0,
})
const vulns = ref<any[]>([emptyVul()])

// 影响URL 多值与后端单字段（换行分隔）互转
const joinUrls = (urls: string[]) => (urls ?? []).map((u) => u.trim()).filter(Boolean).join('\n')
const splitUrls = (raw: string) => {
  const arr = (raw ?? '').split('\n').map((u) => u.trim()).filter(Boolean)
  return arr.length ? arr : ['']
}

function addVuln() {
  const block = emptyVul()
  const first = selectedAssets.value[0]
  const url = (first?.public_urls ?? [])[0]?.url || (first?.internal_urls ?? [])[0] || ''
  if (url) block.affected_urls = [url]
  vulns.value.push(block)
}

// 从知识库按漏洞类型套用标准描述 / 修复建议（危害说明附加在描述后）
async function applyTemplate(vul: any) {
  let entry: any
  try {
    ;({ data: entry } = await client.get(`/knowledge/by-type/${vul.vul_type}`))
  } catch {
    return // 404 提示由拦截器统一处理
  }
  if ((vul.description_html || '').trim() || (vul.solution_html || '').trim()) {
    try {
      await ElMessageBox.confirm('当前已填写漏洞描述或修复建议，套用模板将覆盖这些内容，是否继续？', '套用模板', { type: 'warning' })
    } catch {
      return
    }
  }
  let descHtml = entry.description_html || ''
  if (entry.harm_html) descHtml += `<p><strong>危害说明：</strong></p>${entry.harm_html}`
  vul.description_html = descHtml
  vul.description_json = entry.harm_html ? null : entry.description_json
  vul.solution_html = entry.solution_html || ''
  vul.solution_json = entry.solution_json
  ElMessage.success('已套用知识库模板')
}

async function save() {
  for (const [i, vul] of vulns.value.entries()) {
    if (!vul.title.trim()) return ElMessage.warning(`请填写漏洞 #${i + 1} 的名称`)
  }
  if (!assetIds.value.length) return ElMessage.warning('请选择测试目标资产')
  saving.value = true
  try {
    // 影响URL 多值序列化为后端单字段（换行分隔），剔除前端临时字段
    const toPayload = (v: any) => {
      const { affected_urls, ...rest } = v
      return { ...rest, affected_url: joinUrls(affected_urls) }
    }
    if (editId) {
      await client.put(`/vulns/${editId}`, { ...toPayload(vulns.value[0]), asset_ids: assetIds.value })
      ElMessage.success('保存成功')
      router.push(`/vulns/${editId}`)
    } else {
      const { data } = await client.post('/vulns/batch', {
        asset_ids: assetIds.value,
        vulns: vulns.value.map((v) => {
          const payload = toPayload(v)
          return planId ? { ...payload, testing_plan_id: planId } : payload
        }),
      })
      ElMessage.success(`成功提交 ${data.length} 个漏洞`)
      router.push(data.length === 1 ? `/vulns/${data[0].id}` : '/vulns')
    }
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  await searchAssets()
  if (planId) {
    const { data } = await client.get('/testing-plans', { params: { size: 100 } }).catch(() => ({ data: { items: [] } }))
    planName.value = data.items?.find((p: any) => p.id === planId)?.system_name ?? ''
  }
  if (editId) {
    const { data: vul } = await client.get(`/vulns/${editId}`)
    vulns.value = [{ ...emptyVul(), ...vul, affected_urls: splitUrls(vul.affected_url) }]
    assetIds.value = vul.asset_ids ?? []
    for (const a of vul.assets ?? []) {
      if (!assetCache.value[a.id]) {
        assetCache.value[a.id] = a
        assetOptions.value.push(a)
      }
    }
  }
})
</script>
