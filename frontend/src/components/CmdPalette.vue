<template>
  <!-- ⌘K 命令面板（demo-2 同款交互）：页面跳转 + 动作 + 全局搜索（/api/v1/search） -->
  <Teleport to="body">
    <div v-if="ui.cmdkVisible" class="cmdk-mask" @click.self="close">
      <div class="cmdk" role="dialog" aria-label="命令面板">
        <div class="cmdk-input">
          <el-icon :size="15"><Search /></el-icon>
          <input ref="inputRef" v-model="q" placeholder="搜索漏洞、资产、工单、报告或跳转页面…" @input="onSearch" />
          <kbd class="kbd">esc</kbd>
        </div>
        <div ref="listRef" class="cmdk-list">
          <template v-for="group in groups" :key="group.name">
            <template v-if="group.items.length">
              <div class="cmdk-group">{{ group.name }}</div>
              <div v-for="item in group.items" :key="item.key" class="cmdk-item"
                   :class="{ sel: item.key === selKey }" @mouseenter="selKey = item.key" @click="run(item)">
                <el-icon v-if="item.icon" :size="14"><component :is="item.icon" /></el-icon>
                <span class="cmdk-label">{{ item.label }}</span>
                <span v-if="item.sub" class="cmdk-sub">{{ item.sub }}</span>
                <kbd v-if="item.hint" class="kbd">{{ item.hint }}</kbd>
              </div>
            </template>
          </template>
          <div v-if="!flat.length" class="cmdk-empty">没有匹配的结果</div>
        </div>
        <div class="cmdk-foot">
          <span><kbd class="kbd">↑</kbd><kbd class="kbd">↓</kbd>选择</span>
          <span><kbd class="kbd">↵</kbd>打开</span>
          <span><kbd class="kbd">esc</kbd>关闭</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Aim, Bell, Collection, Connection, DataLine, Document, Flag, Key, Memo,
  Monitor, Moon, OfficeBuilding, Sunny, Tickets, User, Warning,
} from '@element-plus/icons-vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { useUiStore } from '../stores/ui'

interface CmdItem {
  key: string
  label: string
  icon?: unknown
  sub?: string
  hint?: string
  run: () => void
}

const ui = useUiStore()
const theme = useThemeStore()
const auth = useAuthStore()
const router = useRouter()

const q = ref('')
const inputRef = ref<HTMLInputElement>()
const listRef = ref<HTMLElement>()
const selKey = ref('')
const results = ref<CmdItem[]>([])

/* ---- 静态跳转项（与侧边栏同源，按权限显隐） ---- */
const jumpItems = computed<CmdItem[]>(() => {
  const p = (path: string) => () => { router.push(path); close() }
  const list: CmdItem[] = [
    { key: 'nav-dashboard', label: '安全态势', icon: DataLine, hint: '↵', run: p('/dashboard') },
  ]
  if (auth.hasPerm('special:manage')) {
    list.push({ key: 'nav-testing', label: '渗透测试工单', icon: Tickets, run: p('/testing-plans') })
    list.push({ key: 'nav-nonpen', label: '漏扫基线工单', icon: Aim, run: p('/nonpen-plans') })
  }
  list.push({ key: 'nav-vulns', label: '历史漏洞库', icon: Warning, run: p('/vulns') })
  list.push({ key: 'nav-knowledge', label: '漏洞模板库', icon: Collection, run: p('/knowledge') })
  if (auth.hasPerm('report:manage')) {
    list.push({ key: 'nav-reports', label: '报告中心', icon: Document, run: p('/reports') })
    list.push({ key: 'nav-imports', label: 'Word 导入', icon: Document, run: p('/reports/imports') })
  }
  if (auth.hasPerm('asset:manage')) {
    list.push({ key: 'nav-assets', label: '资产台账', icon: Monitor, run: p('/assets') })
    list.push({ key: 'nav-groups', label: '组织管理', icon: OfficeBuilding, run: p('/assets/groups') })
  }
  if (auth.hasPerm('special:manage')) {
    list.push({ key: 'nav-remote', label: '远程检测', icon: Connection, run: p('/remote-testings') })
    list.push({ key: 'nav-spring', label: '春耕行动', icon: Flag, run: p('/spring-actions') })
  }
  if (auth.hasPerm('user:manage')) {
    list.push({ key: 'nav-users', label: '用户管理', icon: User, run: p('/users') })
    list.push({ key: 'nav-roles', label: '权限管理', icon: Key, run: p('/roles') })
  }
  if (auth.hasPerm('system:manage')) {
    list.push({ key: 'nav-audit', label: '审计日志', icon: Memo, run: p('/audit') })
    list.push({ key: 'nav-notify', label: '通知渠道', icon: Bell, run: p('/notify-channels') })
  }
  list.push({ key: 'nav-tokens', label: '访问令牌', icon: Key, run: p('/tokens') })
  return list
})

const actionItems = computed<CmdItem[]>(() => [
  {
    key: 'act-theme', label: theme.dark ? '切换到浅色模式' : '切换到暗黑模式',
    icon: theme.dark ? Sunny : Moon, hint: '↵',
    run: () => { theme.toggle(); close() },
  },
])

/* ---- 分组与扁平列表（过滤 + 搜索结果排序在前） ---- */
const groups = computed(() => {
  const kw = q.value.trim().toLowerCase()
  const hit = (it: CmdItem) => !kw || it.label.toLowerCase().includes(kw) || (it.sub ?? '').toLowerCase().includes(kw)
  return [
    { name: '搜索结果', items: results.value },
    { name: '快速跳转', items: jumpItems.value.filter(hit) },
    { name: '操作', items: actionItems.value.filter(hit) },
  ]
})
const flat = computed(() => groups.value.flatMap(g => g.items))
watch(flat, list => { if (!list.some(i => i.key === selKey.value)) selKey.value = list[0]?.key ?? '' })
watch(q, () => { selKey.value = flat.value[0]?.key ?? '' })

/* ---- 全局搜索（后端 /api/v1/search，接口未就绪或失败时静默为空） ---- */
let searchTimer: ReturnType<typeof setTimeout> | undefined
function onSearch() {
  clearTimeout(searchTimer)
  const kw = q.value.trim()
  if (!kw) { results.value = []; return }
  searchTimer = setTimeout(async () => {
    try {
      const { data } = await client.get('/search', { params: { q: kw } })
      const r = data ?? {}
      const items: CmdItem[] = []
      for (const v of r.vulns ?? []) items.push({
        key: `s-vuln-${v.id}`, label: v.title ?? String(v.id), sub: '漏洞', icon: Warning,
        run: () => { router.push(`/vulns/${v.id}`); close() },
      })
      for (const a of r.assets ?? []) items.push({
        key: `s-asset-${a.id}`, label: a.name ?? String(a.id), sub: '资产', icon: Monitor,
        run: () => { router.push('/assets'); close() },
      })
      for (const pl of r.plans ?? []) items.push({
        key: `s-plan-${pl.type}-${pl.id}`, label: pl.title ?? String(pl.id),
        sub: pl.type === 'nonpen' ? '漏扫基线工单' : '渗透测试工单', icon: Tickets,
        run: () => { router.push(pl.type === 'nonpen' ? '/nonpen-plans' : '/testing-plans'); close() },
      })
      for (const rp of r.reports ?? []) items.push({
        key: `s-report-${rp.id}`, label: rp.title ?? String(rp.id), sub: '报告', icon: Document,
        run: () => { router.push(`/reports/${rp.id}`); close() },
      })
      results.value = items.slice(0, 8)
    } catch { results.value = [] }
  }, 250)
}

/* ---- 打开 / 关闭 / 键盘 ---- */
function open() {
  ui.openCmdk()
  q.value = ''
  results.value = []
  nextTick(() => inputRef.value?.focus())
}
function close() { ui.closeCmdk() }
function run(item: CmdItem) { item.run() }
function move(delta: number) {
  const list = flat.value
  if (!list.length) return
  const idx = list.findIndex(i => i.key === selKey.value)
  const next = list[(idx + delta + list.length) % list.length]
  selKey.value = next.key
  nextTick(() => listRef.value?.querySelector('.cmdk-item.sel')?.scrollIntoView({ block: 'nearest' }))
}
function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    ui.cmdkVisible ? close() : open()
    return
  }
  if (!ui.cmdkVisible) return
  if (e.key === 'Escape') close()
  else if (e.key === 'ArrowDown') { e.preventDefault(); move(1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
  else if (e.key === 'Enter') {
    e.preventDefault()
    flat.value.find(i => i.key === selKey.value)?.run()
  }
}
onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.cmdk-mask {
  position: fixed;
  inset: 0;
  z-index: 2100;
  background: rgba(4, 8, 6, .45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 14vh;
}
html:not(.dark) .cmdk-mask { background: rgba(20, 30, 26, .30); }
.cmdk {
  width: 560px;
  max-width: calc(100vw - 40px);
  border-radius: 12px;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border-strong);
  box-shadow: 0 16px 48px rgba(15, 23, 20, .30);
  overflow: hidden;
}
.cmdk-input {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--tl-border);
  color: var(--tl-text-3);
}
.cmdk-input input {
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--tl-text-1);
  font: inherit;
  font-size: 13.5px;
}
.cmdk-input input::placeholder { color: var(--tl-text-3); }
.cmdk-list { padding: 8px; max-height: 320px; overflow-y: auto; }
.cmdk-group {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--tl-text-3);
  letter-spacing: .08em;
  margin: 8px 8px 4px;
}
.cmdk-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 7px;
  font-size: 13px;
  color: var(--tl-text-2);
  cursor: pointer;
}
.cmdk-item:hover, .cmdk-item.sel { background: var(--tl-surface-2); color: var(--tl-text-1); }
.cmdk-item.sel { outline: 1px solid var(--tl-border-strong); }
.cmdk-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmdk-sub { font-size: 10.5px; color: var(--tl-text-3); flex: none; }
.cmdk-item .kbd { margin-left: auto; }
.cmdk-empty { padding: 28px 0; text-align: center; color: var(--tl-text-3); font-size: 12.5px; }
.cmdk-foot {
  display: flex;
  gap: 14px;
  padding: 9px 16px;
  border-top: 1px solid var(--tl-border);
  font-size: 11px;
  color: var(--tl-text-3);
}
.cmdk-foot span { display: flex; align-items: center; gap: 4px; }
</style>
