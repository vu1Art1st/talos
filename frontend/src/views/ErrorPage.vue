<template>
  <div class="err-root">
    <!-- 背景装饰：细网格 + 品牌色光晕 -->
    <div class="bg" aria-hidden="true">
      <div class="bg-grid"></div>
      <div class="bg-glow"></div>
    </div>

    <!-- 顶栏：本页为顶层路由（不在主布局内），故自带品牌区与明暗切换 -->
    <header class="top">
      <div class="brand">
        <span class="logo-mark"><BrandMark :size="17" /></span>
        <span class="brand-text"><b>Talos</b><i>漏洞管理平台</i></span>
      </div>
      <button
        class="icon-btn"
        type="button"
        :aria-label="theme.dark ? '切换到浅色模式' : '切换到暗黑模式'"
        @click="theme.toggle()"
      >
        <svg v-if="theme.dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2.2M12 19.3v2.2M4.4 4.4l1.6 1.6M18 18l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.4 19.6 6 18M18 6l1.6-1.6" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.9A9.1 9.1 0 1 1 11.1 3a7.1 7.1 0 0 0 9.9 9.9z" />
        </svg>
      </button>
    </header>

    <!-- 主体：巨号状态码（中位为线稿图形替代）+ 文案与操作 -->
    <main class="wrap">
      <div class="stage" :key="meta.code" aria-live="polite">
        <div class="code" role="img" :aria-label="`错误码 ${meta.code}`">
          <span class="d" :data-n="digits[0]">{{ digits[0] }}</span>
          <svg class="ic" aria-hidden="true"><use :href="meta.icon" /></svg>
          <span class="d" :data-n="digits[2]">{{ digits[2] }}</span>
        </div>

        <div class="info">
          <span class="chip"><i></i>{{ meta.chip }}</span>
          <h1>{{ meta.title }}</h1>
          <p class="desc">{{ meta.desc }}</p>
          <div class="actions">
            <button
              v-for="a in meta.actions"
              :key="a.act"
              type="button"
              :class="['btn', a.primary ? 'btn-primary' : 'btn-ghost']"
              @click="onAction(a.act)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <use :href="a.icon" />
              </svg>
              {{ a.label }}
            </button>
          </div>
          <p class="hint">{{ meta.hint }}</p>
        </div>
      </div>
    </main>

    <!-- 图标精灵：viewBox 按各图标自身墨迹（含描边）的居中正方形归一，描边随 --tone 变色 -->
    <svg class="sprite" aria-hidden="true">
      <defs>
        <!-- 400 请求无效：破损的文档 -->
        <symbol id="i-400" viewBox="2 2 60 60" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M34 6H18a4 4 0 0 0-4 4v44a4 4 0 0 0 4 4h28a4 4 0 0 0 4-4V22z" />
          <path d="M34 6v16h16" />
          <path d="M14 34l8-5 7 9 7-7 7 5 7-4" />
        </symbol>
        <!-- 401 身份未验证：挂锁 -->
        <symbol id="i-401" viewBox="6 6.5 52 52" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 28v-7a11 11 0 0 1 22 0v7" />
          <rect x="14" y="27" width="36" height="28" rx="5" />
          <circle cx="32" cy="38" r="3.4" />
          <path d="M32 41.4V47" />
        </symbol>
        <!-- 403 无权限：盾牌 + 斜杠 -->
        <symbol id="i-403" viewBox="3 2 58 58" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M32 6 52 13V28C52 41.4 43.6 51 32 56 20.4 51 12 41.4 12 28V13z" />
          <path d="M22 20.5 42 43.5" />
        </symbol>
        <!-- 404 未找到：虫子 -->
        <symbol id="i-404" viewBox="1 1.6 62 62" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <path d="M26.4 12.6 22.8 7.4M37.6 12.6 41.2 7.4" />
          <ellipse cx="32" cy="17.6" rx="8.6" ry="7" />
          <ellipse cx="32" cy="39" rx="14.6" ry="18" />
          <path d="M32 24.6V57" />
          <path d="M18.6 30.6C11 30 7.4 32.6 4.8 36" />
          <path d="M17.9 39c-7.9.2-11.1 2.9-13.7 6.7" />
          <path d="M18.9 46.8c-6 3-8.5 6.6-9.7 11" />
          <path d="M45.4 30.6C53 30 56.6 32.6 59.2 36" />
          <path d="M46.1 39c7.9.2 11.1 2.9 13.7 6.7" />
          <path d="M45.1 46.8c6 3 8.5 6.6 9.7 11" />
        </symbol>
        <!-- 500 服务器内部错误：齿轮 + 闪电 -->
        <symbol id="i-500" viewBox="5.5 5.5 53 53" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="32" cy="32" r="16" />
          <path stroke-width="6.5" d="M48.5 32h4.5M32 48.5v4.5M15.5 32H11M32 15.5V11M43.7 43.7l3.2 3.2M20.3 43.7l-3.2 3.2M43.7 20.3l3.2-3.2M20.3 20.3l-3.2-3.2" />
          <path d="M34 20 23 34h8l-3 10 13-14h-8z" fill="currentColor" stroke-width="2.5" stroke-linejoin="round" />
        </symbol>
        <!-- 502 / 503 / 504 网关类错误：断开的连接 -->
        <symbol id="i-502" viewBox="2 2 60 60" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <rect x="6" y="19" width="16" height="26" rx="5" />
          <rect x="42" y="19" width="16" height="26" rx="5" />
          <path d="M22 26h6M22 38h6M42 26h-6M42 38h-6" />
        </symbol>
        <!-- 按钮小图标 24×24 -->
        <symbol id="i-home" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 11.2 12 3l9 8.2" /><path d="M5.6 9.6V21h12.8V9.6" />
        </symbol>
        <symbol id="i-back" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 12h15" /><path d="M12 5l-7 7 7 7" />
        </symbol>
        <symbol id="i-login" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 3.5h4A2.5 2.5 0 0 1 21.5 6v12a2.5 2.5 0 0 1-2.5 2.5h-4" />
          <path d="M9.5 16.5 14 12 9.5 7.5" /><path d="M14 12H3.5" />
        </symbol>
        <symbol id="i-refresh" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20.5 12a8.5 8.5 0 1 1-2.5-6" /><path d="M20.5 4.5v5h-5" />
        </symbol>
      </defs>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandMark from '../components/BrandMark.vue'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { getErrorMeta, normalizeCode, normalizeRedirect } from '../utils/errorPage'
import type { ErrorActionKind } from '../utils/errorPage'

const route = useRoute()
const router = useRouter()
const theme = useThemeStore()
const auth = useAuthStore()

/** 状态码来自路由参数：仅接受 4xx / 5xx 三位码，其余归一化为 404（不空白、不抛错） */
const meta = computed(() => getErrorMeta(route.params.code))
const digits = computed(() => [meta.value.code[0], meta.value.code[1], meta.value.code[2]])

function syncTitle() {
  document.title = `${meta.value.code} · ${meta.value.title} - Talos 漏洞管理平台`
}

onMounted(() => {
  // 地址栏里的非法状态码（如 /error/abc）归一到规范 URL，保持可刷新、可分享
  const raw = String(route.params.code ?? '')
  const code = normalizeCode(raw)
  if (raw !== code) router.replace({ name: 'error', params: { code } })
  syncTitle()
})
watch(() => meta.value.code, syncTitle)

/** 401 页「重新登录」前清理本地凭证：否则守约会因残留 token 把 /login 弹回业务页，形成循环 */
function clearCredentials() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  auth.user = null
}

function onAction(act: ErrorActionKind) {
  if (act === 'back') {
    // 直接打开错误页（无来源历史）时退化为回首页，避免停在原地
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
  /* 品牌色调：图标 / chip / 光晕 / 主按钮同一个 --tone。
     浅色态小字压浅底需 ≥4.5:1，故取加深档 #047857（AGENTS.md 认可），#059669 仅 3.3:1 */
  --tone: #047857;
  --on-tone: #ffffff;
  --chip-tint: 7%;
  /* 背景网格线：亮色用低透明度墨色，暗色用低透明度白色，两态都有极弱纹理 */
  --grid-line: color-mix(in srgb, var(--tl-text-1) 4.5%, transparent);
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  overflow-x: hidden;
  background: var(--tl-bg);
  color: var(--tl-text-1);
}
html.dark .err-root {
  --tone: #34d399;
  --on-tone: #05261a;
  --chip-tint: 14%;
  --grid-line: rgba(255, 255, 255, 0.035);
}

.sprite {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
}

/* ===================== 背景装饰：细网格 + 状态色光晕 ===================== */
.bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}
.bg-grid {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 34px 34px;
  -webkit-mask-image: radial-gradient(ellipse 78% 68% at 50% 46%, #000 0%, transparent 78%);
  mask-image: radial-gradient(ellipse 78% 68% at 50% 46%, #000 0%, transparent 78%);
}
.bg-glow {
  position: absolute;
  left: 50%;
  top: 44%;
  transform: translate(-50%, -50%);
  width: min(980px, 130vw);
  aspect-ratio: 1;
  border-radius: 50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--tone) 15%, transparent) 0%, transparent 62%);
}

/* ===================== 顶栏：品牌 + 明暗切换 ===================== */
.top {
  position: relative;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 26px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-mark {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  background: var(--tl-primary);
  color: var(--tl-on-primary);
}
.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}
.brand-text b {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.2px;
}
.brand-text i {
  font-size: 10.5px;
  font-style: normal;
  color: var(--tl-text-3);
}

.icon-btn {
  margin-left: auto;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  cursor: pointer;
  display: grid;
  place-items: center;
  background: var(--tl-surface);
  color: var(--tl-text-2);
  border: 1px solid var(--tl-border);
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.icon-btn:hover {
  border-color: var(--tl-border-strong);
  color: var(--tl-text-1);
}
.icon-btn svg {
  width: 15px;
  height: 15px;
}

/* ===================== 主体：巨号状态码 + 文案双栏 ===================== */
.wrap {
  position: relative;
  z-index: 2;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px 40px 60px;
}
.stage {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: clamp(36px, 6vw, 92px);
  width: 100%;
  max-width: 1000px;
}
.code {
  display: flex;
  align-items: baseline;
  flex-shrink: 0;
  user-select: none;
  font-weight: 800;
  line-height: 0.86;
  letter-spacing: normal;
  font-size: clamp(92px, 13.5vw, 176px);
  color: var(--tl-text-1);
}
/* 每个数字占固定字宽（「1」比「4」窄 25%）：否则换状态码时整组横移 */
.code .d {
  display: block;
  min-width: 0.6em;
  text-align: center;
  flex: none;
}
/* 「1」字面宽只有「4」的 76%，槽内留白全堆在两侧，视觉上离图标更远；
   用 transform 把它朝图标侧微收 —— transform 不改变布局宽度，故不会引起横移 */
.code .d[data-n='1'] {
  transform: translateX(-0.04em);
}
/* 图标与数字同底对齐：baseline 让图标底边贴数字基线；各图标 viewBox 已按自身墨迹居中归一 */
.code .ic {
  width: 0.7em;
  height: 0.7em;
  margin: 0 0.14em;
  flex: none;
  color: var(--tone);
}
/* 文案列固定宽度，不随文案长短伸缩，整组左右位置恒定 */
.info {
  width: 400px;
  max-width: 100%;
  flex: none;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 10px;
  border-radius: 5px;
  font-family: var(--tl-mono);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--tone);
  background: color-mix(in srgb, var(--tone) var(--chip-tint), transparent);
  border: 1px solid color-mix(in srgb, var(--tone) 32%, transparent);
}
.chip i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
  background: var(--tone);
  box-shadow: 0 0 6px color-mix(in srgb, var(--tone) 60%, transparent);
}
html:not(.dark) .chip i {
  box-shadow: none;
}

.info h1 {
  margin: 14px 0 0;
  font-size: clamp(24px, 3vw, 32px);
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.3;
}
/* 释义固定两行高（3.6em = 2 × 1.8）：无论实际 1 行还是 2 行，文案块高度恒定 */
.info .desc {
  margin: 10px 0 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--tl-text-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 3.6em;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 24px;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 34px;
  padding: 0 16px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.btn svg {
  width: 14px;
  height: 14px;
  flex: none;
}
.btn-primary {
  background: var(--tone);
  color: var(--on-tone);
}
.btn-primary:hover {
  filter: brightness(1.08);
}
.btn-ghost {
  background: var(--tl-surface);
  border-color: var(--tl-border);
  color: var(--tl-text-1);
}
.btn-ghost:hover {
  border-color: var(--tl-border-strong);
  background: var(--tl-surface-2);
}

.hint {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--tl-border);
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--tl-text-3);
  min-height: 1.7em;
}

/* ===================== 入场（一次性，尊重 reduce-motion） ===================== */
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.code {
  animation: rise 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.info {
  animation: rise 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) 0.09s both;
}

/* ===================== 响应式 ===================== */
@media (max-width: 900px) {
  .wrap {
    padding: 8px 28px 48px;
  }
  .stage {
    flex-direction: column;
    align-items: flex-start;
    gap: 32px;
    max-width: 520px;
  }
  .code {
    font-size: clamp(84px, 22vw, 132px);
  }
  .info {
    width: 100%;
    max-width: 100%;
  }
}
@media (max-width: 560px) {
  .top {
    padding: 14px 18px;
  }
  .wrap {
    padding: 0 20px 40px;
  }
  .actions {
    gap: 8px;
  }
  .btn {
    flex: 1 1 140px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .code,
  .info {
    animation: none;
  }
}
</style>
