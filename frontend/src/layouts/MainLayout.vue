<template>
  <el-container class="h-full">
    <el-aside :width="collapsed ? '64px' : '224px'" class="tl-aside flex flex-col">
      <!-- Logo：双层六边形品牌标志 + 双行文字组 -->
      <div class="flex items-center flex-none tl-logo" :class="collapsed ? 'justify-center' : 'gap-2 px-4'">
        <BrandMark :size="30" class="flex-none" style="color: var(--tl-text-1)" />
        <div v-if="!collapsed" class="leading-tight whitespace-nowrap">
          <div class="font-extrabold text-[17px] tracking-tight tl-title">Talos</div>
          <div class="text-2xs font-semibold" style="color: var(--tl-brand-mint)">漏洞管理平台</div>
        </div>
      </div>

      <!-- 平铺分组导航 -->
      <nav class="flex-1 overflow-y-auto tl-nav">
        <button class="nav-item" :class="{ active: activeMenu === '/dashboard' }"
                :title="collapsed ? '安全态势' : undefined" @click="go('/dashboard')">
          <el-icon :size="15"><DataLine /></el-icon><span v-if="!collapsed">安全态势</span>
        </button>
        <template v-if="!collapsed"><div class="nav-group">漏洞运营</div></template>
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
        </template>
      </nav>

      <!-- 底部：折叠切换 -->
      <div class="tl-side-foot flex-none">
        <button class="nav-item" @click="collapsed = !collapsed">
          <el-icon :size="15"><Fold /></el-icon><span v-if="!collapsed">收起侧栏</span>
        </button>
        <button v-if="collapsed" class="nav-item justify-center" title="展开侧栏" @click="collapsed = !collapsed">
          <el-icon :size="15"><Expand /></el-icon>
        </button>
      </div>
    </el-aside>

    <!-- 显式 direction="vertical"：el-container 靠子组件名检测方向，原生 header 元素会被误判为横向 -->
    <el-container direction="vertical" class="min-w-0">
      <!-- 顶栏：50px 毛玻璃工具栏 -->
      <el-header class="tl-topbar flex items-center gap-3 flex-none" height="50px">
        <span class="crumb text-xs text-gray-400">Talos /</span>
        <h1 class="text-sm font-semibold m-0">{{ route.meta.title }}</h1>
        <div class="flex items-center gap-2 ml-auto">
          <button class="cmdbtn" @click="ui.openCmdk()">
            <el-icon :size="13"><Search /></el-icon>
            <span class="cmdbtn-text">搜索或跳转…</span>
            <kbd class="kbd">{{ isMac ? '⌘K' : 'Ctrl K' }}</kbd>
          </button>
          <button class="icon-btn" :title="theme.dark ? '切换到浅色' : '切换到暗黑'" @click="theme.toggle()">
            <el-icon :size="14"><Sunny v-if="theme.dark" /><Moon v-else /></el-icon>
          </button>
          <el-dropdown @command="onCommand">
            <span class="flex items-center cursor-pointer" :title="auth.user?.realname || auth.user?.username">
              <div class="avatar-box topbar-avatar">{{ avatarText }}</div>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="tokens">访问令牌</el-dropdown-item>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="tl-main overflow-auto">
        <div class="max-w-[1400px] mx-auto w-full">
          <!-- 视图多为多根节点（Fragment），transition 需单元素根，故用带 key 的 div 包裹 -->
          <router-view v-slot="{ Component, route: r }">
            <transition name="fade-slide" mode="out-in">
              <div :key="r.name as string" class="h-full">
                <component :is="Component" />
              </div>
            </transition>
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
    </el-form>
    <template #footer>
      <el-button v-if="!forcedChange" @click="pwdVisible = false">取消</el-button>
      <el-button type="primary" @click="changePassword">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import {
  Aim, Bell, Collection, Connection, DataLine, Document, Expand, Flag, Fold, Key,
  Memo, Monitor, OfficeBuilding, Search, Sunny, Tickets, User, Warning, Moon,
} from '@element-plus/icons-vue'
import client from '../api/client'
import BrandMark from '../components/BrandMark.vue'
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
const avatarText = computed(() => (auth.user?.realname || auth.user?.username || '?').slice(0, 1))

// 侧边栏折叠状态（持久化；兼容旧 snake_case 键）
const collapsed = ref(
  (localStorage.getItem('sidebarCollapsed') ?? localStorage.getItem('sidebar_collapsed')) === '1',
)
watch(collapsed, (v) => localStorage.setItem('sidebarCollapsed', v ? '1' : '0'))

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
  if (route.path === path) return
  router.push(path)
}

const pwdVisible = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '' })
const pwdFormRef = ref<FormInstance>()
const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' },
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
    router.push('/login')
  } else if (cmd === 'password') {
    pwdVisible.value = true
  } else if (cmd === 'tokens') {
    router.push('/tokens')
  }
}

async function changePassword() {
  const valid = await pwdFormRef.value.validate().catch(() => false)
  if (!valid) return
  await client.post('/auth/password', pwdForm)
  ElMessage.success('密码修改成功，请重新登录')
  pwdVisible.value = false
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.tl-aside {
  background: var(--tl-surface);
  border-right: 1px solid var(--tl-border);
  transition: width .2s ease, background-color .25s ease;
  overflow: hidden;
}
.tl-logo { height: 52px; padding-top: 14px; padding-bottom: 10px; }
.tl-title { color: var(--tl-text-1); }

/* 分组标签：10.5px / 加宽字距 */
.nav-group {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: .1em;
  color: var(--tl-text-3);
  margin: 14px 8px 4px;
  white-space: nowrap;
}

/* 紧凑导航项：约 30px 高、6px 圆角、半透明主色激活底 */
.nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 5.5px 8px;
  margin: 1px 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--tl-text-2);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  white-space: nowrap;
  transition: background .12s ease, color .12s ease;
}
.nav-item:hover { background: var(--tl-surface-2); color: var(--tl-text-1); }
.nav-item.active {
  background: color-mix(in srgb, var(--tl-primary) 10%, transparent);
  color: var(--tl-primary);
  font-weight: 600;
}
.tl-nav { padding: 4px 10px 10px; }

.tl-side-foot { padding: 12px; border-top: 1px solid var(--tl-border); }
.avatar-box {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--tl-text-2);
  background: var(--tl-surface-3);
  border: 1px solid var(--tl-border-strong);
}
.topbar-avatar { width: 28px; height: 28px; }

/* 顶栏：50px，主色调 82% 透明底 + 毛玻璃 */
.tl-topbar {
  height: 50px;
  padding: 0 28px;
  background: color-mix(in srgb, var(--tl-bg) 82%, transparent);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--tl-border);
}
.crumb { white-space: nowrap; }
.tl-topbar h1 { color: var(--tl-text-1); white-space: nowrap; }

.cmdbtn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 200px;
  padding: 5.5px 10px;
  border-radius: 7px;
  border: 1px solid var(--tl-border);
  background: var(--tl-surface);
  color: var(--tl-text-3);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color .12s ease;
}
.cmdbtn:hover { border-color: var(--tl-border-strong); color: var(--tl-text-2); }
.cmdbtn-text { flex: 1; text-align: left; white-space: nowrap; overflow: hidden; }
@media (max-width: 1100px) { .cmdbtn { width: auto; } .cmdbtn-text { display: none; } }

.icon-btn {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  border: 1px solid var(--tl-border);
  background: var(--tl-surface);
  color: var(--tl-text-2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .12s ease;
}
.icon-btn:hover { border-color: var(--tl-border-strong); color: var(--tl-text-1); }

/* 主区：20/28/48 + 最大 1400px 居中 */
.tl-main { padding: 20px 28px 48px; }
@media (max-width: 1023px) { .tl-main { padding: 16px 16px 40px; } }
</style>
