<template>
  <el-container class="h-full">
    <el-aside width="220px" class="bg-[#001529]">
      <div class="flex items-center gap-2 px-5 h-14 text-white font-bold text-lg">
        <el-icon :size="22" color="#409EFF"><Lock /></el-icon>
        Talos 漏洞管理平台
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#001529"
        text-color="rgba(255,255,255,.68)"
        active-text-color="#fff"
        class="!border-r-0"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon><span>安全态势</span>
        </el-menu-item>
        <el-menu-item index="/vulns">
          <el-icon><Warning /></el-icon><span>漏洞管理</span>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('import:manage')" index="/imports">
          <el-icon><Upload /></el-icon><span>Word 导入</span>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('report:manage')" index="/reports">
          <el-icon><Document /></el-icon><span>报告中心</span>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('app:manage')" index="/apps">
          <el-icon><Grid /></el-icon><span>应用管理</span>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('asset:manage')" index="/assets">
          <el-icon><Monitor /></el-icon><span>资产管理</span>
        </el-menu-item>
        <el-menu-item v-if="auth.hasPerm('user:manage')" index="/users">
          <el-icon><User /></el-icon><span>用户与权限</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="flex items-center justify-between bg-white shadow-sm !h-14">
        <div class="text-base font-medium text-gray-700">{{ route.meta.title }}</div>
        <el-dropdown @command="onCommand">
          <span class="flex items-center gap-2 cursor-pointer text-gray-700">
            <el-avatar :size="30" class="!bg-blue-500">
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
      </el-header>

      <el-main class="!p-4 overflow-auto">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <el-dialog v-model="pwdVisible" title="修改密码" width="420px">
    <el-form :model="pwdForm" label-width="80px">
      <el-form-item label="原密码">
        <el-input v-model="pwdForm.old_password" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="pwdForm.new_password" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdVisible = false">取消</el-button>
      <el-button type="primary" @click="changePassword">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => '/' + route.path.split('/')[1])
const pwdVisible = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '' })

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
  if (!pwdForm.new_password) return ElMessage.warning('请输入新密码')
  await client.post('/auth/password', pwdForm)
  ElMessage.success('密码修改成功，请重新登录')
  pwdVisible.value = false
  auth.logout()
  router.push('/login')
}
</script>
