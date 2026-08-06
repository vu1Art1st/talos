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
    <el-button type="primary" plain @click="addVisible = true">
      <el-icon class="mr-1"><Plus /></el-icon>新增复测记录
    </el-button>
    <slot name="actions" />
  </div>

  <el-dialog v-model="addVisible" title="新增复测记录" width="640px">
    <div class="text-sm font-medium text-gray-600 mb-2">漏洞修复详情</div>
    <RichEditor v-model="addForm.content_html"
                @update:json="(j: any) => (addForm.content_json = j)" />
    <div class="mt-3">
      <div class="text-sm font-medium text-gray-600 mb-2">复测结论</div>
      <el-select v-model="addForm.status" clearable placeholder="可选：不调整漏洞状态" class="w-full">
        <el-option label="复测未修复" :value="50" />
        <el-option label="已修复" :value="60" />
      </el-select>
      <div class="text-xs text-gray-400 mt-1">
        选择结论将同步调整漏洞状态（须处于复测中，且必须先填写复测详情）
      </div>
    </div>
    <template #footer>
      <el-button @click="addVisible = false">取消</el-button>
      <el-button type="primary" :loading="adding" @click="submitAdd">确定新增</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import client from '../api/client'
import RichEditor from './RichEditor.vue'

// 复测记录增删改面板：供独立复测页（VulnRetest）与测试计划流程抽屉复用。
// 新增复测记录时可一并选择复测结论（复测未修复/已修复），保存时同步调整漏洞状态。
const props = defineProps<{ vulId: number }>()
const emit = defineEmits<{ (e: 'changed', count: number): void }>()

const records = ref<any[]>([])
const adding = ref(false)
const savingId = ref<number | null>(null)
const addVisible = ref(false)
const addForm = reactive<{ content_html: string; content_json: any; status: number | null }>({
  content_html: '',
  content_json: null,
  status: null,
})

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

async function load() {
  const { data } = await client.get(`/vulns/${props.vulId}/retests`)
  records.value = data
}

// 新增复测记录：填写复测详情并可选择复测结论，一并调整漏洞状态
async function submitAdd() {
  // 复测结论（复测未修复/已修复）强制要求先填写复测详情
  if (addForm.status !== null && !(addForm.content_html || '').trim()) {
    ElMessage.warning('选择复测结论前请先填写复测详情')
    return
  }
  adding.value = true
  try {
    const { data } = await client.post(`/vulns/${props.vulId}/retests`, {
      content_html: addForm.content_html || '',
      content_json: addForm.content_json ?? null,
      status: addForm.status,
    })
    records.value.push(data)
    addVisible.value = false
    addForm.content_html = ''
    addForm.content_json = null
    addForm.status = null
    ElMessage.success('复测记录已新增')
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
