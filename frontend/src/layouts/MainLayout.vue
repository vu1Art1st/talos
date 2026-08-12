<template>
  <el-container class="h-full">
    <el-aside :width="collapsed ? '64px' : '220px'" class="tl-aside flex flex-col">
      <div class="flex items-center h-14 flex-none border-b" :class="collapsed ? 'justify-center' : 'gap-2.5 px-4'"
           style="border-color: var(--tl-border)">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-none tl-brand-gradient">
          <el-icon :size="18" color="#fff"><Lock /></el-icon>
        </div>
        <span v-if="!collapsed" class="font-bold text-[15px] whitespace-nowrap tl-title">Talos 漏洞管理平台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        router
        class="!border-r-0 flex-1 pt-1"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon><template #title>安全态势</template>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('special:manage')" index="/testing-plans">
          <el-icon><Tickets /></el-icon><template #title>渗透测试工单</template>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('special:manage')" index="/nonpen-plans">
          <el-icon><Aim /></el-icon><template #title>漏扫基线工单</template>
        </el-menu-item>
        <el-menu-item index="/vulns">
          <el-icon><Warning /></el-icon><template #title>历史漏洞库</template>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Collection /></el-icon><template #title>漏洞模板库</template>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('report:manage')" index="/reports">
          <el-icon><Document /></el-icon><template #title>报告中心</template>
        </el-menu-item>
        <el-sub-menu v-if="auth.hasPerm('asset:manage')" index="/asset-manage">
          <template #title>
            <el-icon><Monitor /></el-icon><span>资产管理</span>
          </template>
          <el-menu-item index="/assets">资产台账</el-menu-item>
          <el-menu-item index="/assets/groups">组织管理</el-menu-item>
        </el-sub-menu>
        <el-sub-menu v-if="auth.hasPerm('special:manage')" index="/special">
          <template #title>
            <el-icon><Folder /></el-icon><span>专项管理</span>
          </template>
          <el-menu-item index="/remote-testings">远程检测</el-menu-item>
          <el-menu-item index="/spring-actions">春耕行动</el-menu-item>
        </el-sub-menu>
        <el-menu-item v-if="auth.hasPerm('user:manage')" index="/users">
          <el-icon><User /></el-icon><template #title>用户与权限</template>
        </el-menu-item>
      </el-menu>
      <div class="p-3 border-t flex-none" style="border-color: var(--tl-border)">
        <el-button text class="w-full" @click="collapsed = !collapsed">
          <el-icon><Expand v-if="collapsed" /><Fold v-else /></el-icon>
        </el-button>
      </div>
    </el-aside>

    <el-container>
      <el-header class="flex items-center justify-between !h-14 border-b"
                 style="background: var(--tl-surface); border-color: var(--tl-border)">
        <div class="text-base font-medium" style="color: var(--tl-text-1)">{{ route.meta.title }}</div>
        <div class="flex items-center gap-3">
          <el-tooltip :content="theme.dark ? '切换到浅色' : '切换到暗黑'" placement="bottom">
            <el-button circle text @click="theme.toggle()">
              <el-icon :size="17"><Sunny v-if="theme.dark" /><Moon v-else /></el-icon>
            </el-button>
          </el-tooltip>
          <el-dropdown @command="onCommand">
            <span class="flex items-center gap-2 cursor-pointer" style="color: var(--tl-text-1)">
              <el-avatar :size="30" class="tl-brand-gradient">
                {{ (auth.user?.realname || auth.user?.username || '?').slice(0, 1) }}
              </el-avatar>
              {{ auth.user?.realname || auth.user?.username }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="!p-4 overflow-auto">
        <!-- 视图多为多根节点（Fragment），transition 需单元素根，故用带 key 的 div 包裹 -->
        <router-view v-slot="{ Component, route: r }">
          <transition name="fade-slide" mode="out-in">
            <div :key="r.name as string" class="h-full">
              <component :is="Component" />
            </div>
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>

  <el-dialog v-model="pwdVisible" title="修改密码" width="420px"
             :close-on-click-modal="!forcedChange" :close-on-press-escape="!forcedChange" :show-close="!forcedChange">
    <el-alert v-if="forcedChange" type="warning" :closable="false" show-icon class="mb-3"
              title="首次登录或密码已重置，请先修改密码后再使用系统" />
    <el-form :model="pwdForm" label-width="90px">
      <el-form-item label="原密码">
        <el-input v-model="pwdForm.old_password" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
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
import client from '../api/client'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

const auth = useAuthStore()
const theme = useThemeStore()
const route = useRoute()
const router = useRouter()

// 侧边栏折叠状态（持久化）
const collapsed = ref(localStorage.getItem('sidebar_collapsed') === '1')
watch(collapsed, (v) => localStorage.setItem('sidebar_collapsed', v ? '1' : '0'))

// 窄屏（<1024px）自动折叠侧边栏，恢复宽屏时还原用户偏好
onMounted(() => {
  const mq = window.matchMedia('(max-width: 1023px)')
  const apply = () => { if (mq.matches) collapsed.value = true }
  apply()
  mq.addEventListener('change', apply)
})

// 二级菜单使用完整路径高亮，其余按一级路径段匹配
const activeMenu = computed(() =>
  route.path === '/assets/groups' ? route.path : '/' + route.path.split('/')[1],
)
const pwdVisible = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '' })
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
  }
}

async function changePassword() {
  if (pwdForm.new_password.length < 8) return ElMessage.warning('新密码至少 8 位')
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
  transition: width .25s ease, background-color .25s ease;
  overflow: hidden;
}
.tl-title { color: var(--tl-text-1); }

/* 菜单项：圆角胶囊 + 主色浅底选中态 */
.tl-aside :deep(.el-menu) { background: transparent; }
.tl-aside :deep(.el-menu-item),
.tl-aside :deep(.el-sub-menu__title) {
  height: 42px;
  line-height: 42px;
  margin: 3px 10px;
  border-radius: 8px;
  color: var(--tl-text-2);
}
.tl-aside :deep(.el-menu--collapse .el-menu-item),
.tl-aside :deep(.el-menu--collapse .el-sub-menu__title) { margin: 3px 6px; }
.tl-aside :deep(.el-menu-item:hover),
.tl-aside :deep(.el-sub-menu__title:hover) {
  background: var(--tl-surface-2);
  color: var(--tl-text-1);
}
.tl-aside :deep(.el-menu-item.is-active) {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>
