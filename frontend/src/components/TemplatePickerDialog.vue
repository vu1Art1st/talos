<template>
  <!-- 从漏洞模板库套用：默认「当前漏洞类型」（等价原有模板内搜索），可切「全部模板」跨模板检索 -->
  <el-dialog
             :model-value="modelValue"
             :close-on-click-modal="false"
             title="从漏洞模板库套用"
             width="760px"
             top="5vh"
             append-to-body
             @update:model-value="(v: boolean) => emit('update:modelValue', v)">
    <div class="flex items-center flex-wrap gap-2 mb-2">
      <el-radio-group v-model="scope" size="small">
        <el-radio-button value="type" :disabled="currentType == null">
          当前类型{{ currentTypeName ? `：${currentTypeName}` : '' }}
        </el-radio-button>
        <el-radio-button value="all">全部模板</el-radio-button>
      </el-radio-group>
      <span class="text-xs text-gray-400">
        {{ scope === 'all'
          ? '跨模板检索：不确定漏洞类型时，按漏洞名称 / 编号（CVE 等）/ 关键字搜索'
          : '仅检索当前漏洞类型下的模板' }}
      </span>
    </div>

    <el-input v-model="q" clearable class="mb-2"
              placeholder="搜索漏洞名称 / 编号（CVE 等）/ 关键字"
              @keydown="onKeydown">
      <template #prefix><el-icon><Search /></el-icon></template>
    </el-input>

    <div class="flex flex-wrap items-center gap-2 mb-2">
      <el-select v-model="filterTypes" multiple collapse-tags collapse-tags-tooltip filterable
                 :disabled="scope === 'type'" placeholder="漏洞类型" class="tl-tpl-flt">
        <el-option v-for="(name, code) in typeOptions" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-select v-model="filterLevels" multiple collapse-tags collapse-tags-tooltip
                 placeholder="危害等级" class="tl-tpl-flt-sm">
        <el-option v-for="(name, code) in levelOptions" :key="code" :label="name" :value="Number(code)" />
      </el-select>
      <el-input v-model="creator" placeholder="维护人" clearable class="tl-tpl-flt-sm" />
      <!-- 日期区间根节点是 .el-input__wrapper（Element Plus 给了 flex-grow:1），flex 行内必须 !grow-0 -->
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
                      start-placeholder="更新起" end-placeholder="更新止" unlink-panels
                      class="!w-60 !grow-0" />
      <el-select v-model="sort" class="tl-tpl-flt-sm">
        <el-option label="按相关度" value="relevance" />
        <el-option label="按更新时间" value="update_time" />
        <el-option label="按危害等级" value="severity_level" />
        <el-option label="按名称" value="name" />
      </el-select>
      <el-tooltip content="同时检索描述 / 危害说明 / 修复建议正文，结果可能包含较多弱相关项" placement="top">
        <el-checkbox v-model="deep">含正文</el-checkbox>
      </el-tooltip>
      <el-button link type="primary" @click="resetFilters">重置</el-button>
    </div>

    <div ref="listRef" v-loading="loading" class="flex flex-col gap-2 h-[42vh] min-h-[180px] overflow-auto pr-1">
      <div v-for="(t, i) in items" :key="t.id" :data-idx="i"
           :class="['rounded-lg border p-3 cursor-pointer transition',
                    i === activeIndex ? 'border-brand-400 bg-gray-50' : 'border-gray-200 hover:border-brand-400',
                    pickingId === t.id ? 'opacity-60' : '']"
           @click="choose(t)" @mouseenter="activeIndex = i">
        <div class="flex items-center gap-2">
          <span class="tl-tag shrink-0" :style="levelSoftStyle(t.severity_level)">{{ levelName(t.severity_level) }}</span>
          <span class="font-medium" v-html="highlight(t.vulnerability_name, q.trim())"></span>
        </div>
        <!-- 展示所属模板路径：漏洞模板库 / 漏洞类型 / 漏洞名称（末段即当前条目，面包屑惯例） -->
        <div class="text-xs text-gray-400 mt-1 truncate" :title="pathOf(t)">
          漏洞模板库 / {{ t.vul_type_name }} / {{ t.vulnerability_name }}
        </div>
        <div class="text-xs text-gray-400 mt-1">
          维护人 {{ t.username || '-' }} · 更新于 {{ fmtDateTime(t.update_time) }}
        </div>
        <p class="text-xs text-gray-500 mt-1 line-clamp-2" v-html="highlight(t.summary, q.trim())"></p>
      </div>
      <el-empty v-if="!loading && !items.length" :image-size="70" :description="emptyText">
        <el-button v-if="scope === 'type'" type="primary" plain @click="scope = 'all'">
          在全部模板中搜索
        </el-button>
      </el-empty>
    </div>

    <template #footer>
      <span class="text-xs text-gray-400 mr-auto">
        共 {{ total }} 条{{ scope === 'type' ? '（当前类型）' : '（全部模板）' }}
      </span>
      <el-pagination v-if="total > size" small background layout="prev, pager, next"
                     :total="total" :page-size="size" :current-page="page"
                     @current-change="(p: number) => (page = p)" />
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { getKnowledgeEntry, searchKnowledge } from '../api/knowledge'
import type { KnowledgeSearchItem } from '../api/knowledge'
import { useAuthStore } from '../stores/auth'
import { levelName, levelSoftStyle } from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import { highlight } from '../utils/highlight'
import type { KnowledgeTemplate } from '../types'

// 跨模板搜索弹窗：不预选漏洞类型即可按名称/编号/关键字检索全部模板，
// 选中后按 ID 取完整正文并 emit select，由宿主决定回填（本组件不关闭自身，便于覆盖确认取消后继续挑选）。
const props = defineProps<{
  modelValue: boolean
  /** 当前漏洞卡片的漏洞类型码：作为默认作用域；缺省则直接进入「全部模板」 */
  vulType?: number | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'select', entry: KnowledgeTemplate): void
}>()

const auth = useAuthStore()
const currentType = computed(() => props.vulType ?? null)
const typeOptions = ref<Record<string, string>>({})
const levelOptions = ref<Record<string, string>>({})
const currentTypeName = computed(() =>
  currentType.value == null ? '' : (typeOptions.value[currentType.value] ?? ''),
)

const scope = ref<'type' | 'all'>('all')
const q = ref('')
const filterTypes = ref<number[]>([])
const filterLevels = ref<number[]>([])
const creator = ref('')
const dateRange = ref<[string, string] | null>(null)
const deep = ref(false)
const sort = ref('relevance')
const page = ref(1)
const size = 10

const loading = ref(false)
const items = ref<KnowledgeSearchItem[]>([])
const total = ref(0)
const activeIndex = ref(-1)
const pickingId = ref<number | null>(null)
const listRef = ref<HTMLElement>()

let seq = 0            // 请求序号：丢弃过期响应，避免快速输入时错序渲染
let timer: ReturnType<typeof setTimeout> | undefined
let suppress = false   // 打开弹窗批量重置筛选时抑制 watcher 的重复拉取

const emptyText = computed(() => {
  const kw = q.value.trim()
  if (kw) return scope.value === 'type' ? `当前类型下未找到匹配「${kw}」的模板` : `未找到匹配「${kw}」的模板`
  return scope.value === 'type' ? '该漏洞类型暂无模板' : '暂无模板'
})

const pathOf = (t: KnowledgeSearchItem) =>
  `漏洞模板库 / ${t.vul_type_name} / ${t.vulnerability_name}`

async function fetchList() {
  const my = ++seq
  loading.value = true
  try {
    const { data } = await searchKnowledge({
      q: q.value.trim(),
      vul_type: scope.value === 'type' && currentType.value != null
        ? [currentType.value]
        : filterTypes.value,
      severity_level: filterLevels.value,
      creator: creator.value.trim(),
      updated_from: dateRange.value?.[0],
      updated_to: dateRange.value?.[1],
      deep: deep.value,
      sort: sort.value,
      order: sort.value === 'relevance' ? undefined : 'desc',
      page: page.value,
      size,
    })
    if (my !== seq) return
    items.value = data.items ?? []
    total.value = data.total ?? 0
    activeIndex.value = items.value.length ? 0 : -1
  } catch {
    // 失败提示由 client 拦截器统一处理，此处仅收敛状态避免残留旧结果
    if (my !== seq) return
    items.value = []
    total.value = 0
    activeIndex.value = -1
  } finally {
    if (my === seq) loading.value = false
  }
}

/** 筛选变化：回第一页并刷新（page 变化由 watch(page) 兜底触发，避免重复请求） */
function refetch() {
  if (suppress) return
  if (page.value !== 1) {
    page.value = 1
    return
  }
  fetchList()
}

function scheduleFetch() {
  if (suppress) return
  clearTimeout(timer)
  timer = setTimeout(refetch, 250)
}

function move(step: number) {
  if (!items.value.length) return
  activeIndex.value = (activeIndex.value + step + items.value.length) % items.value.length
  // 用 data-idx 定位：v-loading 的遮罩会占用容器子节点，不能按下标取 children
  listRef.value
    ?.querySelector<HTMLElement>(`[data-idx="${activeIndex.value}"]`)
    ?.scrollIntoView({ block: 'nearest' })
}

/** 键盘导航：↑↓ 移动、Enter 套用；组合输入（中文输入法）期间不拦截按键 */
function onKeydown(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    move(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    move(-1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const t = items.value[activeIndex.value]
    if (t) choose(t)
  }
}

async function choose(t: KnowledgeSearchItem) {
  if (pickingId.value != null) return
  pickingId.value = t.id
  try {
    // 列表只带摘要，套用前按 ID 取完整正文（描述/危害/修复建议/CVSS 向量）
    const { data } = await getKnowledgeEntry(t.id)
    emit('select', data)
  } finally {
    pickingId.value = null
  }
}

function resetFilters() {
  suppress = true
  q.value = ''
  filterTypes.value = []
  filterLevels.value = []
  creator.value = ''
  dateRange.value = null
  deep.value = false
  sort.value = 'relevance'
  page.value = 1
  nextTick(() => {
    suppress = false
    fetchList()
  })
}

async function onOpen() {
  clearTimeout(timer)
  const meta: Record<string, Record<number, string>> | null = await auth.fetchMeta()
  typeOptions.value = meta?.vul_type ?? {}
  levelOptions.value = meta?.vul_level ?? {}
  suppress = true
  scope.value = currentType.value == null ? 'all' : 'type'
  q.value = ''
  filterTypes.value = []
  filterLevels.value = []
  creator.value = ''
  dateRange.value = null
  deep.value = false
  sort.value = 'relevance'
  page.value = 1
  pickingId.value = null
  await nextTick()
  suppress = false
  await fetchList()
}

// 打开即初始化（用 prop watcher 而非 el-dialog 的 open 事件：不依赖过渡钩子，行为更确定）
watch(() => props.modelValue, (v) => { if (v) onOpen() })
watch(q, scheduleFetch)
// 作用域切换时清空类型筛选（两个入口语义不能叠加）——必须先于下面的数组 watcher 创建，
// 这样同一次 scope 变更里 refetch 只按清空后的条件请求一次
watch(scope, () => { filterTypes.value = [] })
watch([scope, filterTypes, filterLevels, creator, dateRange, deep, sort], refetch)
watch(page, () => { if (!suppress) fetchList() })
</script>

<style scoped>
/* 关键词高亮：沿用主题交互色，避免 mark 默认黄底在暗色下刺眼 */
:deep(.tl-hl) {
  background: transparent;
  color: var(--tl-primary);
  font-weight: 600;
}

.tl-tpl-flt {
  width: 168px;
}

.tl-tpl-flt-sm {
  width: 132px;
}
</style>
