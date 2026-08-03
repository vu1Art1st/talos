<template>
  <el-empty v-if="!records.length" description="暂无复测记录，点击下方按钮新增" :image-size="80" />

  <el-card v-for="(rec, i) in records" :key="rec.id" shadow="never" class="!rounded-lg mb-4">
    <template #header>
      <div class="flex items-center gap-2">
        <span class="font-medium">复测记录 #{{ i + 1 }}</span>
        <span class="text-xs text-gray-400">{{ rec.username }} · {{ fmt(rec.create_time) }}</span>
        <div class="flex-1" />
        <el-button size="small" type="primary" :loading="savingId === rec.id" @click="saveRecord(rec)">
          保存
        </el-button>
        <el-popconfirm title="确认删除该复测记录？" @confirm="removeRecord(rec)">
          <template #reference>
            <el-button size="small" type="danger" plain>删除</el-button>
          </template>
        </el-popconfirm>
      </div>
    </template>
    <div class="text-sm font-medium text-gray-600 mb-2">漏洞修复</div>
    <RichEditor v-model="rec.content_html"
                @update:json="(j: any) => (rec.content_json = j)" />
  </el-card>

  <div class="flex items-center gap-2">
    <el-button type="primary" plain :loading="adding" @click="addRecord">
      <el-icon class="mr-1"><Plus /></el-icon>新增复测记录
    </el-button>
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import client from '../api/client'
import RichEditor from './RichEditor.vue'

// 复测记录增删改面板：供独立复测页（VulnRetest）与测试计划流程抽屉复用。
const props = defineProps<{ vulId: number }>()
const emit = defineEmits<{ (e: 'changed', count: number): void }>()

const records = ref<any[]>([])
const adding = ref(false)
const savingId = ref<number | null>(null)

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

async function load() {
  const { data } = await client.get(`/vulns/${props.vulId}/retests`)
  records.value = data
}

// 新增复测记录：后端创建空记录后追加到列表，生成新的富文本编辑框
async function addRecord() {
  adding.value = true
  try {
    const { data } = await client.post(`/vulns/${props.vulId}/retests`, { content_html: '', content_json: null })
    records.value.push(data)
    ElMessage.success('已新增复测记录，请填写漏洞修复内容')
    emit('changed', records.value.length)
  } finally {
    adding.value = false
  }
}

async function saveRecord(rec: any) {
  savingId.value = rec.id
  try {
    const { data } = await client.put(`/vulns/${props.vulId}/retests/${rec.id}`, {
      content_html: rec.content_html || '',
      content_json: rec.content_json ?? null,
    })
    Object.assign(rec, data)
    ElMessage.success('复测记录已保存')
    emit('changed', records.value.length)
  } finally {
    savingId.value = null
  }
}

async function removeRecord(rec: any) {
  await client.delete(`/vulns/${props.vulId}/retests/${rec.id}`)
  records.value = records.value.filter((r) => r.id !== rec.id)
  ElMessage.success('复测记录已删除')
  emit('changed', records.value.length)
}

defineExpose({ recordCount: () => records.value.length })

onMounted(load)
</script>
