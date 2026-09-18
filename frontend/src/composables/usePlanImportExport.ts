import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import client from '../api/client'
import type { QueryParams } from '../types'
import { saveBlob } from '../utils/download'

interface PlanImportExportOptions {
  /** 取当前筛选参数（导出与列表同口径） */
  getFilterParams: () => QueryParams
  /** 导入成功后的重载（列表回到首页 + 刷新统计） */
  onImported: () => Promise<unknown>
}

/**
 * 工单列表「导入导出」下拉的三种操作（审计 E-2 从 views/TestingPlanList.vue 抽出）。
 *
 * 覆盖：导出 Excel、下载导入模板、导入 Excel（含失败明细弹窗）。
 * 下拉命令分发与隐藏文件选择器回调一并收在此处，模板只保留一个 `@command` 与一个 `@change`。
 */
export function usePlanImportExport(opts: PlanImportExportOptions) {
  const importing = ref(false)
  const importInputRef = ref<HTMLInputElement>()

  async function exportExcel() {
    const { data } = await client.get('/testing-plans/export', {
      params: opts.getFilterParams(), responseType: 'blob',
    })
    saveBlob(data, '渗透测试工单导出.xlsx')
  }

  async function downloadTemplate() {
    const { data } = await client.get('/testing-plans/import/template', { responseType: 'blob' })
    saveBlob(data, '渗透测试工单导入模板.xlsx')
  }

  async function doImport(options: { file: File }) {
    importing.value = true
    try {
      const fd = new FormData()
      fd.append('file', options.file)
      const { data } = await client.post('/testing-plans/import', fd)
      if (data.failed > 0) {
        await ElMessageBox.alert(
          `共 ${data.total} 行，新增 ${data.created} 行，更新 ${data.updated} 行，失败 ${data.failed} 行：<br/>${data.errors.join('<br/>')}`,
          '导入结果', { dangerouslyUseHTMLString: true },
        )
      } else {
        ElMessage.success(`导入完成：新增 ${data.created} 条，更新 ${data.updated} 条`)
      }
      await opts.onImported()
    } finally {
      importing.value = false
    }
  }

  /** 下拉命令分发：分别对应「导入模板下载 / 导入 Excel / 导出 Excel」 */
  function onImportExport(command: string) {
    if (command === 'template') downloadTemplate()
    else if (command === 'export') exportExcel()
    else if (command === 'import') importInputRef.value?.click()
  }

  /** 隐藏文件选择器触发后走导入逻辑（沿用 el-upload 的 http-request 入参结构 { file }） */
  function onImportFileChange(e: Event) {
    const input = e.target as HTMLInputElement
    const file = input.files?.[0]
    if (file) doImport({ file })
    input.value = ''
  }

  return {
    importing,
    importInputRef,
    exportExcel,
    downloadTemplate,
    doImport,
    onImportExport,
    onImportFileChange,
  }
}
