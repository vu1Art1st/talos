<template>
  <el-dialog v-model="visible" :title="title" width="80%" top="4vh" destroy-on-close @closed="cleanup">
    <div v-loading="loading" element-loading-text="正在生成预览…" class="h-[78vh]">
      <iframe v-if="blobUrl" :src="blobUrl" class="w-full h-full border-0" />
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import client from '../api/client'

const visible = ref(false)
const loading = ref(false)
const blobUrl = ref('')
const title = ref('文件预览')

/** 打开预览：url 为返回 inline PDF 的接口地址（走 axios 以携带鉴权头） */
async function open(url: string, name = '文件预览') {
  title.value = name
  visible.value = true
  loading.value = true
  try {
    const { data } = await client.get(url, { responseType: 'blob' })
    blobUrl.value = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
  } catch {
    ElMessage.error('预览加载失败，请确认转换服务可用')
    visible.value = false
  } finally {
    loading.value = false
  }
}

function cleanup() {
  if (blobUrl.value) {
    URL.revokeObjectURL(blobUrl.value)
    blobUrl.value = ''
  }
}

defineExpose({ open })
</script>
