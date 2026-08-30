<template>
  <div>
    <!-- 无记录但漏洞存在历史复测内容（报告「复测处理」直接写入 retest_html）时只读展示 -->
    <el-card v-if="!records.length && fallbackHtml" shadow="never" class="mb-4">
      <template #header>
        <div class="flex items-center gap-2">
          <span class="font-medium">复测详情</span>
          <span class="text-xs text-gray-400">历史复测内容（来自报告复测处理）</span>
        </div>
      </template>
      <div class="text-sm prose max-w-none" v-html="safeHtml(fallbackHtml)" />
    </el-card>

    <el-empty v-if="!records.length && !fallbackHtml" description="暂无复测记录，点击下方按钮新增" :image-size="80" />

    <el-card v-for="(rec, i) in records" :key="rec.id" shadow="never" class="mb-4">
      <template #header>
        <div class="flex items-center gap-2">
          <el-input
            v-if="editingTitleId === rec.id"
            v-model="titleDraft"
            size="small"
            class="!w-64"
            placeholder="复测记录标题（留空则按创建日期自动生成）"
            maxlength="255"
            @keyup.enter="confirmEditTitle(rec)"
            @blur="cancelEditTitle"
          />
          <div v-else class="flex items-center gap-2 cursor-pointer group" @click="startEditTitle(rec)">
            <span class="font-medium">{{ titles[i] }}</span>
            <el-icon class="text-gray-300 group-hover:text-primary" :size="13"><EditPen /></el-icon>
          </div>
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

    <el-dialog
             :close-on-click-modal="false" v-model="addVisible" title="新增复测记录" width="640px" append-to-body>
      <el-form ref="addFormRef" :model="addForm" :rules="addRules">
        <div class="mb-3">
          <div class="text-sm font-medium text-gray-600 mb-2">复测标题 <span class="text-xs text-gray-400">（选填，留空按创建日期自动生成）</span></div>
          <el-input v-model="addForm.title" placeholder="如：复测记录250815" maxlength="255" clearable />
        </div>
        <div class="text-sm font-medium text-gray-600 mb-2">漏洞修复详情</div>
        <RichEditor v-model="addForm.content_html"
                    @update:json="(j: any) => (addForm.content_json = j)" />
        <el-form-item prop="status" class="mt-3">
          <div class="w-full">
            <div class="text-sm font-medium text-gray-600 mb-2">复测结论</div>
            <el-select v-model="addForm.status" clearable placeholder="可选：不调整漏洞状态" class="w-full">
              <el-option label="复测未修复" :value="50" />
              <el-option label="已修复" :value="60" />
            </el-select>
            <div class="text-xs text-gray-400 mt-1">
              选择结论将同步调整漏洞状态（须处于复测中，且必须先填写复测详情）
            </div>
          </div>
        </el-form-item>
      </el-form>
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
import type { FormInstance, FormItemRule, FormRules } from 'element-plus'
import { EditPen, Plus } from '@element-plus/icons-vue'
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
// 标题行内编辑状态：正在编辑的记录 id 与草稿值
const editingTitleId = ref<number | null>(null)
const titleDraft = ref('')
const addForm = reactive<{ title: string; content_html: string; content_json: any; status: number | null }>({
  title: '',
  content_html: '',
  content_json: null,
  status: null,
})
const addFormRef = ref<FormInstance>()

// 复测结论（复测未修复/已修复）强制要求先填写复测详情
const requireConclusionDetail: FormItemRule['validator'] = (_rule, value, callback) => {
  if (value !== null && !(addForm.content_html || '').trim()) {
    callback(new Error('选择复测结论前请先填写复测详情'))
  } else {
    callback()
  }
}
const addRules: FormRules = {
  status: [{ validator: requireConclusionDetail }],
}

// 标题优先取自定义 title；为空按创建日期生成：复测记录yymmdd，同日多条依次追加 -1、-2 后缀
const titles = computed(() => {
  const dayCount: Record<string, number> = {}
  return records.value.map((r: any) => {
    if ((r.title || '').trim()) return r.title.trim()
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
  const valid = await addFormRef.value.validate().catch(() => false)
  if (!valid) return
  adding.value = true
  try {
    const { data } = await client.post(`/vulns/${props.vulId}/retests`, {
      title: addForm.title.trim() || null,
      content_html: addForm.content_html || '',
      content_json: addForm.content_json ?? null,
      status: addForm.status,
    })
    records.value.push(data)
    addVisible.value = false
    addForm.title = ''
    addForm.content_html = ''
    addForm.content_json = null
    addForm.status = null
    ElMessage.success('复测记录已新增')
    emit('changed', records.value.length)
  } finally {
    adding.value = false
  }
}

// ---------- 标题行内编辑 ----------
function startEditTitle(rec: any) {
  editingTitleId.value = rec.id
  titleDraft.value = rec.title || ''
}
function cancelEditTitle() {
  editingTitleId.value = null
  titleDraft.value = ''
}
async function confirmEditTitle(rec: any) {
  if (editingTitleId.value !== rec.id) return
  editingTitleId.value = null
  // 标题有改动时才提交；回车保存标题，随后可继续编辑内容
  if (titleDraft.value.trim() === (rec.title || '').trim()) {
    titleDraft.value = ''
    return
  }
  const newTitle = titleDraft.value.trim() || null
  titleDraft.value = ''
  savingId.value = rec.id
  try {
    const { data } = await client.put(`/vulns/${props.vulId}/retests/${rec.id}`, {
      title: newTitle,
      content_html: rec.content_html || '',
      content_json: rec.content_json ?? null,
    })
    Object.assign(rec, data)
    ElMessage.success('复测记录标题已更新')
    emit('changed', records.value.length)
  } finally {
    savingId.value = null
  }
}

async function saveRecord(rec: any) {
  savingId.value = rec.id
  try {
    const { data } = await client.put(`/vulns/${props.vulId}/retests/${rec.id}`, {
      title: rec.title || null,
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
