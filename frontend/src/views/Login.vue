<template>
  <div class="login-bg min-h-full flex items-center justify-center">
    <!-- 装饰：细点阵与光斑 -->
    <div class="bg-dots"></div>
    <div class="bg-blob blob-1"></div>
    <div class="bg-blob blob-2"></div>
    <div class="bg-blob blob-3"></div>

    <div class="login-card w-[400px] max-w-[calc(100vw-32px)] px-9 pt-10 pb-7">
      <span class="corner tl"></span><span class="corner br"></span>

      <!-- 品牌区：标志 + 双行文字组（与侧边栏一致） -->
      <div class="flex items-center justify-center gap-3.5 mb-7">
        <BrandMark :size="56" class="flex-none logo-mark" />
        <div class="flex flex-col items-start gap-[7px]">
          <div class="text-[27px] font-extrabold tracking-[1px] leading-none" style="color: var(--tl-text-1)">Talos</div>
          <span class="subtitle"><span class="dot"></span>漏洞管理平台</span>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="formRules" label-position="top" @keyup.enter="onLogin">
        <el-form-item prop="username" class="field">
          <template #label>用户名</template>
          <el-input v-model="form.username" placeholder="请输入用户名" autocomplete="username" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password" class="field">
          <template #label>密码</template>
          <el-input v-model="form.password" type="password" placeholder="请输入密码" autocomplete="current-password" show-password :prefix-icon="Key" />
        </el-form-item>

        <div class="aux-row">
          <el-checkbox v-model="remember">记住我</el-checkbox>
        </div>

        <el-button class="login-btn w-full" size="large" :loading="loading" @click="onLogin">
          登 录
          <el-icon class="ml-1"><Right /></el-icon>
        </el-button>
      </el-form>

      <div class="divider">平台能力</div>
      <div class="env-chips">
        <span class="chip"><span class="chip-dot" style="background: var(--tl-primary)"></span>漏洞全生命周期</span>
        <span class="chip"><span class="chip-dot" style="background: var(--tl-accent)"></span>资产管理</span>
        <span class="chip"><span class="chip-dot" style="background: var(--tl-warning)"></span>报告与态势</span>
      </div>

      <div class="footer">Talos Vulnerability Management<span class="sep">|</span>内置 admin 登录</div>
    </div>

    <div class="slogan">🛡️ <b>Talos</b> · 漏洞收录、验证、复测、报告与安全态势一站式管理</div>
    <div class="ver-chip">Talos v2.8.0 · Lovely UI</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { Key, Right, User } from '@element-plus/icons-vue'
import BrandMark from '../components/BrandMark.vue'
import { useAuthStore } from '../stores/auth'

const REMEMBER_KEY = 'tl_login_username'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(false)
const remember = ref(false)
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
  const valid = await formRef.value.validate().catch(() => false)
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
/* 背景与光斑：明暗双态跟随 --tl-* 令牌（html.dark 自动切换） */
.login-bg {
  --lp-primary: var(--tl-primary);
  --lp-soft: color-mix(in srgb, var(--tl-primary) 12%, transparent);
  --lp-glow-a: color-mix(in srgb, var(--tl-primary) 11%, transparent);
  --lp-glow-b: color-mix(in srgb, var(--tl-accent) 9%, transparent);
  --lp-glow-c: color-mix(in srgb, var(--tl-primary) 9%, transparent);
  --lp-dot: color-mix(in srgb, var(--tl-text-1) 5%, transparent);
  --lp-chip-bg: var(--tl-surface-2);
  --lp-field-bg: var(--tl-surface-2);
  --lp-btn-grad: linear-gradient(135deg, #10b981, #059669 55%, #047857);
  --lp-btn-shadow: color-mix(in srgb, var(--tl-primary) 28%, transparent);
  position: relative;
  background:
    radial-gradient(720px 420px at 12% 8%, var(--lp-glow-a), transparent 60%),
    radial-gradient(640px 420px at 88% 12%, var(--lp-glow-b), transparent 60%),
    radial-gradient(760px 480px at 78% 92%, var(--lp-glow-c), transparent 62%),
    var(--tl-bg);
}
html.dark .login-bg {
  --lp-btn-grad: linear-gradient(135deg, #6ee7b7, #34d399 55%, #10b981);
  --lp-btn-shadow: color-mix(in srgb, var(--tl-primary) 22%, transparent);
}

.bg-dots {
  position: fixed; inset: 0; pointer-events: none;
  background-image: radial-gradient(var(--lp-dot) 1px, transparent 1px);
  background-size: 22px 22px;
  mask-image: radial-gradient(ellipse at center, rgba(0, 0, 0, .9), transparent 75%);
}
.bg-blob { position: fixed; border-radius: 50%; filter: blur(70px); opacity: .55; pointer-events: none; }
.blob-1 { width: 340px; height: 340px; left: -90px; bottom: -110px; background: var(--lp-glow-a); }
.blob-2 { width: 300px; height: 300px; right: -70px; top: -80px; background: var(--lp-glow-b); }
.blob-3 { width: 220px; height: 220px; right: 16%; bottom: -80px; background: var(--lp-glow-c); }

.login-card {
  position: relative; z-index: 1;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(15, 23, 20, .04), 0 16px 40px rgba(15, 23, 20, .08);
}
.corner { position: absolute; width: 46px; height: 46px; pointer-events: none; }
.corner.tl { top: 14px; left: 14px; border-top: 2px solid var(--lp-soft); border-left: 2px solid var(--lp-soft); border-radius: 8px 0 0 0; }
.corner.br { right: 14px; bottom: 14px; border-bottom: 2px solid var(--lp-soft); border-right: 2px solid var(--lp-soft); border-radius: 0 0 8px 0; }

.logo-mark { color: var(--tl-brand-mint); }
.subtitle {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--tl-text-2);
  background: var(--lp-soft); border: 1px solid var(--tl-border);
  padding: 3px 10px; border-radius: 999px;
}
.subtitle .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--tl-primary); box-shadow: 0 0 0 3px var(--lp-soft); }

/* 表单：标签在字段上方，输入框对齐 demo（44px 高、10px 圆角、聚焦薄荷描边） */
.field { margin-bottom: 16px; }
.field :deep(.el-form-item__label) {
  font-size: 13px; font-weight: 500; color: var(--tl-text-2);
  margin-bottom: 6px; line-height: 1.4; padding: 0;
}
.field :deep(.el-input__wrapper) {
  height: 44px; border-radius: 10px;
  background: var(--lp-field-bg);
  box-shadow: 0 0 0 1px var(--tl-border) inset;
  transition: box-shadow .15s, background .15s;
}
.field :deep(.el-input__wrapper.is-focus) {
  background: var(--tl-surface);
  box-shadow: 0 0 0 1px var(--tl-primary) inset, 0 0 0 3px var(--lp-soft);
}

.aux-row { display: flex; justify-content: space-between; align-items: center; margin: 2px 0 18px; font-size: 13px; color: var(--tl-text-2); }
.aux-row :deep(.el-checkbox__label) { font-size: 13px; color: var(--tl-text-2); }

/* 登录按钮：薄荷渐变（亮：白字 / 暗：深墨字），对比度 ≥4.5:1 */
.login-btn {
  height: 46px; border: none; border-radius: 10px;
  font-size: 15px; font-weight: 700; letter-spacing: 2px;
  color: var(--tl-on-primary);
  background: var(--lp-btn-grad);
  box-shadow: 0 6px 16px var(--lp-btn-shadow);
  transition: filter .15s ease, box-shadow .15s ease, transform .12s ease;
}
.login-btn:hover {
  color: var(--tl-on-primary);
  background: var(--lp-btn-grad);
  filter: brightness(1.06);
  box-shadow: 0 8px 20px var(--lp-btn-shadow);
}
.login-btn:active { transform: translateY(1px); }

.divider { display: flex; align-items: center; gap: 12px; margin: 22px 0 14px; color: var(--tl-text-3); font-size: 12px; }
.divider::before, .divider::after { content: ""; flex: 1; height: 1px; background: var(--tl-border); }
.env-chips { display: flex; justify-content: center; gap: 6px; flex-wrap: wrap; }
.chip {
  font-size: 12px; color: var(--tl-text-2); background: var(--lp-chip-bg);
  border: 1px solid var(--tl-border); border-radius: 999px; padding: 3px 8px;
  display: inline-flex; align-items: center; gap: 5px;
}
.chip-dot { width: 6px; height: 6px; border-radius: 50%; }

.footer { margin-top: 18px; text-align: center; font-size: 12px; color: var(--tl-text-3); }
.footer .sep { margin: 0 8px; color: var(--tl-border); }

.slogan {
  position: fixed; left: 40px; bottom: 36px; z-index: 1;
  color: var(--tl-text-2); font-size: 13px; letter-spacing: .5px;
  display: flex; align-items: center; gap: 10px;
}
.slogan b { color: var(--tl-text-1); }
.ver-chip {
  position: fixed; right: 40px; bottom: 36px; z-index: 1;
  font-size: 12px; color: var(--tl-text-2);
  background: color-mix(in srgb, var(--tl-surface) 70%, transparent);
  border: 1px solid var(--tl-border);
  padding: 4px 12px; border-radius: 999px; backdrop-filter: blur(6px);
}
@media (max-width: 900px) { .slogan, .ver-chip { display: none; } }
</style>
