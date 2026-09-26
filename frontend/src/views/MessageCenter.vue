<template>
  <el-card shadow="never" v-loading="loading">
    <template #header>
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold">消息中心</span>
        <span class="text-xs text-gray-400">共 {{ total }} 条，未读 {{ unread }} 条</span>
        <div class="flex-1" />
        <el-select v-model="msgType" placeholder="全部类型" clearable class="!w-[150px]" @change="reload">
          <el-option v-for="o in typeOptions" :key="o.value" :value="o.value" :label="o.label" />
        </el-select>
        <el-checkbox v-model="unreadOnly" @change="reload">仅未读</el-checkbox>
        <el-button class="btn-min" :disabled="!unread" @click="readAll">全部标为已读</el-button>
      </div>
    </template>

    <el-table :data="items" stripe>
      <el-table-column label="" width="44">
        <template #default="{ row }">
          <i class="msg-dot" :class="{ unread: !row.is_read }"></i>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <span class="tl-tag" :style="softStyle(STAT_CARD_COLORS.gray)">{{ messageTypeName(row.msg_type) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column prop="content" label="内容" min-width="320" show-overflow-tooltip />
      <el-table-column label="时间" width="170">
        <template #default="{ row }"><span class="num">{{ fmtDateTime(row.create_time) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right" class-name="op-col">
        <template #default="{ row }">
          <el-button v-if="row.link" size="small" type="primary" link @click="open(row)">查看</el-button>
          <el-button v-if="!row.is_read" size="small" link @click="readOne(row)">标为已读</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="暂无消息" :image-size="80" /></template>
    </el-table>

    <TlPagination v-model:page="page" v-model:size="size" :total="total"
                  @page-change="load" @size-change="onSizeChange" />
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import client from '../api/client'
import TlPagination from '../components/TlPagination.vue'
import { useAuthStore } from '../stores/auth'
import { messageTypeName, messageTypeOptions, softStyle, STAT_CARD_COLORS } from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import type { MessageItem, MessagePage } from '../types'

const auth = useAuthStore()
const router = useRouter()
const items = ref<MessageItem[]>([])
const total = ref(0)
const unread = ref(0)
const page = ref(1)
const size = ref(20)
const loading = ref(false)
const msgType = ref('')
const unreadOnly = ref(false)

const typeOptions = computed(() => messageTypeOptions())

async function load(p = page.value) {
  page.value = p
  loading.value = true
  try {
    const { data } = await client.get<MessagePage>('/messages', {
      params: {
        page: p, size: size.value,
        msg_type: msgType.value || undefined,
        unread_only: unreadOnly.value || undefined,
      },
    })
    items.value = data.items
    total.value = data.total
    unread.value = data.unread
  } finally {
    loading.value = false
  }
}

function reload() {
  return load(1)
}

function onSizeChange(n: number) {
  size.value = n
  void load(1)
}

async function readOne(row: MessageItem) {
  await client.post(`/messages/${row.id}/read`)
  row.is_read = true
  unread.value = Math.max(unread.value - 1, 0)
}

async function open(row: MessageItem) {
  await readOne(row)
  if (row.link) router.push(row.link)
}

async function readAll() {
  await client.post('/messages/read', { ids: [] })
  ElMessage.success('已全部标为已读')
  await load()
}

onMounted(async () => {
  await auth.fetchMeta()
  await load()
})
</script>

<style scoped>
.msg-dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--tl-border-strong);
}
.msg-dot.unread { background: var(--tl-brand-mint); }
</style>
