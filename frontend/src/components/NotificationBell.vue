<template>
  <el-popover placement="bottom-end" :width="360" trigger="click" @show="loadRecent">
    <template #reference>
      <button class="icon-btn" :title="unread ? `${unread} 条未读消息` : '消息中心'">
        <el-badge :value="unread" :max="99" :hidden="!unread" class="bell-badge">
          <el-icon :size="14"><Bell /></el-icon>
        </el-badge>
      </button>
    </template>

    <div class="flex items-center gap-2 px-1 pb-2" style="border-bottom: 1px solid var(--tl-border)">
      <span class="text-xs font-semibold">消息中心</span>
      <span v-if="unread" class="text-xs text-gray-400">{{ unread }} 条未读</span>
      <div class="flex-1" />
      <el-button size="small" link :disabled="!unread" @click="readAll">全部已读</el-button>
    </div>

    <div v-loading="loading" class="max-h-[320px] overflow-auto py-1">
      <el-empty v-if="!loading && !recent.length" description="暂无消息" :image-size="56" />
      <div v-for="m in recent" :key="m.id"
           class="msg-item flex items-start gap-2 px-2 py-2 rounded cursor-pointer"
           @click="openMessage(m)">
        <i class="msg-dot" :class="{ unread: !m.is_read }"></i>
        <div class="min-w-0 flex-1">
          <div class="text-xs font-medium truncate" style="color: var(--tl-text-1)">{{ m.title }}</div>
          <div class="text-2xs text-gray-400 truncate">{{ m.content }}</div>
          <div class="text-2xs text-gray-400 mt-0.5">
            {{ messageTypeName(m.msg_type) }} · {{ fmtDateTime(m.create_time) }}
          </div>
        </div>
      </div>
    </div>

    <div class="flex items-center justify-center pt-2" style="border-top: 1px solid var(--tl-border)">
      <el-button size="small" link @click="goAll">查看全部消息 →</el-button>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import client from '../api/client'
import { messageTypeName } from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import type { MessageItem, MessagePage } from '../types'

const router = useRouter()
const unread = ref(0)
const recent = ref<MessageItem[]>([])
const loading = ref(false)
let timer: number | undefined

/** 未读数刷新：定时 + 窗口重新可见时（多标签页阅读状态最终一致） */
async function refreshUnread() {
  const { data } = await client.get<{ unread: number }>('/messages/unread-count')
  unread.value = data.unread
}

async function loadRecent() {
  loading.value = true
  try {
    const { data } = await client.get<MessagePage>('/messages', { params: { page: 1, size: 10 } })
    recent.value = data.items
    unread.value = data.unread
  } finally {
    loading.value = false
  }
}

async function openMessage(m: MessageItem) {
  if (!m.is_read) {
    await client.post(`/messages/${m.id}/read`)
    m.is_read = true
    unread.value = Math.max(unread.value - 1, 0)
  }
  if (m.link) router.push(m.link)
}

async function readAll() {
  await client.post('/messages/read', { ids: [] })
  await loadRecent()
}

function goAll() {
  router.push('/messages')
}

function onVisible() {
  if (document.visibilityState === 'visible') void refreshUnread()
}

onMounted(() => {
  void refreshUnread()
  timer = window.setInterval(refreshUnread, 60000)
  document.addEventListener('visibilitychange', onVisible)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
  document.removeEventListener('visibilitychange', onVisible)
})

defineExpose({ refreshUnread })
</script>

<style scoped>
.bell-badge :deep(.el-badge__content) { font-size: 10px; height: 15px; line-height: 15px; padding: 0 4px; }
.msg-item:hover { background: var(--tl-surface-2); }
.msg-dot {
  width: 6px; height: 6px; border-radius: 50%; flex: none; margin-top: 5px;
  background: var(--tl-border-strong);
}
.msg-dot.unread { background: var(--tl-brand-mint); }
</style>
