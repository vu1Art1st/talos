<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-title">找回密码</div>
      <div class="auth-subtitle">重置链接将发送到账号绑定的邮箱</div>
      <el-alert v-if="checked && !enabled" type="warning" :closable="false" show-icon class="mb-4"
                title="自助找回未启用，请联系管理员重置密码" />
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top"
               @keyup.enter="submit">
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" autocomplete="email" placeholder="请输入账号邮箱" />
        </el-form-item>
        <el-button type="primary" class="w-full" :loading="loading" :disabled="checked && !enabled"
                   @click="submit">
          发送重置邮件
        </el-button>
      </el-form>
      <div class="auth-links">
        <el-button link @click="router.push('/login')">返回登录</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import client from '../api/client'

const router = useRouter()
const formRef = ref<FormInstance>()
const form = reactive({ email: '' })
const loading = ref(false)
const checked = ref(false)
const enabled = ref(false)
const rules: FormRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid || !enabled.value) return
  loading.value = true
  try {
    const { data } = await client.post('/auth/password-reset/request', { email: form.email })
    ElMessage.success(data.msg)
    form.email = ''
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    enabled.value = (await client.get('/auth/password-reset/status')).data.enabled
  } finally {
    checked.value = true
  }
})
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
.auth-links { display: flex; justify-content: center; margin-top: 16px; }
</style>
