<template>
  <el-card shadow="never" class="!rounded-lg" v-loading="loading">
    <template #header>
      <div class="flex items-center gap-2">
        <span class="text-base font-semibold">通知渠道</span>
        <span class="text-sm text-gray-400">漏洞创建 / 工单认领 / 状态流转 / 复测完成事件推送到企业微信、钉钉或邮箱</span>
        <div class="flex-1" />
        <el-button type="primary" @click="openDialog()">
          <el-icon class="mr-1"><Plus /></el-icon>新建渠道
        </el-button>
      </div>
    </template>

    <el-table :data="items" stripe>
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column label="类型" width="110">
        <template #default="{ row }">
          <span class="tl-tag" :style="softStyle(typeColor(row.type))">{{ typeName(row.type) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="订阅事件" min-width="220">
        <template #default="{ row }">
          <div class="flex flex-wrap gap-1">
            <span v-for="e in row.events" :key="e" class="tl-tag" :style="softStyle(STAT_CARD_COLORS.blue)">
              {{ eventName(e) }}
            </span>
            <span v-if="!row.events?.length" class="text-gray-400">未订阅</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="配置" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.type === 'email' ? (row.config?.recipients ?? []).join('、') : row.config?.url }}
        </template>
      </el-table-column>
      <el-table-column label="启用" width="80">
        <template #default="{ row }">
          <el-switch :model-value="row.is_active" @change="(v: any) => toggleActive(row, v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="testSend(row)">测试发送</el-button>
          <el-button size="small" link @click="openDialog(row)">编辑</el-button>
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

    <div class="mt-4 flex justify-end">
      <el-pagination background layout="total, prev, pager, next" :total="total"
                     :page-size="20" :current-page="page" @current-change="load" />
    </div>
  </el-card>

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
import { softStyle, STAT_CARD_COLORS } from '../utils/colors'

const auth = useAuthStore()
const { items, total, page, loading, load } = useListPage('/notify-channels')

const channelTypes = computed<Record<string, string>>(() => (auth.meta as any)?.notify_channel_types ?? {})
const eventDict = computed<Record<string, string>>(() => (auth.meta as any)?.notify_events ?? {})
const typeName = (t: string) => channelTypes.value[t] ?? t
const eventName = (e: string) => eventDict.value[e] ?? e
const typeColor = (t: string) =>
  ({ wecom: STAT_CARD_COLORS.blue, dingtalk: STAT_CARD_COLORS.orange, email: STAT_CARD_COLORS.green })[t] ?? STAT_CARD_COLORS.gray

const dialogVisible = ref(false)
const saving = ref(false)
const editing = ref(false)
const editId = ref<number | null>(null)
const webhookUrl = ref('')
const recipientsText = ref('')
const form = reactive({ name: '', type: 'wecom', events: [] as string[], is_active: true })

function openDialog(row?: any) {
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
  const config =
    form.type === 'email'
      ? { recipients: recipientsText.value.split('\n').map((s) => s.trim()).filter(Boolean) }
      : { url: webhookUrl.value.trim() }
  if (form.type === 'email' && !config.recipients.length) return ElMessage.warning('请至少填写一个收件邮箱')
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

async function toggleActive(row: any, value: boolean) {
  await client.put(`/notify-channels/${row.id}`, {
    name: row.name, type: row.type, config: row.config, events: row.events, is_active: value,
  })
  ElMessage.success(value ? '已启用' : '已停用')
  await load()
}

async function testSend(row: any) {
  const { data } = await client.post(`/notify-channels/${row.id}/test`)
  ElMessage.success(data.msg)
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
