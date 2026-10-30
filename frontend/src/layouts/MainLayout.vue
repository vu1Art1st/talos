<template>
  <el-container class="h-full">
    <el-aside id="primary-navigation"
              aria-label="主导航"
              :width="collapsed ? '64px' : '216px'"
              :class="{ 'mobile-open': mobileNavOpen }"
              :role="isMobile ? 'dialog' : undefined"
              :aria-modal="isMobile ? 'true' : undefined"
              :aria-hidden="isMobile && !mobileNavOpen ? 'true' : undefined"
              :inert="isMobile && !mobileNavOpen"
              class="tl-aside flex flex-col">
      <!-- Logo：双层六边形品牌标志 + 双行文字组 -->
      <div class="flex items-center flex-none tl-logo" :class="collapsed ? 'justify-center' : 'gap-2 px-4'">
        <BrandMark :size="32" class="flex-none" style="color: var(--tl-brand-accent)" />
        <div v-if="!collapsed" class="leading-tight whitespace-nowrap">
          <div class="font-semibold text-lg tl-title">Talos</div>
          <div class="text-2xs font-semibold" style="color: var(--tl-brand-accent)">漏洞管理平台</div>
        </div>
      </div>

      <!-- 平铺分组导航 -->
      <nav ref="navEl" class="flex-1 overflow-y-auto tl-nav">
        <button class="nav-item" :class="{ active: activeMenu === '/dashboard' }"
                :title="collapsed ? '安全态势' : undefined" @click="go('/dashboard')">
          <el-icon :size="15"><DataLine /></el-icon><span v-if="!collapsed">安全态势</span>
        </button>
        <template v-if="!collapsed"><div class="nav-group">漏洞运营</div></template>
        <button class="nav-item" :class="{ active: activeMenu === '/todos' }"
                :title="collapsed ? '个人待办' : undefined" @click="go('/todos')">
          <el-icon :size="15"><Finished /></el-icon><span v-if="!collapsed">个人待办</span>
        </button>
        <button v-if="auth.hasPerm('special:manage')" class="nav-item" :class="{ active: activeMenu === '/testing-plans' }"
                :title="collapsed ? '渗透测试工单' : undefined" @click="go('/testing-plans')">
          <el-icon :size="15"><Tickets /></el-icon><span v-if="!collapsed">渗透测试工单</span>
        </button>
        <button v-if="auth.hasPerm('special:manage')" class="nav-item" :class="{ active: activeMenu === '/nonpen-plans' }"
                :title="collapsed ? '漏扫基线工单' : undefined" @click="go('/nonpen-plans')">
          <el-icon :size="15"><Aim /></el-icon><span v-if="!collapsed">漏扫基线工单</span>
        </button>
        <button class="nav-item" :class="{ active: activeMenu === '/vulns' }"
                :title="collapsed ? '历史漏洞库' : undefined" @click="go('/vulns')">
          <el-icon :size="15"><Warning /></el-icon><span v-if="!collapsed">历史漏洞库</span>
        </button>
        <button class="nav-item" :class="{ active: activeMenu === '/knowledge' }"
                :title="collapsed ? '漏洞模板库' : undefined" @click="go('/knowledge')">
          <el-icon :size="15"><Collection /></el-icon><span v-if="!collapsed">漏洞模板库</span>
        </button>
        <button v-if="auth.hasPerm('report:manage')" class="nav-item" :class="{ active: activeMenu === '/reports' }"
                :title="collapsed ? '报告中心' : undefined" @click="go('/reports')">
          <el-icon :size="15"><Document /></el-icon><span v-if="!collapsed">报告中心</span>
        </button>
        <button v-if="auth.hasPerm('report:manage')" class="nav-item" :class="{ active: activeMenu === '/report-templates' }"
                :title="collapsed ? '报告模板' : undefined" @click="go('/report-templates')">
          <el-icon :size="15"><Files /></el-icon><span v-if="!collapsed">报告模板</span>
        </button>
        <template v-if="auth.hasPerm('asset:manage')">
          <template v-if="!collapsed"><div class="nav-group">资产管理</div></template>
          <button class="nav-item" :class="{ active: activeMenu === '/assets' }"
                  :title="collapsed ? '资产台账' : undefined" @click="go('/assets')">
            <el-icon :size="15"><Monitor /></el-icon><span v-if="!collapsed">资产台账</span>
          </button>
          <button class="nav-item" :class="{ active: activeMenu === '/assets/groups' }"
                  :title="collapsed ? '组织管理' : undefined" @click="go('/assets/groups')">
            <el-icon :size="15"><OfficeBuilding /></el-icon><span v-if="!collapsed">组织管理</span>
          </button>
        </template>
        <template v-if="auth.hasPerm('special:manage')">
          <template v-if="!collapsed"><div class="nav-group">专项管理</div></template>
          <button class="nav-item" :class="{ active: activeMenu === '/remote-testings' }"
                  :title="collapsed ? '远程检测' : undefined" @click="go('/remote-testings')">
            <el-icon :size="15"><Connection /></el-icon><span v-if="!collapsed">远程检测</span>
          </button>
          <button class="nav-item" :class="{ active: activeMenu === '/spring-actions' }"
                  :title="collapsed ? '春耕行动' : undefined" @click="go('/spring-actions')">
            <el-icon :size="15"><Flag /></el-icon><span v-if="!collapsed">春耕行动</span>
          </button>
        </template>
        <template v-if="auth.hasPerm('system:manage') || auth.hasPerm('user:manage')">
          <template v-if="!collapsed"><div class="nav-group">系统管理</div></template>
          <button v-if="auth.hasPerm('user:manage')" class="nav-item" :class="{ active: activeMenu === '/users' }"
                  :title="collapsed ? '用户管理' : undefined" @click="go('/users')">
            <el-icon :size="15"><User /></el-icon><span v-if="!collapsed">用户管理</span>
          </button>
          <button v-if="auth.hasPerm('user:manage')" class="nav-item" :class="{ active: activeMenu === '/roles' }"
                  :title="collapsed ? '权限管理' : undefined" @click="go('/roles')">
            <el-icon :size="15"><Key /></el-icon><span v-if="!collapsed">权限管理</span>
          </button>
          <button v-if="auth.hasPerm('system:manage')" class="nav-item" :class="{ active: activeMenu === '/audit' }"
                  :title="collapsed ? '审计日志' : undefined" @click="go('/audit')">
            <el-icon :size="15"><Memo /></el-icon><span v-if="!collapsed">审计日志</span>
          </button>
          <button v-if="auth.hasPerm('system:manage')" class="nav-item" :class="{ active: activeMenu === '/notify-channels' }"
                  :title="collapsed ? '通知渠道' : undefined" @click="go('/notify-channels')">
            <el-icon :size="15"><Bell /></el-icon><span v-if="!collapsed">通知渠道</span>
          </button>
          <button v-if="auth.hasPerm('system:manage')" class="nav-item" :class="{ active: activeMenu === '/sla-config' }"
                  :title="collapsed ? 'SLA 配置' : undefined" @click="go('/sla-config')">
            <el-icon :size="15"><Timer /></el-icon><span v-if="!collapsed">SLA 配置</span>
          </button>
        </template>
      </nav>

      <!-- 底部：折叠切换（单按钮，按状态切换图标，避免折叠态出现双图标） -->
      <div class="tl-side-foot flex-none">
        <button class="nav-item" :class="{ 'justify-center': collapsed }"
                :title="collapsed ? '展开侧栏' : undefined" @click="collapsed = !collapsed">
          <el-icon :size="15"><Expand v-if="collapsed" /><Fold v-else /></el-icon><span v-if="!collapsed">收起侧栏</span>
        </button>
      </div>
    </el-aside>
    <div v-if="mobileNavOpen" class="mobile-nav-scrim" @click="closeMobileNav" />

    <!-- 显式 direction="vertical"：el-container 靠子组件名检测方向，原生 header 元素会被误判为横向 -->
    <el-container direction="vertical" class="min-w-0">
      <!-- 顶栏：50px 毛玻璃工具栏 -->
      <el-header class="tl-topbar flex items-center gap-3 flex-none" height="52px">
        <button ref="mobileMenuRef" class="icon-btn mobile-menu-btn" type="button"
                aria-label="打开导航" aria-controls="primary-navigation" :aria-expanded="mobileNavOpen"
                @click="openMobileNav">
          <el-icon :size="16"><Menu /></el-icon>
        </button>
        <span class="crumb text-xs text-gray-400">Talos /</span>
        <!-- 来源链：编辑/详情类页面展示可点的来源页（redirect 参数优先，回落浏览器站内历史） -->
        <button v-if="crumbBack" class="crumb-back text-xs" type="button"
                :title="`返回${crumbBack.title}`" @click="onCrumbBack">
          <el-icon :size="11"><ArrowLeft /></el-icon>{{ crumbBack.title }}
        </button>
        <span v-if="crumbBack" class="crumb text-xs text-gray-400">/</span>
        <h1 class="text-sm font-semibold m-0">{{ route.meta.title }}</h1>
        <div class="flex items-center gap-2 ml-auto">
          <button class="cmdbtn" @click="ui.openCmdk()">
            <el-icon :size="13"><Search /></el-icon>
            <span class="cmdbtn-text">搜索或跳转…</span>
            <kbd class="kbd">{{ isMac ? '⌘K' : 'Ctrl K' }}</kbd>
          </button>
          <NotificationBell />
          <button class="icon-btn" :title="theme.dark ? '切换到浅色' : '切换到暗黑'" @click="theme.toggle()">
            <el-icon :size="14"><Sunny v-if="theme.dark" /><Moon v-else /></el-icon>
          </button>
          <el-dropdown @command="onCommand">
            <span class="flex items-center cursor-pointer" :title="auth.user?.realname || auth.user?.username">
              <UserAvatar :avatar="auth.user?.avatar" :avatar-url="auth.user?.avatar_url"
                          :name="auth.user?.realname || auth.user?.username" :size="28" />
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="tokens">访问令牌</el-dropdown-item>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main ref="mainEl" class="tl-main overflow-auto">
        <!-- h-full：撑满 el-main，使声明了 h-full 的视图（报告编辑/漏洞编辑/详情）正文与侧栏可各自独立滚动 -->
        <div class="max-w-[1920px] mx-auto w-full h-full">
          <!-- 视图多为多根节点（Fragment），transition 需单元素根，故用带 key 的 div 包裹 -->
          <router-view v-slot="{ Component, route: r }">
            <div :key="r.name as string" class="h-full">
              <component :is="Component" />
            </div>
          </router-view>
        </div>
      </el-main>
    </el-container>
  </el-container>

  <!-- ⌘K 命令面板（顶栏入口 + 全局快捷键） -->
  <CmdPalette />

  <el-dialog v-model="pwdVisible" title="修改密码" width="420px"
             :close-on-click-modal="!forcedChange" :close-on-press-escape="!forcedChange" :show-close="!forcedChange">
    <el-alert v-if="forcedChange" type="warning" :closable="false" show-icon class="mb-3"
              title="首次登录或密码已重置，请先修改密码后再使用系统" />
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
      <el-form-item label="原密码" prop="old_password">
        <el-input v-model="pwdForm.old_password" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码" prop="new_password">
        <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 8 位" />
      </el-form-item>
      <el-form-item label="确认新密码" prop="confirm_password">
        <el-input v-model="pwdForm.confirm_password" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button v-if="!forcedChange" @click="pwdVisible = false">取消</el-button>
      <el-button type="primary" @click="changePassword">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { resolveBackPath } from '../composables/useNavBack'
import {
  Aim, ArrowLeft, Bell, Collection, Connection, DataLine, Document, Expand, Files, Finished, Flag, Fold, Key,
  Memo, Menu, Monitor, OfficeBuilding, Search, Sunny, Tickets, Timer, User, Warning, Moon,
} from '@element-plus/icons-vue'
import client from '../api/client'
import BrandMark from '../components/BrandMark.vue'
import NotificationBell from '../components/NotificationBell.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { useUiStore } from '../stores/ui'
import CmdPalette from '../components/CmdPalette.vue'

const auth = useAuthStore()
const theme = useThemeStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const isMac = /mac/i.test(navigator.platform || navigator.userAgent)
// 侧边栏折叠状态（持久化；兼容旧 snake_case 键）
const collapsed = ref(
  (localStorage.getItem('sidebarCollapsed') ?? localStorage.getItem('sidebar_collapsed')) === '1',
)
const mobileNavOpen = ref(false)
const isMobile = ref(false)
const mobileMenuRef = ref<HTMLButtonElement>()
const navEl = ref<HTMLElement>()
let mobileQuery: MediaQueryList | null = null
watch(collapsed, (v) => localStorage.setItem('sidebarCollapsed', v ? '1' : '0'))
watch(() => route.fullPath, () => {
  if (isMobile.value && mobileNavOpen.value) {
    mobileNavOpen.value = false
    collapsed.value = true
  }
})

// 窄屏（<1024px）自动折叠侧边栏，恢复宽屏时还原用户偏好
onMounted(() => {
  const mq = window.matchMedia('(max-width: 1023px)')
  const apply = () => { if (mq.matches) collapsed.value = true }
  apply()
  mq.addEventListener('change', apply)
})

// 一级路径段高亮；组织管理使用完整路径
const activeMenu = computed(() =>
  route.path === '/assets/groups' ? route.path : '/' + route.path.split('/')[1],
)
function go(path: string) {
  closeMobileNav()
  if (route.path === path) return
  router.push(path)
}

function openMobileNav() {
  collapsed.value = false
  mobileNavOpen.value = true
  void nextTick(() => navEl.value?.querySelector('button')?.focus())
}

function closeMobileNav() {
  const wasOpen = mobileNavOpen.value
  mobileNavOpen.value = false
  if (window.matchMedia('(max-width: 760px)').matches) collapsed.value = true
  if (wasOpen) void nextTick(() => mobileMenuRef.value?.focus())
}

function toggleSidebar() {
  if (window.matchMedia('(max-width: 760px)').matches) closeMobileNav()
  else collapsed.value = !collapsed.value
}

function syncMobileViewport() {
  isMobile.value = !!mobileQuery?.matches
  if (!isMobile.value) mobileNavOpen.value = false
}

function onWindowKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && mobileNavOpen.value) closeMobileNav()
}

// ---------- 面包屑来源链（回退 UX） ----------
// 编辑/详情类页面在顶栏展示可点的来源页：redirect 参数优先（跨页原路返回，如工单抽屉 → 编辑漏洞），
// 回落浏览器站内历史（列表 → 编辑等常规导航）；首级页面或无来源时维持原静态面包屑。
const crumbBack = computed(() => {
  const back = resolveBackPath(route)
  if (!back) return null
  let title: string
  try {
    title = (router.resolve(back.path).meta?.title as string | undefined) ?? back.path
  } catch {
    return null
  }
  if (!title || title === route.meta.title) return null
  return { ...back, title }
})

function onCrumbBack() {
  const back = crumbBack.value
  if (!back) return
  if (back.isHistoryBack) router.back()
  else void router.push(back.path)
}

// ---------- 滚动位置记忆（回退 UX） ----------
// el-main 是常驻滚动容器：按 fullPath 记录滚动位置；返回式导航（浏览器后退 / redirect 回跳，
// 判据为 history.state.position 不高于离开时）恢复，前进式导航置顶。
const mainEl = ref<{ $el: HTMLElement } | null>(null)
const SCROLL_MEM_MAX = 120
const scrollMem = new Map<string, { top: number; position: number }>()
let scrollRaf = 0

function saveScroll() {
  const el = mainEl.value?.$el
  if (!el) return
  const position = (window.history.state as { position?: unknown } | null)?.position
  if (typeof position !== 'number') return
  const fp = route.fullPath
  if (!scrollMem.has(fp) && scrollMem.size >= SCROLL_MEM_MAX) {
    const oldest = scrollMem.keys().next().value
    if (oldest !== undefined) scrollMem.delete(oldest)
  }
  scrollMem.set(fp, { top: el.scrollTop, position })
}

function onMainScroll() {
  cancelAnimationFrame(scrollRaf)
  scrollRaf = requestAnimationFrame(saveScroll)
}

/** 恢复滚动：数据异步加载期间高度不足时以 rAF 重试，直至到位或超时 */
function restoreScroll(el: HTMLElement, fp: string, top: number) {
  const deadline = performance.now() + 1200
  const attempt = () => {
    if (route.fullPath !== fp) return // 用户已再次导航，放弃
    el.scrollTop = top
    if (el.scrollTop >= top - 1) return
    if (el.scrollHeight >= top + el.clientHeight || performance.now() > deadline) return
    requestAnimationFrame(attempt)
  }
  requestAnimationFrame(attempt)
}

watch(
  () => ({ fp: route.fullPath, p: route.path }),
  ({ fp, p }, prev) => {
    if (!prev || fp === prev.fp) return
    // 同页 query 变化（筛选、抽屉状态位）不干预滚动
    if (p === prev.p) return
    const el = mainEl.value?.$el
    if (!el) return
    const memo = scrollMem.get(fp)
    const position = (window.history.state as { position?: unknown } | null)?.position
    if (memo && typeof position === 'number' && memo.position >= position) {
      restoreScroll(el, fp, memo.top)
    } else {
      el.scrollTop = 0
    }
  },
)

onMounted(() => {
  mainEl.value?.$el?.addEventListener('scroll', onMainScroll, { passive: true })
  window.addEventListener('keydown', onWindowKeydown)
  mobileQuery = window.matchMedia('(max-width: 760px)')
  syncMobileViewport()
  mobileQuery.addEventListener('change', syncMobileViewport)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(scrollRaf)
  mainEl.value?.$el?.removeEventListener('scroll', onMainScroll)
  window.removeEventListener('keydown', onWindowKeydown)
  mobileQuery?.removeEventListener('change', syncMobileViewport)
})

const pwdVisible = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const pwdFormRef = ref<FormInstance>()
const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value && value === pwdForm.old_password) callback(new Error('新密码不能与原密码相同'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== pwdForm.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}
// 强制改密（首登或被重置）：弹框不可关闭，必须修改后才能继续
const forcedChange = computed(() => !!auth.user?.must_change_password)

onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  if (auth.user?.must_change_password) {
    ElMessage.warning('首次登录请修改密码')
    pwdVisible.value = true
  }
})

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
  } else if (cmd === 'profile') {
    router.push('/profile')
  } else if (cmd === 'password') {
    pwdVisible.value = true
  } else if (cmd === 'tokens') {
    router.push('/tokens')
  }
}

async function changePassword() {
  const valid = await pwdFormRef.value?.validate().catch(() => false)
  if (!valid) return
  await client.post('/auth/password', {
    old_password: pwdForm.old_password,
    new_password: pwdForm.new_password,
  })
  ElMessage.success('密码修改成功，请重新登录')
  pwdVisible.value = false
  auth.logout(true)
}
</script>

<style scoped>
.tl-aside {
  background: var(--tl-surface);
  border-right: 0.5px solid var(--tl-border);
  transition: width 250ms ease-out, background-color 250ms ease-out;
  overflow: hidden;
}
.icon-btn.mobile-menu-btn {
  display: none;
}
.mobile-nav-scrim {
  display: none;
}
.tl-logo { min-height: 68px; padding: 14px 18px; }
.tl-title { color: var(--tl-text-strong); }

/* 分组标签 */
.nav-group {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--tl-text-3);
  margin: 14px 8px 4px;
  white-space: nowrap;
}

/* 紧凑导航项 */
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 34px;
  padding: 6px 9px;
  margin: 1px 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--tl-text-2);
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 250ms ease-out, color 250ms ease-out;
}
.nav-item:hover { background: var(--tl-surface-2); color: var(--tl-text-1); }
.nav-item.active {
  background: var(--jade-a3);
  color: var(--tl-primary-text);
  font-weight: 600;
}
.tl-nav {
  padding: 4px 10px 16px;
  scrollbar-width: none;
}
.tl-nav::-webkit-scrollbar {
  display: none;
}

.tl-side-foot { padding: 12px; border-top: 0.5px solid var(--tl-border); }
.avatar-box {
  width: 26px;
  height: 26px;
  border-radius: 4px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--tl-text-2);
  background: var(--tl-surface-3);
  border: 0.5px solid var(--tl-border-strong);
}
.topbar-avatar { width: 28px; height: 28px; }

/* 顶栏 */
.tl-topbar {
  height: 52px;
  padding: 0 24px;
  background: var(--tl-surface);
  border-bottom: 0.5px solid var(--tl-border);
}
.crumb { white-space: nowrap; }
/* 来源链按钮：轻量可点，hover 反馈与侧栏导航一致 */
.crumb-back {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--tl-text-2);
  font: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 250ms ease-out, color 250ms ease-out;
}
.crumb-back:hover { background: var(--tl-surface-2); color: var(--tl-primary); }
.tl-topbar h1 {
  min-width: 0;
  overflow: hidden;
  color: var(--tl-text-strong);
  font-size: 16px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmdbtn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 200px;
  padding: 5.5px 10px;
  border-radius: 4px;
  border: 0.5px solid var(--tl-border);
  background: var(--tl-surface);
  color: var(--tl-text-3);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 250ms ease-out, color 250ms ease-out;
}
.cmdbtn:hover { border-color: var(--tl-border-strong); color: var(--tl-text-2); }
.cmdbtn-text { flex: 1; text-align: left; white-space: nowrap; overflow: hidden; }
@media (max-width: 1100px) { .cmdbtn { width: auto; } .cmdbtn-text, .cmdbtn .kbd { display: none; } }

.icon-btn {
  width: 30px;
  height: 30px;
  border-radius: 4px;
  border: 0.5px solid var(--tl-border);
  background: var(--tl-surface);
  color: var(--tl-text-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 250ms ease-out, color 250ms ease-out;
}
.icon-btn:hover { border-color: var(--tl-border-strong); color: var(--tl-text-1); }

/* 主区：20/28/48，≥1536px 提升 24/32/48；内容 1920px 封顶居中（MASTER.md 6.2） */
.tl-main { padding: 18px 24px 40px; }
@media (min-width: 1536px) { .tl-main { padding: 24px 32px 40px; } }
@media (max-width: 1023px) { .tl-main { padding: 16px 16px 40px; } }
@media (max-width: 760px) {
  .tl-aside {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 60;
    width: 216px !important;
    transform: translateX(-100%);
    box-shadow: var(--tl-shadow-pop);
    transition: transform 250ms ease-out;
  }
  .tl-aside.mobile-open {
    transform: translateX(0);
  }
  .mobile-nav-scrim {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 59;
    background: var(--sage-a6);
  }
  .icon-btn.mobile-menu-btn {
    display: inline-flex;
  }
  .tl-side-foot {
    display: none;
  }
  .tl-main {
    padding: 12px 12px 32px;
  }
}
@media (max-width: 700px) {
  .tl-topbar { gap: 4px; padding: 0 12px; }
  .tl-topbar .crumb,
  .tl-topbar .crumb-back { display: none; }
  .tl-topbar h1 { flex: 1; }
  .tl-topbar .ml-auto { gap: 4px; }
  .icon-btn { width: 28px; height: 28px; }
  .cmdbtn { padding: 5px 7px; }
}
</style>
