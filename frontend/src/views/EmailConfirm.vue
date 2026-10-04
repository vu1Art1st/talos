<template>
  <div class="auth-page">
    <div class="auth-card text-center">
      <el-result v-if="state === 'pending'" icon="info" title="正在确认邮箱"
                 sub-title="请稍候，不要关闭当前页面" />
      <el-result v-else-if="state === 'success'" icon="success" title="邮箱更换成功"
                 sub-title="下次密码找回将使用新的邮箱地址" />
      <el-result v-else icon="error" title="确认失败" :sub-title="message" />
      <el-button type="primary" @click="goNext">{{ nextText }}</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import client from '../api/client'

const router = useRouter()
const state = ref<'pending' | 'success' | 'error'>('pending')
const message = ref('链接无效或已过期')
const params = new URLSearchParams(window.location.hash.slice(1))
const token = params.get('token') || ''
if (window.location.hash) {
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
}

const loggedIn = computed(() => !!localStorage.getItem('access_token'))
const nextText = computed(() => loggedIn.value ? '返回个人中心' : '返回登录')

function goNext() {
  void router.replace(loggedIn.value ? '/profile' : '/login')
}

onMounted(async () => {
  if (!token) {
    state.value = 'error'
    return
  }
  try {
    await client.post('/auth/email-change/confirm', { token })
    state.value = 'success'
  } catch (error) {
    state.value = 'error'
    const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (detail) message.value = detail
  }
})
</script>

<style scoped>
.auth-page {
  min-height: 100%; display: flex; align-items: center; justify-content: center;
  padding: 24px; background: var(--tl-bg);
}
.auth-card {
  width: 480px; max-width: 100%; padding: 28px; border: 1px solid var(--tl-border);
  border-radius: 12px; background: var(--tl-surface); box-shadow: 0 16px 40px rgba(15, 23, 20, .08);
}
</style>
