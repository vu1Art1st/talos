<template>
  <div class="min-h-full flex items-center justify-center relative overflow-hidden"
       style="background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)">
    <div class="absolute inset-0 opacity-20"
         style="background-image: radial-gradient(circle at 25% 25%, #409eff55 0, transparent 40%), radial-gradient(circle at 75% 70%, #67c23a44 0, transparent 40%)" />
    <el-card class="w-[400px] !rounded-xl shadow-2xl z-10">
      <div class="text-center mb-6 mt-2">
        <div class="flex items-center justify-center gap-2 text-2xl font-bold text-gray-800">
          <el-icon :size="28" color="#409EFF"><Lock /></el-icon>
          Talos 漏洞管理平台
        </div>
        <div class="text-gray-400 text-sm mt-2">现代化漏洞全生命周期管理</div>
      </div>
      <el-form :model="form" size="large" @keyup.enter="onLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" show-password :prefix-icon="Key" />
        </el-form-item>
        <el-button type="primary" size="large" class="w-full" :loading="loading" @click="onLogin">
          登 录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Key, User } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function onLogin() {
  if (!form.username || !form.password) return ElMessage.warning('请输入用户名和密码')
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push((route.query.redirect as string) || '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>
