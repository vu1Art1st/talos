<template>
  <!-- 漏洞详情弹窗（渗透测试工单/远程检测共用）：点击漏洞名称就地弹出，不再跳转历史漏洞库页面 -->
  <el-dialog
         :close-on-click-modal="false" :model-value="visible" title="漏洞详情" append-to-body :width="dialogWidth"
             @update:model-value="emit('update:visible', $event)">
    <div v-loading="loading" element-loading-text="正在加载漏洞信息…">
      <template v-if="vuln">
        <div class="flex items-start justify-between gap-3">
          <div class="text-lg font-semibold text-gray-800 leading-snug break-words">{{ vuln.title }}</div>
          <el-button class="shrink-0" :icon="Close" circle plain size="small"
                     @click="emit('update:visible', false)" aria-label="关闭" />
        </div>
        <div class="flex flex-wrap items-center gap-2 mt-3">
          <span class="tl-tag" :style="levelSoftStyle(vuln.level)">{{ levelName(vuln.level) }}</span>
          <span class="tl-tag" :style="vulTypeSoftStyle(vuln.vul_type)">
            {{ meta?.vul_type?.[vuln.vul_type ?? 0] ?? vuln.vul_type }}
          </span>
          <span class="tl-tag" :style="statusSoftStyleWithRetest(vuln.status, vuln.is_retest)">
            {{ statusLabel(vuln.status, vuln.is_retest, vulStatusMap) }}
          </span>
          <span v-if="vuln.assets?.length" class="tl-tag" :style="softStyle(STAT_CARD_COLORS.gray)">
            关联资产：{{ vuln.assets.map((a) => a.name).join('、') }}
          </span>
        </div>
        <el-descriptions :column="detailCols" border class="mt-4" size="small">
          <el-descriptions-item label="影响URL" :span="detailCols">
            <div v-if="affectedUrls.length" class="flex flex-col gap-0.5">
              <span v-for="(u, i) in affectedUrls" :key="i">{{ u }}</span>
            </div>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="vuln.testing_plan_id" label="渗透测试工单">已关联工单</el-descriptions-item>
        </el-descriptions>
        <div v-if="sections.length" class="mt-4 space-y-4">
          <section v-for="sec in sections" :key="sec.title">
            <h4 class="text-sm font-semibold text-gray-700 mb-1.5">{{ sec.title }}</h4>
            <div v-if="sec.html" class="rich-content" v-html="safeHtml(sec.html)" />
            <div v-else class="text-sm text-gray-400">暂无内容</div>
          </section>
        </div>
      </template>
      <el-empty v-else-if="!loading" description="未获取到漏洞详情" :image-size="80" />
    </div>
    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" :disabled="!vuln" @click="goFullDetail">查看完整详情</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Close } from '@element-plus/icons-vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { Vuln } from '../types'
import {
  levelName,
  levelSoftStyle,
  softStyle,
  STAT_CARD_COLORS,
  statusSoftStyleWithRetest,
  statusLabel,
  vulTypeSoftStyle,
} from '../utils/colors'
import { safeHtml } from '../utils/html'

const props = defineProps<{
  visible: boolean
  /** 待展示的漏洞 ID；为空时展示空态 */
  vulnId?: number | null
}>()
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
}>()

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const vuln = ref<Vuln | null>(null)
const meta = ref<Record<string, Record<number, string>> | null>(null)
const vulStatusMap = computed<Record<number, string>>(() => meta.value?.vul_status ?? {})

// 影响URL 多值（后端换行分隔存储）逐行展示
const affectedUrls = computed<string[]>(() =>
  (vuln.value?.affected_url ?? '').split('\n').map((u: string) => u.trim()).filter(Boolean))
// 描述 / 复现 / 修复建议 等富文本区段（仅展示有内容的）
const sections = computed(() =>
  [
    { title: '漏洞描述', html: vuln.value?.description_html },
    { title: '复现步骤', html: vuln.value?.reproduce_html },
    { title: '修复建议', html: vuln.value?.solution_html },
  ].filter((s) => s.html || s.title === '漏洞描述'))
// 移动端单列、桌面端双列（响应式）；弹窗宽度归档 L=800
const dialogWidth = computed(() =>
  typeof window !== 'undefined' && window.innerWidth < 640 ? '92%' : '800px')
const detailCols = computed(() =>
  typeof window !== 'undefined' && window.innerWidth < 640 ? 1 : 2)

async function load(id: number) {
  loading.value = true
  vuln.value = null
  try {
    if (!meta.value?.vul_type) meta.value = await auth.fetchMeta()
    const { data } = await client.get<Vuln>(`/vulns/${id}`)
    vuln.value = data
  } finally {
    loading.value = false
  }
}

function goFullDetail() {
  if (vuln.value?.id) router.push(`/vulns/${vuln.value.id}`)
}

watch(
  () => [props.visible, props.vulnId] as const,
  ([visible, id]) => {
    if (!visible) return
    if (id) load(id)
    else vuln.value = null
  },
  { immediate: true },
)
</script>
