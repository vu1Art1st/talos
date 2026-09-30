<template>
  <el-dialog
    v-model="visible"
    :close-on-click-modal="false"
    :title="title"
    width="800px"
    top="4vh"
    destroy-on-close
    append-to-body
    @closed="cleanup"
  >
    <div v-loading="fetching || viewerLoading" element-loading-text="正在加载预览…" class="file-preview-body">
      <FileViewer
        v-if="viewerFile"
        ref="viewerRef"
        :file="viewerFile"
        :options="viewerOptions"
        class="w-full h-full"
        @load-start="onViewerLoadStart"
        @load-complete="onViewerLoadComplete"
        @error="onViewerError"
      />
      <el-empty v-else-if="error" :description="error" :image-size="80" />
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :disabled="!ready || fetching || printing" :loading="printing"
                 @click="printDocument">
        <el-icon class="mr-1"><Printer /></el-icon>打印 / 另存为 PDF
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Printer } from '@element-plus/icons-vue'
import type { FileViewerOptions, FileViewerVue3Handle } from '@file-viewer/vue3'
import '@file-viewer/vue3/dist/file-viewer3.css'
import client from '../api/client'
import { useThemeStore } from '../stores/theme'

const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

// File Viewer 及其 Word renderer 只在首次打开预览时加载。
const FileViewer = defineAsyncComponent(() => import('@file-viewer/vue3').then((mod) => mod.FileViewer))

const theme = useThemeStore()
const visible = ref(false)
const fetching = ref(false)
const viewerLoading = ref(false)
const printing = ref(false)
const ready = ref(false)
const title = ref('文件预览')
const viewerFile = ref<File | null>(null)
const viewerRef = ref<FileViewerVue3Handle | null>(null)
const error = ref('')
let requestSeq = 0
let controller: AbortController | null = null

const viewerOptions = computed<FileViewerOptions>(() => ({
  theme: theme.dark ? 'dark' : 'light',
  toolbar: false,
  styleIsolation: 'shadow',
  docx: {
    visualPagination: true,
    externalLinkPolicy: 'block',
    externalResourcePolicy: 'block',
  },
}))

function docxFilename(name: string): string {
  const value = name.trim() || 'document.docx'
  return value.toLowerCase().endsWith('.docx') ? value : `${value}.docx`
}

function isCanceled(err: unknown): boolean {
  const value = err as { code?: string; name?: string } | null
  return value?.code === 'ERR_CANCELED' || value?.name === 'AbortError'
}

/** 打开预览：url 返回原始 DOCX，经 axios 携带鉴权后交给 File Viewer。 */
async function open(url: string, name = '文件预览') {
  cleanup()
  const seq = ++requestSeq
  controller = new AbortController()
  title.value = name
  visible.value = true
  fetching.value = true
  error.value = ''
  ready.value = false
  viewerFile.value = null

  try {
    const { data } = await client.get<Blob>(url, {
      responseType: 'blob',
      signal: controller.signal,
      meta: { skipErrorPage: true },
    })
    if (seq !== requestSeq || !visible.value) return
    viewerFile.value = new File([data], docxFilename(name), { type: DOCX_MIME })
  } catch (err) {
    if (seq !== requestSeq || isCanceled(err)) return
    error.value = '预览加载失败，请稍后重试'
    ElMessage.error(error.value)
  } finally {
    if (seq === requestSeq) fetching.value = false
  }
}

function onViewerLoadStart() {
  viewerLoading.value = true
  ready.value = false
}

function onViewerLoadComplete() {
  viewerLoading.value = false
  ready.value = true
}

function onViewerError(message: string) {
  viewerLoading.value = false
  ready.value = false
  error.value = message || '文件预览失败'
  viewerFile.value = null
  viewerRef.value = null
}

async function printDocument() {
  if (!viewerRef.value || !ready.value || printing.value) return
  printing.value = true
  try {
    await viewerRef.value.printRenderedHtml()
  } catch {
    ElMessage.error('打印准备失败，请稍后重试')
  } finally {
    printing.value = false
  }
}

function cleanup() {
  requestSeq += 1
  controller?.abort()
  controller = null
  viewerFile.value = null
  viewerRef.value = null
  ready.value = false
  viewerLoading.value = false
  fetching.value = false
  error.value = ''
  title.value = '文件预览'
}

defineExpose({ open })
</script>

<style scoped>
.file-preview-body {
  height: 78vh;
  min-height: 320px;
}
</style>
