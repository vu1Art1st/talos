<template>
  <div class="login-bg min-h-full flex items-center justify-center relative overflow-hidden">
    <!-- 网格纹理 -->
    <div class="login-grid absolute inset-0" />
    <!-- 品牌光晕 -->
    <div class="absolute inset-0"
         style="background-image: radial-gradient(circle at 20% 20%, rgba(129,140,248,.35) 0, transparent 42%), radial-gradient(circle at 80% 75%, rgba(139,92,246,.30) 0, transparent 42%)" />
    <div class="login-card z-10 w-[400px] p-8">
      <div class="text-center mb-7">
        <div class="inline-flex w-14 h-14 rounded-2xl items-center justify-center mb-3"
             style="background: linear-gradient(135deg,#6366f1,#8b5cf6); box-shadow: 0 10px 24px rgba(99,102,241,.45)">
          <el-icon :size="28" color="#fff"><Lock /></el-icon>
        </div>
        <div class="text-[22px] font-bold text-white">Talos 漏洞管理平台</div>
        <div class="text-sm mt-1.5" style="color: rgba(255,255,255,.55)">现代化漏洞全生命周期管理</div>
      </div>
      <el-form :model="form" size="large" @keyup.enter="onLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" show-password :prefix-icon="Key" />
        </el-form-item>
        <el-button class="login-btn w-full" size="large" :loading="loading" @click="onLogin">
          登 录
        </el-button>
      </el-form>
    </div>
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

<style scoped>
.login-bg {
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 45%, #4f46e5 100%);
}
.login-grid {
  background-image:
    linear-gradient(rgba(255, 255, 255, .06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, .06) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: radial-gradient(circle at center, #000 0, transparent 80%);
}
/* 玻璃拟态卡片 */
.login-card {
  background: rgba(255, 255, 255, .08);
  border: 1px solid rgba(255, 255, 255, .18);
  border-radius: 18px;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 24px 60px rgba(0, 0, 0, .35);
}
/* 输入框在玻璃卡上的适配 + 聚焦动效 */
.login-card :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, .1);
  box-shadow: none;
  border: 1px solid rgba(255, 255, 255, .2);
  border-radius: 10px;
  transition: border-color .2s, box-shadow .2s, background .2s;
}
.login-card :deep(.el-input__wrapper:hover) {
  border-color: rgba(255, 255, 255, .38);
}
.login-card :deep(.el-input__wrapper.is-focus) {
  border-color: #818cf8;
  background: rgba(255, 255, 255, .16);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, .35);
}
.login-card :deep(.el-input__inner) {
  color: #fff;
}
.login-card :deep(.el-input__inner::placeholder) {
  color: rgba(255, 255, 255, .5);
}
.login-card :deep(.el-input__prefix),
.login-card :deep(.el-input__suffix) {
  color: rgba(255, 255, 255, .6);
}
/* 渐变登录按钮 */
.login-btn {
  border: none;
  color: #fff;
  font-weight: 600;
  letter-spacing: 2px;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  transition: transform .15s, box-shadow .2s, filter .2s;
}
.login-btn:hover {
  filter: brightness(1.05);
  box-shadow: 0 10px 24px rgba(99, 102, 241, .5);
  transform: translateY(-1px);
}
.login-btn:active {
  transform: translateY(0);
}
</style>
