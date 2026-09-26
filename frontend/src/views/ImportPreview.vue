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
        <!-- P1-5：重复漏洞候选检查（标题/URL/等级/工单/相似度并列，可合并或保留为独立记录） -->
        <el-button :loading="dupLoading" @click="openDuplicates">重复候选检查</el-button>
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
      <el-alert
        v-if="mismatchItems.length"
        class="mt-3"
        type="warning"
        :closable="false"
        show-icon
        title="风险问题汇总与风险问题详情等级不一致"
      >
        <div class="flex items-center gap-2 text-xs">
          <span>共 {{ mismatchItems.length }} 条记录，入库将以风险问题详情的等级为准。</span>
          <el-button link type="primary" size="small" @click="mismatchVisible = true">查看详情</el-button>
        </div>
      </el-alert>
    </el-card>


    <el-card v-for="rec in records" :key="rec.id" shadow="never"
             :class="{ 'opacity-50': rec.status === 'discarded' }">
      <div class="flex items-center gap-2 mb-3">
        <el-checkbox v-model="checked[rec.id]" :disabled="rec.status !== 'parsed'" />
        <span class="dot-tag" :style="dotStyle(importRecordMeta(rec.status).color)">
          <i></i>{{ importRecordMeta(rec.status).label }}
        </span>
        <span v-if="rec.parse_error" class="ktag">{{ rec.parse_error }}</span>
        <span v-if="rec.merge_vul_id" class="ktag" style="color: var(--tl-primary)">
          合并到漏洞 #{{ rec.merge_vul_id }}
        </span>
        <div class="flex-1" />
        <el-button v-if="rec.merge_vul_id" size="small" link @click="mergeRecord(rec, null)">取消合并</el-button>
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
            <!-- 与漏洞录入页同一编辑器：支持粘贴多行/分号文本自动切分、去重与行内校验 -->
            <AffectedUrlEditor v-model="rec.affected_url" />
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

    <ImportLevelMismatchDialog v-model="mismatchVisible" :items="mismatchItems" />

    <!-- P1-5 重复候选：标题 / URL / 等级 / 关联工单 / 相似度并列；可合并或保留为独立记录 -->
    <el-dialog v-model="dupVisible" title="重复漏洞候选" width="960px">
      <div class="text-xs text-gray-400 mb-2">
        相似度 ≥ 50%（或 URL 命中）的已入库漏洞会被列为候选；选择「合并」后该记录入库时将更新目标漏洞而非新建。
      </div>
      <el-empty v-if="!duplicates.length" description="未发现重复候选，可按独立记录入库" :image-size="70" />
      <div v-for="g in duplicates" :key="g.record_id" class="dup-group">
        <div class="flex items-center gap-2 mb-1">
          <span class="text-sm font-semibold">{{ g.title }}</span>
          <span class="dot-tag" :style="levelDotStyle(g.level)"><i></i>{{ meta?.vul_level?.[g.level] }}</span>
          <span v-if="g.merge_vul_id" class="ktag" style="color: var(--tl-primary)">已选合并 #{{ g.merge_vul_id }}</span>
        </div>
        <el-table :data="g.candidates" size="small" stripe>
          <el-table-column label="候选漏洞" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <el-link type="primary" @click="router.push(`/vulns/${row.vul_id}`)">#{{ row.vul_id }} {{ row.title }}</el-link>
            </template>
          </el-table-column>
          <el-table-column label="等级" width="90">
            <template #default="{ row }">
              <span class="dot-tag" :style="levelDotStyle(row.level)"><i></i>{{ meta?.vul_level?.[row.level] }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">{{ meta?.vul_status?.[row.status] ?? row.status }}</template>
          </el-table-column>
          <el-table-column label="关联工单" width="140">
            <template #default="{ row }">{{ row.ticket_id || '-' }}</template>
          </el-table-column>
          <el-table-column label="相似度" width="100">
            <template #default="{ row }"><span class="num">{{ Math.round(row.similarity * 100) }}%</span></template>
          </el-table-column>
          <el-table-column label="操作" width="150" class-name="op-col">
            <template #default="{ row }">
              <el-button size="small" type="primary" link
                         :disabled="g.merge_vul_id === row.vul_id"
                         @click="mergeRecord(g, row.vul_id)">合并到该漏洞</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" link class="mt-1" @click="mergeRecord(g, null)">保留为独立记录</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import AffectedUrlEditor from '../components/AffectedUrlEditor.vue'
import ImportLevelMismatchDialog from '../components/ImportLevelMismatchDialog.vue'
import { usePlanAssetLink } from '../composables/usePlanAssetLink'
import { useAuthStore } from '../stores/auth'
import { dotStyle, importRecordMeta, levelDotStyle } from '../utils/colors'
import { safeHtml } from '../utils/html'
import { joinAffectedUrl, parseAffectedUrl, validateAffectedUrls } from '../utils/urls'
import type {
  Asset, ImportBatch, ImportDuplicateGroup, ImportLevelMismatch, ImportRecord, Items, Report, TestingPlan,
} from '../types'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const batch = ref<ImportBatch | null>(null)
const records = ref<ImportRecord[]>([])
const assets = ref<Asset[]>([])
const reports = ref<Report[]>([])
const reportId = ref<number | null>(null)
const plans = ref<TestingPlan[]>([])
const meta = ref<Record<string, Record<number, string>> | null>(null)
const editing = ref<number | null>(null)
const checked = reactive<Record<number, boolean>>({})
const loading = ref(false)
// 等级不一致提醒：风险汇总与风险详情等级不一致的记录（仅在首次加载时自动弹窗，横幅可再次查看）
const mismatchItems = ref<ImportLevelMismatch[]>([])
const mismatchVisible = ref(false)
const mismatchNotified = ref(false)

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
    const { data } = await client.get<{ batch: ImportBatch; records: ImportRecord[] }>(
      `/imports/${route.params.id}`,
    )
    batch.value = data.batch
    records.value = data.records
    for (const r of data.records) if (r.status === 'parsed' && checked[r.id] === undefined) checked[r.id] = true
    await loadLevelMismatch()
  } finally {
    loading.value = false
  }
}

// 报告存在「风险问题汇总与风险问题详情等级不一致」的记录时提醒用户
async function loadLevelMismatch() {
  const { data } = await client.get<ImportLevelMismatch[]>('/imports/level-mismatches', {
    params: { batch_ids: route.params.id },
  })
  mismatchItems.value = data
  if (data.length && !mismatchNotified.value) {
    mismatchNotified.value = true
    mismatchVisible.value = true
  }
}

async function saveRecord(rec: ImportRecord) {
  // 影响URL 与录入页同一口径：不合规时中止提交（错误已由编辑器行内提示，无需弹窗）
  const parsed = parseAffectedUrl(rec.affected_url)
  if (!validateAffectedUrls(parsed).ok) return
  await client.put(`/imports/records/${rec.id}`, {
    title: rec.title, level: rec.level, vul_type: rec.vul_type,
    affected_url: joinAffectedUrl(parsed),
  })
  ElMessage.success('修正已保存')
  editing.value = null
  await load()
}

async function discard(rec: ImportRecord) {
  await client.post(`/imports/records/${rec.id}/discard`)
  checked[rec.id] = false
  await load()
}

// ---------- P1-5 重复候选与合并 ----------
const dupVisible = ref(false)
const dupLoading = ref(false)
const duplicates = ref<ImportDuplicateGroup[]>([])

async function openDuplicates() {
  dupLoading.value = true
  try {
    duplicates.value = (await client.get<ImportDuplicateGroup[]>(`/imports/${route.params.id}/duplicates`)).data
    dupVisible.value = true
  } finally {
    dupLoading.value = false
  }
}

/** 合并到已有漏洞（vulId）或保留为独立记录（null）；对单条记录与候选分组两种入参通用 */
async function mergeRecord(target: ImportRecord | ImportDuplicateGroup, vulId: number | null) {
  const recordId = 'record_id' in target ? target.record_id : target.id
  await client.post(`/imports/records/${recordId}/merge`, { vul_id: vulId })
  target.merge_vul_id = vulId
  ElMessage.success(vulId ? `已选择合并到漏洞 #${vulId}` : '已设为独立记录')
  await load()
}

async function confirm() {
  const { data } = await client.post<{ msg: string }>(`/imports/${route.params.id}/confirm`, {
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
    client.get<Items<Asset>>('/assets', { params: { size: 100 } }),
    // 无报告权限时静默降级为不可关联
    client.get<Items<Report>>('/reports', { params: { size: 100 } }).catch(() => ({ data: { items: [] } })),
    // 无专项权限时静默降级为不可关联计划
    client.get<Items<TestingPlan>>('/testing-plans', { params: { size: 100 } }).catch(() => ({ data: { items: [] } })),
  ])
  assets.value = assetPage.items
  reports.value = reportPage.items
  plans.value = planPage.items
  await load()
})
</script>
