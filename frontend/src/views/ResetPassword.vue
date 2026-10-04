<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-title">设置新密码</div>
      <div class="auth-subtitle">新密码至少 8 位，且不能与原密码相同</div>
      <el-alert v-if="!token" type="error" :closable="false" show-icon class="mb-4"
                title="链接无效或已过期，请重新申请" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="submit">
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="form.new_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm_password">
          <el-input v-model="form.confirm_password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-button type="primary" class="w-full" :loading="loading" :disabled="!token" @click="submit">
          确认重置
        </el-button>
      </el-form>
      <div class="auth-links">
        <el-button link @click="router.push('/login')">返回登录</el-button>
        <el-button link @click="router.push('/forgot-password')">重新申请</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import client from '../api/client'

const router = useRouter()
const token = ref('')
const params = new URLSearchParams(window.location.hash.slice(1))
token.value = params.get('token') || ''
if (window.location.hash) {
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
}

const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ new_password: '', confirm_password: '' })
const rules: FormRules = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== form.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || !token.value) return
  loading.value = true
  try {
    await client.post('/auth/password-reset/confirm', {
      token: token.value,
      new_password: form.new_password,
    })
    ElMessage.success('密码已重置，请使用新密码登录')
    await router.replace('/login')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100%; display: flex; align-items: center; justify-content: center;
  padding: 24px; background: var(--tl-bg);
}
.auth-card {
  width: 420px; max-width: 100%; padding: 30px; border: 1px solid var(--tl-border);
  border-radius: 12px; background: var(--tl-surface); box-shadow: 0 16px 40px rgba(15, 23, 20, .08);
}
.auth-title { font-size: 22px; font-weight: 700; color: var(--tl-text-1); }
.auth-subtitle { margin: 8px 0 22px; font-size: 13px; color: var(--tl-text-3); }
.auth-links { display: flex; justify-content: center; gap: 8px; margin-top: 16px; }
</style>
