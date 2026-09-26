<template>
  <el-tabs v-model="tab" class="tl-tabs">
    <!-- ---------- 渠道配置 ---------- -->
    <el-tab-pane label="渠道配置" name="channels">
      <el-card shadow="never" v-loading="loading">
        <template #header>
          <div class="flex items-center gap-2">
            <span class="text-sm font-semibold">通知渠道</span>
            <span class="text-xs text-gray-400">
              漏洞创建 / 工单认领 / 状态流转 / 复测完成 / SLA 到期与逾期事件推送
            </span>
            <div class="flex-1" />
            <el-button type="primary" class="btn-min" @click="openFormDialog()">
              <el-icon class="mr-1"><Plus /></el-icon>新建渠道
            </el-button>
          </div>
        </template>

        <el-table :data="items" stripe>
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">
              <span class="ktag">{{ channelTypeName(row.type) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="订阅事件" min-width="220">
            <template #default="{ row }">
              <div v-if="row.events?.length" class="flex items-center flex-wrap gap-1">
                <span v-for="e in row.events.slice(0, 2)" :key="e" class="ktag">{{ eventName(e) }}</span>
                <el-popover v-if="row.events.length > 2" placement="left" :width="240" trigger="hover">
                  <template #reference>
                    <el-button size="small" type="primary" link class="!p-0">+{{ row.events.length - 2 }}</el-button>
                  </template>
                  <div class="flex flex-wrap gap-1">
                    <span v-for="e in row.events" :key="e" class="ktag">{{ eventName(e) }}</span>
                  </div>
                </el-popover>
              </div>
              <span v-else class="text-gray-400">未订阅</span>
            </template>
          </el-table-column>
          <el-table-column label="配置" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.type === 'email' ? (row.config?.recipients ?? []).join('、') : row.config?.url }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-switch :model-value="row.is_active" @change="() => toggleActive(row)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right" class-name="op-col">
            <template #default="{ row }">
              <el-button size="small" type="primary" link :loading="testing === row.id" @click="testSend(row)">
                测试发送
              </el-button>
              <el-button size="small" link @click="openFormDialog(row)">编辑</el-button>
              <el-popconfirm title="确认删除该渠道？" @confirm="remove(row.id)">
                <template #reference>
                  <el-button size="small" type="danger" link>删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无通知渠道，可新建企业微信 / 钉钉 / 邮件渠道" :image-size="80" />
          </template>
        </el-table>

        <TlPagination v-model:page="page" v-model:size="size" :total="total"
                      @page-change="load" @size-change="onSizeChange" />
      </el-card>
    </el-tab-pane>

    <!-- ---------- 投递记录 ---------- -->
    <el-tab-pane label="投递记录" name="deliveries">
      <el-card shadow="never" v-loading="dlLoading">
        <template #header>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-sm font-semibold">投递记录</span>
            <span class="text-xs text-gray-400">每条通知的最终状态可查询；进程重启不丢失待重试记录</span>
            <div class="flex-1" />
            <el-select v-model="dlFilter.channel_id" placeholder="全部渠道" clearable class="!w-[150px]"
                       @change="loadDeliveries(1)">
              <el-option v-for="c in items" :key="c.id" :value="c.id" :label="c.name" />
            </el-select>
            <el-input v-model="dlFilter.event" placeholder="事件码" clearable class="!w-[130px]" @change="loadDeliveries(1)" />
            <el-select v-model="dlFilter.status" placeholder="全部状态" clearable class="!w-[130px]"
                       @change="loadDeliveries(1)">
              <el-option v-for="o in deliveryStatusOptions" :key="o.value" :value="o.value" :label="o.label" />
            </el-select>
            <el-date-picker v-model="dlRange" type="daterange" value-format="YYYY-MM-DD" unformat
                            start-placeholder="开始日期" end-placeholder="结束日期" class="!w-[240px]"
                            @change="loadDeliveries(1)" />
            <el-button class="btn-min" @click="loadDeliveries(dlPage)">刷新</el-button>
          </div>
        </template>

        <el-table :data="deliveries" stripe>
          <el-table-column label="时间" width="170">
            <template #default="{ row }"><span class="num">{{ fmtDateTime(row.request_time) }}</span></template>
          </el-table-column>
          <el-table-column label="渠道" min-width="140">
            <template #default="{ row }">
              {{ row.channel_name || '-' }}
              <span class="text-xs text-gray-400">（{{ channelTypeName(row.channel_type) }}）</span>
            </template>
          </el-table-column>
          <el-table-column label="事件" width="140">
            <template #default="{ row }">{{ eventName(row.event) }}</template>
          </el-table-column>
          <el-table-column prop="target" label="目标" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <span class="dot-tag" :style="dotStyle(notifyDeliveryMeta(row.status).color)">
                <i></i>{{ notifyDeliveryMeta(row.status).label }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="尝试" width="70">
            <template #default="{ row }"><span class="num">{{ row.attempts }}</span></template>
          </el-table-column>
          <el-table-column label="HTTP" width="70">
            <template #default="{ row }"><span class="num">{{ row.http_status || '-' }}</span></template>
          </el-table-column>
          <el-table-column label="最后错误" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.dead_letter_reason" class="text-xs" style="color: var(--tl-danger, #DC2626)">
                {{ row.dead_letter_reason }}
              </span>
              <span v-else-if="row.last_error" class="text-xs">{{ row.last_error }}</span>
              <span v-else class="text-xs text-gray-400">-</span>
            </template>
          </el-table-column>
          <el-table-column label="下次重试" width="170">
            <template #default="{ row }">
              <span class="num">{{ row.next_retry_at ? fmtDateTime(row.next_retry_at) : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right" class-name="op-col">
            <template #default="{ row }">
              <el-button v-if="row.status === 'failed' || row.status === 'dead'" size="small" type="primary" link
                         @click="replay(row)">重放</el-button>
            </template>
          </el-table-column>
          <template #empty><el-empty description="暂无投递记录" :image-size="80" /></template>
        </el-table>

        <TlPagination v-model:page="dlPage" v-model:size="dlSize" :total="dlTotal"
                      @page-change="loadDeliveries" @size-change="onDeliverySizeChange" />
      </el-card>
    </el-tab-pane>
  </el-tabs>

  <el-dialog :close-on-click-modal="false" v-model="dialogVisible"
             :title="editing ? '编辑渠道' : '新建渠道'" width="640px">
    <el-form :model="form" label-width="90px">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" maxlength="64" placeholder="例如：安全群机器人" />
      </el-form-item>
      <el-form-item label="类型" required>
        <el-select v-model="form.type" class="w-full" :disabled="editing">
          <el-option v-for="(name, code) in channelTypes" :key="code" :label="name" :value="code" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.type === 'email'" label="收件邮箱" required>
        <el-input v-model="recipientsText" type="textarea" :rows="3" placeholder="每行一个收件邮箱" />
      </el-form-item>
      <el-form-item v-else-if="form.type" label="Webhook" required>
        <el-input v-model="webhookUrl" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
      </el-form-item>
      <el-form-item label="订阅事件" required>
        <el-checkbox-group v-model="form.events">
          <el-checkbox v-for="(name, code) in eventDict" :key="code" :value="code">{{ name }}</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="form.is_active" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import client from '../api/client'
import { useListPage } from '../composables/useListPage'
import { useAuthStore } from '../stores/auth'
import { dotStyle, notifyDeliveryMeta, notifyDeliveryStatusOptions } from '../utils/colors'
import { fmtDateTime } from '../utils/format'
import TlPagination from '../components/TlPagination.vue'
import type { NotifyChannel, NotifyDelivery, NotifyTestResult } from '../types'

const auth = useAuthStore()
const tab = ref('channels')
const { items, total, page, size, loading, load, onSizeChange } = useListPage<NotifyChannel>('/notify-channels')

// 异构 meta 边界内取用时收窄为「码 → 名称」字典
const channelTypes = computed<Record<string, string>>(() => auth.meta?.notify_channel_types ?? {})
const eventDict = computed<Record<string, string>>(() => auth.meta?.notify_events ?? {})
const channelTypeName = (t: string) => channelTypes.value[t] ?? t
const eventName = (e: string) => eventDict.value[e] ?? e

const deliveryStatusOptions = computed(() => notifyDeliveryStatusOptions())

// ---------- 投递记录 ----------
const deliveries = ref<NotifyDelivery[]>([])
const dlTotal = ref(0)
const dlPage = ref(1)
const dlSize = ref(20)
const dlLoading = ref(false)
const dlRange = ref<[string, string] | null>(null)
const dlFilter = reactive<{ event: string; status: string; channel_id: number | null }>({
  event: '', status: '', channel_id: null,
})

async function loadDeliveries(p = dlPage.value) {
  dlPage.value = p
  dlLoading.value = true
  try {
    const { data } = await client.get('/notify-channels/deliveries', {
      params: {
        page: p, size: dlSize.value,
        channel_id: dlFilter.channel_id ?? undefined,
        event: dlFilter.event || undefined,
        status: dlFilter.status || undefined,
        date_from: dlRange.value?.[0] || undefined,
        date_to: dlRange.value?.[1] || undefined,
      },
    })
    deliveries.value = data.items
    dlTotal.value = data.total
  } finally {
    dlLoading.value = false
  }
}

function onDeliverySizeChange(n: number) {
  dlSize.value = n
  void loadDeliveries(1)
}

async function replay(row: NotifyDelivery) {
  const { data } = await client.post(`/notify-channels/deliveries/${row.id}/replay`)
  ElMessage[data.status === 'success' ? 'success' : 'warning'](
    data.status === 'success' ? '重放成功，通知已送达' : `重放未成功：${data.last_error || data.dead_letter_reason || '未知错误'}`,
  )
  await loadDeliveries()
}

// ---------- 渠道表单 ----------
const dialogVisible = ref(false)
const saving = ref(false)
const testing = ref<number | null>(null)
const editing = ref(false)
const editId = ref<number | null>(null)
const webhookUrl = ref('')
const recipientsText = ref('')
const form = reactive({ name: '', type: 'wecom', events: [] as string[], is_active: true })

function openFormDialog(row?: NotifyChannel) {
  editing.value = !!row
  editId.value = row?.id ?? null
  form.name = row?.name ?? ''
  form.type = row?.type ?? 'wecom'
  form.events = row ? [...(row.events ?? [])] : []
  form.is_active = row ? row.is_active : true
  webhookUrl.value = row?.config?.url ?? ''
  recipientsText.value = (row?.config?.recipients ?? []).join('\n')
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写渠道名称')
  const config: { recipients?: string[]; url?: string } =
    form.type === 'email'
      ? { recipients: recipientsText.value.split('\n').map((s) => s.trim()).filter(Boolean) }
      : { url: webhookUrl.value.trim() }
  if (form.type === 'email' && !config.recipients?.length) return ElMessage.warning('请至少填写一个收件邮箱')
  if (form.type !== 'email' && !config.url) return ElMessage.warning('请填写 webhook 地址')
  if (!form.events.length) return ElMessage.warning('请至少订阅一个事件')
  saving.value = true
  try {
    const body = { name: form.name.trim(), type: form.type, config, events: form.events, is_active: form.is_active }
    if (editing.value && editId.value) await client.put(`/notify-channels/${editId.value}`, body)
    else await client.post('/notify-channels', body)
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function toggleActive(row: NotifyChannel) {
  await client.post(`/notify-channels/${row.id}/${row.is_active ? 'pause' : 'resume'}`)
  ElMessage.success(row.is_active ? '已暂停' : '已恢复')
  await load()
}

async function testSend(row: NotifyChannel) {
  testing.value = row.id
  try {
    const { data } = await client.post<NotifyTestResult>(`/notify-channels/${row.id}/test`)
    if (data.status === 'success') ElMessage.success(`测试通知已送达（投递 #${data.delivery_id}）`)
    else ElMessage.warning(`测试通知发送失败：${data.error || '未知错误'}（投递 #${data.delivery_id}）`)
    await loadDeliveries(1)
  } finally {
    testing.value = null
  }
}

async function remove(id: number) {
  await client.delete(`/notify-channels/${id}`)
  ElMessage.success('删除成功')
  await load()
}

onMounted(async () => {
  await auth.fetchMeta()
  await load()
})
</script>
