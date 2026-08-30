<template>
  <div class="login-bg min-h-full flex items-center justify-center">
    <div class="login-card w-[400px] p-8">
      <!-- 品牌区：标志在左 + 双行文字组在右（与侧边栏一致） -->
      <div class="flex items-center justify-center gap-3 mb-8">
        <BrandMark :size="54" class="flex-none" style="color: var(--tl-text-1)" />
        <div class="leading-tight text-left">
          <div class="text-[30px] font-extrabold tracking-tight leading-none" style="color: var(--tl-text-1)">Talos</div>
          <div class="text-[13.5px] font-semibold mt-1" style="color: var(--tl-brand-mint)">漏洞管理平台</div>
        </div>
      </div>
      <el-form ref="formRef" :model="form" :rules="formRules" size="large" @keyup.enter="onLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
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
import type { FormInstance, FormRules } from 'element-plus'
import { Key, User } from '@element-plus/icons-vue'
import BrandMark from '../components/BrandMark.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
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
/* 纯色底（跟随系统明暗令牌，默认浅色）：柔和、克制，无渐变与光晕装饰 */
.login-bg { background: var(--tl-bg); }

.login-card {
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(15, 23, 20, .04), 0 16px 40px rgba(15, 23, 20, .06);
}

/* 登录按钮：主色深档底（亮 #036046 / 暗 #5DDBAB），文字对比度 ≥4.5:1 */
.login-btn {
  border: none;
  color: var(--tl-on-primary);
  font-weight: 700;
  letter-spacing: 2px;
  border-radius: 10px;
  background: var(--el-color-primary-dark-2);
  transition: background .15s ease, box-shadow .15s ease;
}
.login-btn:hover {
  background: var(--el-color-primary);
  box-shadow: 0 6px 16px color-mix(in srgb, var(--tl-primary) 25%, transparent);
}
.login-btn:active { background: var(--el-color-primary-dark-2); }
</style>
