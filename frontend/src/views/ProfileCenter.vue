<template>
  <div class="profile-page">
    <el-card shadow="never">
      <div class="profile-head">
        <UserAvatar :avatar="auth.user?.avatar" :avatar-url="auth.user?.avatar_url"
                    :name="displayName" :size="64" />
        <div class="min-w-0">
          <div class="text-base font-semibold">{{ displayName }}</div>
          <div class="text-xs text-gray-400 mt-1">
            {{ auth.user?.username }} · {{ auth.user?.role_name || '未分配角色' }}
          </div>
        </div>
        <div class="flex-1" />
        <span class="save-state" :class="`is-${saveState}`">{{ saveStateLabel }}</span>
      </div>
    </el-card>

    <el-tabs v-model="tab" class="profile-tabs">
      <el-tab-pane label="个人资料" name="profile">
        <div class="profile-grid">
          <section class="setting-block avatar-setting">
            <div class="block-title">头像</div>
            <div class="avatar-stage">
              <UserAvatar :avatar="auth.user?.avatar" :avatar-url="auth.user?.avatar_url"
                          :name="displayName" :size="96" />
            </div>
            <div class="preset-grid">
              <button v-for="preset in presetIds" :key="preset" class="preset-btn"
                      :class="{ active: auth.user?.avatar === `preset:${preset}` }"
                      type="button" :title="presetName(preset)" @click="setPreset(preset)">
                <PresetAvatar :preset-id="preset" :size="34" />
              </button>
            </div>
            <div class="flex gap-2 mt-4">
              <el-button class="btn-min" @click="fileInput?.click()">
                <el-icon class="mr-1"><Upload /></el-icon>上传
              </el-button>
              <el-button class="btn-min" :disabled="!auth.user?.avatar" @click="resetAvatar">恢复默认</el-button>
            </div>
            <input ref="fileInput" class="hidden" type="file" accept=".png,.jpg,.jpeg,.webp" @change="uploadAvatar" />
          </section>

          <section class="setting-block">
            <div class="block-title">资料</div>
            <el-form label-position="top" class="max-w-[520px]">
              <el-form-item label="用户名">
                <el-input :model-value="auth.user?.username" disabled />
              </el-form-item>
              <el-form-item label="姓名">
                <el-input v-model="form.realname" maxlength="64" />
              </el-form-item>
              <el-form-item label="手机号">
                <el-input v-model="form.phone" maxlength="32" />
              </el-form-item>
            </el-form>
            <div class="meta-grid">
              <span>所属组织</span><b>{{ auth.user?.group_names?.join('、') || '未分配' }}</b>
              <span>创建时间</span><b>{{ fmtDateTime(auth.user?.create_time) }}</b>
              <span>最近登录</span><b>{{ fmtDateTime(auth.user?.last_login) }}</b>
            </div>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane label="账号安全" name="security">
        <div class="profile-grid">
          <section class="setting-block">
            <div class="block-title">登录邮箱</div>
            <el-form ref="emailFormRef" :model="emailForm" :rules="emailRules" label-position="top"
                     class="max-w-[520px]">
              <el-form-item label="当前邮箱">
                <el-input :model-value="auth.user?.email || '未绑定'" disabled />
              </el-form-item>
              <el-form-item label="新邮箱" prop="new_email">
                <el-input v-model="emailForm.new_email" autocomplete="email" />
              </el-form-item>
              <el-form-item label="当前密码" prop="current_password">
                <el-input v-model="emailForm.current_password" type="password" show-password
                          autocomplete="current-password" />
              </el-form-item>
              <el-button type="primary" :loading="emailSaving" @click="requestEmailChange">发送确认链接</el-button>
            </el-form>
          </section>

          <section class="setting-block">
            <div class="block-title">修改密码</div>
            <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules"
                     label-position="top" class="max-w-[520px]">
              <el-form-item label="当前密码" prop="old_password">
                <el-input v-model="passwordForm.old_password" type="password" show-password
                          autocomplete="current-password" />
              </el-form-item>
              <el-form-item label="新密码" prop="new_password">
                <el-input v-model="passwordForm.new_password" type="password" show-password
                          autocomplete="new-password" />
              </el-form-item>
              <el-form-item label="确认新密码" prop="confirm_password">
                <el-input v-model="passwordForm.confirm_password" type="password" show-password
                          autocomplete="new-password" />
              </el-form-item>
              <el-button type="primary" :loading="passwordSaving" @click="changePassword">修改密码</el-button>
            </el-form>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane label="登录会话" name="sessions">
        <section class="setting-block wide">
          <div class="flex items-center gap-2 mb-3">
            <div class="block-title mb-0">活跃会话</div>
            <div class="flex-1" />
            <el-button class="btn-min" :loading="sessionLoading" @click="revokeOthers">退出其他设备</el-button>
          </div>
          <el-table v-loading="sessionLoading" :data="sessions" stripe>
            <el-table-column label="设备" min-width="220">
              <template #default="{ row }">
                <div class="truncate">{{ row.user_agent || '未知设备' }}</div>
                <div v-if="row.is_current" class="text-xs" style="color: var(--tl-primary)">当前会话</div>
              </template>
            </el-table-column>
            <el-table-column label="IP" width="150" prop="ip" />
            <el-table-column label="最近续期" width="170">
              <template #default="{ row }">{{ fmtDateTime(row.last_seen_at) }}</template>
            </el-table-column>
            <el-table-column label="登录时间" width="170">
              <template #default="{ row }">{{ fmtDateTime(row.create_time) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="revokeSession(row)">退出</el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </el-tab-pane>

      <el-tab-pane label="消息偏好" name="preferences">
        <div class="profile-grid">
          <section class="setting-block">
            <div class="block-title">站内消息</div>
            <div class="pref-list">
              <div v-for="(label, key) in messageTypes" :key="key" class="pref-row">
                <span>{{ label }}</span>
                <el-switch :model-value="!disabledTypes.includes(key)" :disabled="key === 'system'"
                           @change="toggleMessageType(key, Boolean($event))" />
              </div>
            </div>
          </section>
          <section class="setting-block">
            <div class="block-title">开放接口</div>
            <el-button @click="router.push('/tokens')">
              <el-icon class="mr-1"><Key /></el-icon>访问令牌
            </el-button>
          </section>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Key, Upload } from '@element-plus/icons-vue'
import client from '../api/client'
import PresetAvatar from '../components/PresetAvatar.vue'
import UserAvatar from '../components/UserAvatar.vue'
import { AUTOSAVE_STATE_LABEL, useAutosave } from '../composables/useAutosave'
import { useAuthStore } from '../stores/auth'
import { fmtDateTime } from '../utils/format'
import { registerUnsavedGuard } from '../utils/unsavedGuard'
import type { UserSession } from '../types'

const auth = useAuthStore()
const router = useRouter()
const tab = ref('profile')
const fileInput = ref<HTMLInputElement>()
const sessions = ref<UserSession[]>([])
const sessionLoading = ref(false)
const form = reactive({ realname: '', phone: '' })
const disabledTypes = ref<string[]>([])
let hydrating = true

const displayName = computed(() => auth.user?.realname || auth.user?.username || '')
const presetIds = computed(() => Object.keys((auth.meta?.avatar_presets as Record<string, string>) || {}))
const messageTypes = computed(() => (auth.meta?.message_type as Record<string, string>) || {})
const saveStateLabel = computed(() => AUTOSAVE_STATE_LABEL[saveState.value])

const emailFormRef = ref<FormInstance>()
const emailSaving = ref(false)
const emailForm = reactive({ new_email: '', current_password: '' })
const emailRules: FormRules = {
  new_email: [
    { required: true, message: '请输入新邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  current_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
}

const passwordFormRef = ref<FormInstance>()
const passwordSaving = ref(false)
const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const passwordRules: FormRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '新密码至少 8 位', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value && value === passwordForm.old_password) callback(new Error('新密码不能与原密码相同'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== passwordForm.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

async function customAskOnLeave() {
  try {
    await ElMessageBox.confirm('个人中心有未保存的修改，离开将丢失这些内容。', '未保存的修改', {
      confirmButtonText: '继续保存',
      cancelButtonText: '放弃修改',
      distinguishCancelAndClose: true,
      type: 'warning',
    })
    return 'save' as const
  } catch (action) {
    return action === 'cancel' ? 'discard' as const : 'stay' as const
  }
}

async function saveAll() {
  const [profileRes, prefsRes] = await Promise.all([
    client.put('/auth/profile', { realname: form.realname, phone: form.phone }),
    client.put('/auth/preferences', { disabled_types: disabledTypes.value }),
  ])
  if (auth.user) {
    auth.user = { ...auth.user, ...profileRes.data, message_prefs: prefsRes.data }
  }
}

const {
  state: saveState, hasUnsaved, markDirty, markSaved, saveNow, confirmLeave,
} = useAutosave({ save: saveAll, interval: 1000, askOnLeave: customAskOnLeave })
const unregisterGuard = registerUnsavedGuard(confirmLeave)

function hydrate() {
  hydrating = true
  form.realname = auth.user?.realname || ''
  form.phone = auth.user?.phone || ''
  disabledTypes.value = [...(auth.user?.message_prefs?.disabled_types || [])]
  markSaved()
  void nextTick(() => { hydrating = false })
}

watch(() => [form.realname, form.phone, disabledTypes.value.join(',')], () => {
  if (!hydrating) markDirty()
})

function presetName(id: string) {
  return (auth.meta?.avatar_presets as Record<string, string> | undefined)?.[id] || `预置头像 ${id}`
}

async function setPreset(id: string) {
  const { data } = await client.put('/auth/avatar', { preset_id: id })
  if (auth.user) auth.user = { ...auth.user, ...data }
}

async function resetAvatar() {
  const { data } = await client.delete('/auth/avatar')
  if (auth.user) auth.user = { ...auth.user, ...data }
}

async function uploadAvatar(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.warning('头像大小不能超过 2MB')
    return
  }
  const body = new FormData()
  body.append('file', file)
  const { data } = await client.post('/auth/avatar', body)
  if (auth.user) auth.user = { ...auth.user, ...data }
}

async function requestEmailChange() {
  const valid = await emailFormRef.value?.validate().catch(() => false)
  if (!valid) return
  emailSaving.value = true
  try {
    await client.post('/auth/email-change', emailForm)
    ElMessage.success('确认邮件已发送，请查收新邮箱')
    emailForm.new_email = ''
    emailForm.current_password = ''
  } finally {
    emailSaving.value = false
  }
}

async function changePassword() {
  const valid = await passwordFormRef.value?.validate().catch(() => false)
  if (!valid) return
  if (hasUnsaved.value && !(await saveNow())) return
  passwordSaving.value = true
  try {
    await client.post('/auth/password', {
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success('密码修改成功，请重新登录')
    await auth.logout(true)
  } finally {
    passwordSaving.value = false
  }
}

async function loadSessions() {
  sessionLoading.value = true
  try {
    sessions.value = (await client.get<UserSession[]>('/auth/sessions')).data
  } finally {
    sessionLoading.value = false
  }
}

async function revokeSession(row: UserSession) {
  const { data } = await client.delete(`/auth/sessions/${row.id}`)
  if (row.is_current || data.current) {
    ElMessage.success('当前会话已退出')
    await auth.logout(true)
    return
  }
  ElMessage.success('已退出该设备')
  await loadSessions()
}

async function revokeOthers() {
  sessionLoading.value = true
  try {
    const { data } = await client.post('/auth/sessions/revoke-others')
    ElMessage.success(data.count ? `已退出 ${data.count} 个设备` : '没有其他活跃设备')
    await loadSessions()
  } finally {
    sessionLoading.value = false
  }
}

function toggleMessageType(key: string, enabled: boolean) {
  disabledTypes.value = enabled
    ? disabledTypes.value.filter((item) => item !== key)
    : [...new Set([...disabledTypes.value, key])]
}

onMounted(async () => {
  await Promise.all([auth.fetchMeta(), auth.fetchMe()])
  hydrate()
  await loadSessions()
})

onBeforeUnmount(unregisterGuard)
onBeforeRouteLeave(() => confirmLeave())
</script>

<style scoped>
.profile-page { display: flex; flex-direction: column; gap: 16px; }
.profile-head { display: flex; align-items: center; gap: 14px; }
.save-state { font-size: 12px; color: var(--tl-text-3); }
.save-state.is-failed, .save-state.is-conflict { color: var(--tl-danger); }
.profile-tabs { min-height: 420px; }
.profile-grid { display: grid; grid-template-columns: minmax(300px, 420px) minmax(320px, 1fr); gap: 16px; }
.setting-block {
  border: 1px solid var(--tl-border);
  border-radius: 8px;
  background: var(--tl-surface);
  padding: 18px;
  min-width: 0;
}
.setting-block.wide { width: 100%; }
.block-title { font-size: 14px; font-weight: 600; margin-bottom: 16px; color: var(--tl-text-1); }
.avatar-stage { display: flex; justify-content: center; margin-bottom: 16px; }
.preset-grid { display: grid; grid-template-columns: repeat(6, 38px); gap: 8px; justify-content: center; }
.preset-btn {
  width: 38px; height: 38px; padding: 2px; border: 1px solid transparent; border-radius: 8px;
  background: transparent; cursor: pointer; transition: border-color .15s, background .15s;
}
.preset-btn:hover, .preset-btn.active { border-color: var(--tl-primary); background: var(--tl-surface-2); }
.meta-grid { display: grid; grid-template-columns: 88px 1fr; gap: 10px 14px; font-size: 13px; margin-top: 16px; }
.meta-grid span { color: var(--tl-text-3); }
.meta-grid b { font-weight: 500; color: var(--tl-text-2); }
.pref-list { max-width: 480px; }
.pref-row { display: flex; align-items: center; justify-content: space-between; padding: 11px 0; border-bottom: 1px solid var(--tl-border); }
.pref-row:last-child { border-bottom: 0; }
@media (max-width: 900px) {
  .profile-grid { grid-template-columns: 1fr; }
}
</style>
