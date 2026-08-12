<template>
  <div>
    <!-- 无记录但漏洞存在历史复测内容（报告「复测处理」直接写入 retest_html）时只读展示 -->
    <el-card v-if="!records.length && fallbackHtml" shadow="never" class="!rounded-lg mb-4">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="font-medium">复测详情</span>
          <span class="text-xs text-gray-400">历史复测内容（来自报告复测处理）</span>
        </div>
      </template>
      <div class="text-sm prose max-w-none" v-html="safeHtml(fallbackHtml)" />
    </el-card>

    <el-empty v-if="!records.length && !fallbackHtml" description="暂无复测记录，点击下方按钮新增" :image-size="80" />

    <el-card v-for="(rec, i) in records" :key="rec.id" shadow="never" class="!rounded-lg mb-4">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="font-medium">{{ titles[i] }}</span>
          <span class="text-xs text-gray-400">{{ rec.username }} · {{ fmtDateTime(rec.create_time) }}</span>
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
        <el-button type="primary" :loading="adding" @click="submitAdd">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import client from '../api/client'
import RichEditor from './RichEditor.vue'
import { fmtDateTime } from '../utils/format'
import { safeHtml } from '../utils/html'

// 复测记录增删改面板：供独立复测页（VulnRetest）与测试计划流程抽屉复用。
// 新增复测记录时可一并选择复测结论（复测未修复/已修复），保存时同步调整漏洞状态。
const props = defineProps<{ vulId: number }>()
const emit = defineEmits<{ (e: 'changed', count: number): void }>()

const records = ref<any[]>([])
const adding = ref(false)
const savingId = ref<number | null>(null)
const addVisible = ref(false)
// 无记录时回退展示漏洞 retest_html（报告「复测处理」写入的历史复测内容）
const fallbackHtml = ref('')
const addForm = reactive<{ content_html: string; content_json: any; status: number | null }>({
  content_html: '',
  content_json: null,
  status: null,
})

// 标题按记录创建日期生成：复测记录yymmdd，同日多条依次追加 -1、-2 后缀
const titles = computed(() => {
  const dayCount: Record<string, number> = {}
  return records.value.map((r: any) => {
    const key = r.create_time ? dayjs(r.create_time).format('YYMMDD') : ''
    const n = dayCount[key] ?? 0
    dayCount[key] = n + 1
    return n === 0 ? `复测记录${key}` : `复测记录${key}-${n}`
  })
})

async function load() {
  const { data } = await client.get(`/vulns/${props.vulId}/retests`)
  records.value = data
  // 记录为空时回退读取漏洞 retest_html，保证报告「复测处理」填写的复测内容可见
  if (!data.length) {
    try {
      const vul = await client.get(`/vulns/${props.vulId}`)
      fallbackHtml.value = vul.data?.retest_html || ''
    } catch {
      fallbackHtml.value = ''
    }
  } else {
    fallbackHtml.value = ''
  }
}

// 组件实例可能被 el-table 展开行复用（切换漏洞行），监听 vulId 变化时重新加载
watch(() => props.vulId, load, { immediate: true })

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
</script>
