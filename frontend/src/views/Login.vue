<template>
  <div class="login-bg min-h-full flex items-center justify-center">
    <div class="login-dots" aria-hidden="true"></div>
    <div class="login-orb orb-a" aria-hidden="true"></div>
    <div class="login-orb orb-b" aria-hidden="true"></div>
    <div class="login-orb orb-c" aria-hidden="true"></div>

    <button class="login-theme-toggle" type="button"
            :aria-label="theme.dark ? '切换到浅色模式' : '切换到暗色模式'"
            :title="theme.dark ? '切换到浅色模式' : '切换到暗色模式'"
            @click="theme.toggle()">
      <el-icon :size="16"><Sunny v-if="theme.dark" /><Moon v-else /></el-icon>
    </button>

    <div class="login-card w-[416px] max-w-[calc(100vw-32px)] px-8 pt-[30px] pb-6">
      <span class="corner corner-top" aria-hidden="true"></span>
      <span class="corner corner-bottom" aria-hidden="true"></span>
      <div class="flex items-center justify-center gap-3.5 mb-7">
        <BrandMark :size="46" class="flex-none logo-mark" />
        <div class="flex flex-col items-start">
          <div class="brand-name">Talos</div>
          <span class="subtitle"><i aria-hidden="true"></i>漏洞管理平台</span>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top" @keyup.enter="onLogin">
        <el-form-item prop="username" class="field">
          <template #label>用户名</template>
          <el-input v-model="form.username" data-test="login-username" placeholder="请输入用户名" autocomplete="username" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password" class="field">
          <template #label>密码</template>
          <el-input v-model="form.password" data-test="login-password" type="password" placeholder="请输入密码" autocomplete="current-password" show-password :prefix-icon="Key" />
        </el-form-item>

        <div class="aux-row">
          <el-checkbox v-model="remember">记住我</el-checkbox>
          <el-button link type="primary" size="small" @click="router.push('/forgot-password')">
            忘记密码？
          </el-button>
        </div>

        <el-button class="login-btn w-full" data-test="login-submit" size="large" :loading="loading" @click="onLogin">
          登录
          <el-icon class="ml-1"><Right /></el-icon>
        </el-button>
      </el-form>

      <div class="capability-divider">平台能力</div>
      <div class="capability-list">
        <span class="capability-chip"><i></i>漏洞全生命周期</span>
        <span class="capability-chip"><i></i>资产管理</span>
        <span class="capability-chip"><i></i>报告与态势</span>
      </div>
      <div class="character-note">
        <img class="character-avatar" src="/avatars/duty-roxy.webp" alt="值守角色洛克茜" />
        <div class="character-copy">
          <strong>安全值守已就绪</strong>
          <span>洛克茜等待接入本次工作任务</span>
        </div>
      </div>
      <div class="login-card-footer">Talos 漏洞全生命周期管理平台</div>
    </div>

    <div class="login-slogan"><b>Talos</b><span>漏洞全生命周期管理平台</span></div>
    <div class="ver-chip">Talos v{{ version }}</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { Key, Moon, Right, Sunny, User } from '@element-plus/icons-vue'
import BrandMark from '../components/BrandMark.vue'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

const REMEMBER_KEY = 'tl_login_username'

const auth = useAuthStore()
const theme = useThemeStore()
const router = useRouter()
const route = useRoute()
const version = __APP_VERSION__
const loading = ref(false)
const remember = ref(true)
const form = reactive({ username: '', password: '' })
const formRef = ref<FormInstance>()
const formRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

onMounted(() => {
  const saved = localStorage.getItem(REMEMBER_KEY)
  if (saved) {
    form.username = saved
    remember.value = true
  }
})

async function onLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    if (remember.value) localStorage.setItem(REMEMBER_KEY, form.username)
    else localStorage.removeItem(REMEMBER_KEY)
    router.push((route.query.redirect as string) || '/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-bg {
  --lp-field-bg: var(--tl-surface-2);
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(720px 420px at 12% 8%, var(--jade-a3), transparent 62%),
    radial-gradient(620px 400px at 88% 12%, var(--sky-a3), transparent 62%),
    radial-gradient(760px 480px at 78% 92%, var(--jade-a2), transparent 64%),
    var(--tl-bg);
}

.login-dots {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image: radial-gradient(var(--sage-a6) 0.5px, transparent 0.5px);
  background-size: 22px 22px;
  mask-image: radial-gradient(ellipse at center, var(--sage-a8), transparent 76%);
}

.login-orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(70px);
  opacity: .48;
  pointer-events: none;
}

.orb-a {
  width: 340px;
  height: 340px;
  left: -90px;
  bottom: -110px;
  background: var(--jade-a4);
}

.orb-b {
  width: 300px;
  height: 300px;
  right: -70px;
  top: -80px;
  background: var(--sky-a4);
}

.orb-c {
  width: 220px;
  height: 220px;
  right: 16%;
  bottom: -80px;
  background: var(--jade-a3);
}

.login-theme-toggle {
  position: fixed;
  top: 22px;
  right: 24px;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0.5px solid var(--tl-border);
  border-radius: 4px;
  background: var(--tl-surface);
  color: var(--tl-text-2);
  transition: background-color 250ms ease-out, border-color 250ms ease-out, color 250ms ease-out;
}

.login-theme-toggle:hover {
  border-color: var(--tl-border-strong);
  background: var(--tl-surface-2);
  color: var(--tl-text-strong);
}

.login-card {
  position: relative; z-index: 1;
  background: var(--tl-surface);
  border: 0.5px solid var(--tl-border);
  border-radius: 8px;
  box-shadow: 0 20px 56px var(--sage-a7);
}

.corner {
  position: absolute;
  width: 46px;
  height: 46px;
  pointer-events: none;
}

.corner-top {
  top: 14px;
  left: 14px;
  border-top: 0.5px solid var(--jade-a8);
  border-left: 0.5px solid var(--jade-a8);
  border-radius: 4px 0 0 0;
}

.corner-bottom {
  right: 14px;
  bottom: 14px;
  border-right: 0.5px solid var(--jade-a8);
  border-bottom: 0.5px solid var(--jade-a8);
  border-radius: 0 0 4px 0;
}

.logo-mark { color: var(--tl-brand-accent); }
.brand-name {
  color: var(--tl-text-strong);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.25;
}
.subtitle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--tl-primary-text);
  background: var(--jade-a3);
  border: 0.5px solid var(--jade-a5);
  border-radius: 4px;
  padding: 2px 7px;
}
.subtitle i {
  width: 5px;
  height: 5px;
  flex: none;
  border-radius: 50%;
  background: var(--jade-9);
}

.field { margin-bottom: 16px; }
.field :deep(.el-form-item__label) {
  font-size: 14px; font-weight: 500; color: var(--tl-text-2);
  margin-bottom: 6px; line-height: 1.4; padding: 0;
}
.field :deep(.el-form-item__label::before) {
  display: none;
}
.field :deep(.el-input__wrapper) {
  height: 44px; border-radius: 4px;
  background: var(--lp-field-bg);
  border: 0.5px solid var(--tl-border);
  box-shadow: none;
  transition: border-color 250ms ease-out, background-color 250ms ease-out;
}
.field :deep(.el-input__wrapper.is-focus) {
  background: var(--tl-surface);
  border-color: var(--tl-primary);
  box-shadow: 0 0 0 0.5px var(--tl-focus);
}

.aux-row { display: flex; justify-content: space-between; align-items: center; margin: 2px 0 18px; font-size: 14px; color: var(--tl-text-2); }
.aux-row :deep(.el-checkbox__label) { font-size: 14px; color: var(--tl-text-2); }

.login-btn {
  height: 44px;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--tl-on-primary);
  background: linear-gradient(135deg, var(--jade-9), var(--jade-10) 55%, var(--jade-11));
  box-shadow: 0 6px 16px var(--jade-a5);
  transition: filter 250ms ease-out, box-shadow 250ms ease-out;
}
.login-btn:hover {
  color: var(--tl-on-primary);
  background: linear-gradient(135deg, var(--jade-9), var(--jade-10) 55%, var(--jade-11));
  filter: brightness(1.04);
  box-shadow: 0 8px 20px var(--jade-a6);
}

.capability-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0 14px;
  color: var(--tl-text-3);
  font-size: 12px;
}

.capability-divider::before,
.capability-divider::after {
  content: "";
  flex: 1;
  height: 0.5px;
  background: var(--tl-border);
}

.capability-list {
  display: flex;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
}

.capability-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border: 0.5px solid var(--tl-border);
  border-radius: 4px;
  background: var(--tl-surface-2);
  color: var(--tl-text-2);
  font-size: 12px;
}

.capability-chip i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--jade-9);
}

.capability-chip:nth-child(2) i {
  background: var(--sky-9);
}

.capability-chip:nth-child(3) i {
  background: var(--amber-9);
}

.login-card-footer {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 0.5px solid var(--tl-border);
  color: var(--tl-text-3);
  font-size: 12px;
  text-align: center;
}

.character-note {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 0.5px solid var(--tl-border);
}

.character-avatar {
  width: 42px;
  height: 42px;
  flex: none;
  object-fit: contain;
}

.character-copy {
  min-width: 0;
}

.character-copy strong {
  display: block;
  color: var(--tl-text-strong);
  font-size: 12px;
  font-weight: 600;
}

.character-copy span {
  display: block;
  color: var(--tl-text-3);
  font-size: 12px;
}

.login-slogan {
  position: fixed;
  left: 40px;
  bottom: 36px;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--tl-text-2);
  font-size: 14px;
}

.login-slogan b {
  color: var(--tl-text-strong);
  font-weight: 600;
}
.ver-chip {
  position: fixed; right: 40px; bottom: 36px; z-index: 1;
  font-size: 12px; color: var(--tl-text-3);
  padding: 3px 8px;
  border: 0.5px solid var(--tl-border);
  border-radius: 4px;
  background: var(--sage-a3);
}
@media (max-width: 760px) {
  .login-slogan,
  .ver-chip {
    display: none;
  }
  .login-theme-toggle {
    top: 12px;
    right: 12px;
  }
}
@media (max-width: 480px) {
  .login-card {
    padding: 28px 24px 24px;
  }
}
</style>
