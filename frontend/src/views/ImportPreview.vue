<template>
  <div v-loading="loading" class="space-y-3">
    <el-card shadow="never">
      <!-- 第一行：操作行（返回 / 标题 / 批次信息 / 确认按钮） -->
      <div class="flex flex-wrap items-center gap-3">
        <el-button @click="router.push('/reports/imports')">
          <el-icon class="mr-1"><Back /></el-icon>返回
        </el-button>
        <div class="font-medium text-sm">报告导入确认</div>
        <span v-if="batch" class="ktag">{{ batch.filename }}</span>
        <template v-if="batch?.doc_kind === 'report'">
          <span class="ktag">报告格式</span>
          <span v-if="batch.meta_json?.system_name" class="ktag">{{ batch.meta_json.system_name }}</span>
          <span v-if="batch.meta_json?.report_date" class="ktag">{{ batch.meta_json.report_date }}</span>
          <span v-if="batch.meta_json?.is_retest" class="ktag">复测</span>
        </template>
        <div class="flex-1" />
        <el-button type="primary" :disabled="!selected.length" @click="confirm">
          确认入库（{{ selected.length }} 条）
        </el-button>
      </div>
      <!-- 第二行：三个关联选框独立成行（方案A双行布局，14寸屏不串行） -->
      <div class="flex flex-wrap items-center gap-3 mt-3">
        <el-select v-model="planId" filterable clearable placeholder="关联渗透测试工单（可选）"
                   class="flex-1 min-w-40" size="small">
          <el-option v-for="p in plans" :key="p.id" :label="planLabel(p)" :value="p.id" />
        </el-select>
        <el-select v-model="assetId" filterable clearable placeholder="入库到已有资产（可选）"
                   class="flex-1 min-w-40" size="small">
          <el-option v-for="a in filteredAssets" :key="a.id" :label="a.name" :value="a.id" />
        </el-select>
        <el-select v-model="reportId" filterable clearable placeholder="关联到报告（可选）"
                   class="flex-1 min-w-40" size="small">
          <el-option v-for="r in reports" :key="r.id" :label="r.title" :value="r.id" />
        </el-select>
      </div>
      <div v-if="batch?.doc_kind === 'report'" class="mt-2 text-xs text-gray-400">
        报告格式确认入库时：已选择的渗透测试工单将作为关联计划，未选择则按系统名自动匹配/创建计划与资产（无系统名时复用计划首个关联资产）
      </div>
    </el-card>

    <el-card v-for="rec in records" :key="rec.id" shadow="never"
             :class="{ 'opacity-50': rec.status === 'discarded' }">
      <div class="flex items-center gap-2 mb-3">
        <el-checkbox v-model="checked[rec.id]" :disabled="rec.status !== 'parsed'" />
        <span class="dot-tag" :style="dotStyle(importRecordMeta(rec.status).color)">
          <i></i>{{ importRecordMeta(rec.status).label }}
        </span>
        <span v-if="rec.parse_error" class="ktag">{{ rec.parse_error }}</span>
        <div class="flex-1" />
        <el-button v-if="rec.status !== 'confirmed' && rec.status !== 'discarded'" size="small"
                   @click="editing = editing === rec.id ? null : rec.id">
          {{ editing === rec.id ? '收起' : '修正' }}
        </el-button>
        <el-button v-if="rec.status !== 'confirmed' && rec.status !== 'discarded'" size="small" type="danger" plain
                   @click="discard(rec)">丢弃</el-button>
        <el-button v-if="rec.vul_id" size="small" type="success" link
                   @click="router.push(`/vulns/${rec.vul_id}`)">查看漏洞</el-button>
      </div>

      <template v-if="editing === rec.id">
        <el-form label-width="90px" size="small">
          <el-form-item label="漏洞名称">
            <el-input v-model="rec.title" />
          </el-form-item>
          <div class="grid grid-cols-1 md:grid-cols-2">
            <el-form-item label="等级">
              <el-select v-model="rec.level" class="w-full">
                <el-option v-for="(name, code) in meta?.vul_level" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="rec.vul_type" filterable class="w-full">
                <el-option v-for="(name, code) in meta?.vul_type" :key="code" :label="name" :value="Number(code)" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="影响URL">
            <el-input v-model="rec.affected_url" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="small" @click="saveRecord(rec)">保存修正</el-button>
          </el-form-item>
        </el-form>
      </template>
      <template v-else>
        <div class="font-semibold" style="color: var(--tl-text-1)">{{ rec.title || '（未识别标题）' }}</div>
        <div class="flex gap-2 mt-1 text-sm text-gray-500 items-center min-w-0">
          <span class="dot-tag flex-none" :style="levelDotStyle(rec.level)"><i></i>{{ meta?.vul_level?.[rec.level] }}</span>
          <span class="flex-none">{{ meta?.vul_type?.[rec.vul_type] }}</span>
          <span v-if="rec.affected_url" class="truncate min-w-0 flex-1" :title="rec.affected_url">{{ rec.affected_url }}</span>
        </div>
        <el-collapse class="mt-2">
          <el-collapse-item title="内容预览">
            <div class="rich-content text-sm">
              <h4 v-if="rec.description_html">漏洞描述</h4>
              <div v-html="safeHtml(rec.description_html)" />
              <h4 v-if="rec.reproduce_html">复现步骤</h4>
              <div v-html="safeHtml(rec.reproduce_html)" />
              <h4 v-if="rec.solution_html">修复建议</h4>
              <div v-html="safeHtml(rec.solution_html)" />
              <h4 v-if="rec.retest_html">复测详情</h4>
              <div v-html="safeHtml(rec.retest_html)" />
            </div>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-card>

    <el-empty v-if="!records.length" description="该批次没有解析出漏洞记录，请检查文档是否符合模板" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import { usePlanAssetLink } from '../composables/usePlanAssetLink'
import { useAuthStore } from '../stores/auth'
import { dotStyle, importRecordMeta, levelDotStyle } from '../utils/colors'
import { safeHtml } from '../utils/html'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const batch = ref<any>(null)
const records = ref<any[]>([])
const assets = ref<any[]>([])
const reports = ref<any[]>([])
const reportId = ref<number | null>(null)
const plans = ref<any[]>([])
const meta = ref<any>(null)
const editing = ref<number | null>(null)
const checked = reactive<Record<number, boolean>>({})
const loading = ref(false)

const selected = computed(() =>
  records.value.filter((r) => r.status === 'parsed' && checked[r.id]).map((r) => r.id),
)

// 工单/资产联动（planLabel、filteredAssets、选定工单自动联动资产）：与批量确认对话框共用
const { planId, assetId, planLabel, filteredAssets } = usePlanAssetLink(
  () => plans.value,
  () => assets.value,
)

async function load() {
  loading.value = true
  try {
    const { data } = await client.get(`/imports/${route.params.id}`)
    batch.value = data.batch
    records.value = data.records
    for (const r of data.records) if (r.status === 'parsed' && checked[r.id] === undefined) checked[r.id] = true
  } finally {
    loading.value = false
  }
}

async function saveRecord(rec: any) {
  await client.put(`/imports/records/${rec.id}`, {
    title: rec.title, level: rec.level, vul_type: rec.vul_type, affected_url: rec.affected_url,
  })
  ElMessage.success('修正已保存')
  editing.value = null
  await load()
}

async function discard(rec: any) {
  await client.post(`/imports/records/${rec.id}/discard`)
  checked[rec.id] = false
  await load()
}

async function confirm() {
  const { data } = await client.post(`/imports/${route.params.id}/confirm`, {
    record_ids: selected.value,
    asset_id: assetId.value,
    report_id: reportId.value,
    testing_plan_id: planId.value,
  })
  ElMessage.success(data.msg)
  await load()
}

onMounted(async () => {
  meta.value = await auth.fetchMeta()
  const [{ data: assetPage }, { data: reportPage }, { data: planPage }] = await Promise.all([
    client.get('/assets', { params: { size: 100 } }),
    // 无报告权限时静默降级为不可关联
    client.get('/reports', { params: { size: 100 } }).catch(() => ({ data: { items: [] } })),
    // 无专项权限时静默降级为不可关联计划
    client.get('/testing-plans', { params: { size: 100 } }).catch(() => ({ data: { items: [] } })),
  ])
  assets.value = assetPage.items
  reports.value = reportPage.items
  plans.value = planPage.items
  await load()
})
</script>
