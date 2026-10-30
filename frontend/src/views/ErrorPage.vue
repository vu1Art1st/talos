<template>
  <div class="err-root">
    <header class="top">
      <div class="brand">
        <BrandMark :size="24" />
        <div>
          <b>Talos</b>
          <span>漏洞管理平台</span>
        </div>
      </div>
      <button
        class="icon-btn"
        type="button"
        :aria-label="theme.dark ? '切换到浅色模式' : '切换到暗黑模式'"
        @click="theme.toggle()"
      >
        <el-icon :size="16"><Sunny v-if="theme.dark" /><Moon v-else /></el-icon>
      </button>
    </header>

    <main class="wrap">
      <section class="panel" aria-live="polite">
        <div class="status">
          <el-icon :size="18"><WarningFilled /></el-icon>
          <span>{{ meta.code }}</span>
        </div>
        <h1>{{ meta.title }}</h1>
        <p>{{ meta.desc }}</p>
        <el-button type="primary" data-test="error-primary" @click="onAction(primaryAction.act)">
          <el-icon class="mr-1"><component :is="primaryActionIcon" /></el-icon>
          {{ primaryAction.label }}
        </el-button>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back, Key, Moon, Refresh, Sunny, WarningFilled } from '@element-plus/icons-vue'
import BrandMark from '../components/BrandMark.vue'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { getErrorMeta, normalizeCode, normalizeRedirect } from '../utils/errorPage'
import type { ErrorActionKind } from '../utils/errorPage'

const route = useRoute()
const router = useRouter()
const theme = useThemeStore()
const auth = useAuthStore()

const meta = computed(() => getErrorMeta(route.params.code))
const primaryAction = computed(() =>
  meta.value.actions.find((action) => action.primary) ?? meta.value.actions[0],
)
const primaryActionIcon = computed(() => {
  if (primaryAction.value.act === 'login') return Key
  if (primaryAction.value.act === 'reload') return Refresh
  return Back
})

function syncTitle() {
  document.title = `${meta.value.code} ${meta.value.title} - Talos 漏洞管理平台`
}

onMounted(() => {
  const raw = String(route.params.code ?? '')
  const code = normalizeCode(raw)
  if (raw !== code) router.replace({ name: 'error', params: { code } })
  syncTitle()
})
watch(() => meta.value.code, syncTitle)

function clearCredentials() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  auth.user = null
}

function onAction(act: ErrorActionKind) {
  if (act === 'back') {
    const state = window.history.state as { back?: string | null } | null
    if (state?.back) router.back()
    else router.replace('/dashboard')
  } else if (act === 'home') {
    router.replace('/dashboard')
  } else if (act === 'login') {
    clearCredentials()
    const redirect = normalizeRedirect(route.query.redirect)
    router.replace({ path: '/login', query: redirect ? { redirect } : {} })
  } else {
    window.location.reload()
  }
}
</script>

<style scoped>
.err-root {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  overflow-x: clip;
  background: var(--tl-bg);
  color: var(--tl-text-1);
}

.top {
  display: flex;
  align-items: center;
  padding: 18px 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--tl-primary-text);
}

.brand > div {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.brand b {
  color: var(--tl-text-strong);
  font-size: 14px;
  font-weight: 600;
}

.brand span {
  color: var(--tl-text-3);
  font-size: 12px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  margin-left: auto;
  display: grid;
  place-items: center;
  border: 0.5px solid var(--tl-border);
  border-radius: 4px;
  background: var(--tl-surface);
  color: var(--tl-text-2);
  cursor: pointer;
  transition: border-color 250ms ease-out, color 250ms ease-out;
}

.icon-btn:hover {
  border-color: var(--tl-border-strong);
  color: var(--tl-text-1);
}

.wrap {
  flex: 1;
  display: grid;
  place-items: center;
  padding: 24px;
}

.panel {
  width: 100%;
  max-width: 560px;
  padding: 32px;
  border: 0.5px solid var(--tl-border);
  border-radius: 8px;
  background: var(--tl-surface);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--tl-primary-text);
  font-family: var(--tl-mono);
  font-size: 12px;
  font-weight: 600;
}

h1 {
  margin: 12px 0 0;
  color: var(--tl-text-strong);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.5;
}

p {
  margin: 8px 0 20px;
  color: var(--tl-text-2);
  font-size: 14px;
  line-height: 1.7;
}

@media (max-width: 560px) {
  .top {
    padding: 14px 16px;
  }

  .wrap {
    padding: 16px;
  }

  .panel {
    padding: 24px;
  }
}
</style>
