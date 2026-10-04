// 报告导出任务：重复导出确认、任务提交、文件下载（含目录域提示）、记录删除。
// 报告列表 / 报告编辑器 / 工单流程抽屉三处共用；各处的任务列表存储结构不同，留在调用方。
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ElMessageBoxOptions } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'
import type {
  BatchExportCheckResult,
  ExportCheckResult,
  ExportFormat,
  ExportJob,
  ExportMissingField,
} from '../types'
import { saveBlob, saveReportBlob } from '../utils/download'

// 导出记录类型上提到 src/types（审计 E-5）：本文件改为转出，保证「单一来源」
export type { ExportJob }

const MISSING_FIELD_LABELS: Record<ExportMissingField, string> = {
  author: '报告作者',
  test_period: '测试周期',
  target_ip: '被测系统IP',
  test_account: '被测测试账号',
}

function missingFieldText(fields: ExportMissingField[] | undefined): string {
  return (fields ?? []).map((field) => MISSING_FIELD_LABELS[field] ?? field).join('、')
}

function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char] ?? char))
}

export function useExportJobs() {
  /**
   * 拉取指定报告的导出记录（调用方自行决定缓存结构）。
   * 该接口被报告编辑器 / 工单抽屉以 2s 间隔轮询，故声明 skipErrorPage：
   * 失败时只留轻提示，不用全屏错误页打断正在进行的编辑。
   */
  async function fetchJobs(reportId: number | string): Promise<ExportJob[]> {
    const { data } = await client.get(`/reports/${reportId}/exports`, { meta: { skipErrorPage: true } })
    return data
  }

  async function fetchExportCheck(
    reportId: number | string,
    fmt: ExportFormat,
  ): Promise<ExportCheckResult | null> {
    try {
      const { data } = await client.post<ExportCheckResult>(`/reports/${reportId}/export-check`, { fmt })
      return data
    } catch {
      // 检查接口异常时不阻断导出（与既有重复导出检查口径一致）
      return null
    }
  }

  /** 空字段提醒：确认后仍继续导出。 */
  async function confirmMissingFields(
    data: ExportCheckResult,
    fallbackTitle: string,
  ): Promise<boolean> {
    if (!data.missing_fields?.length) return true
    const fields = missingFieldText(data.missing_fields)
    const message =
      `<div>《${escapeHtml(data.report_title || fallbackTitle)}》以下信息为空，请补充后再导出报告：</div>` +
      `<div style="margin-top: 8px;">· ${escapeHtml(fields)}</div>` +
      `<div style="margin-top: 12px; color: var(--el-text-color-secondary);">如仍需导出，可继续。</div>`
    return await ElMessageBox.confirm(message, '报告信息不完整', {
      confirmButtonText: '仍要导出',
      cancelButtonText: '返回补充',
      type: 'warning',
      width: 460,
      dangerouslyUseHTMLString: true,
    } as ElMessageBoxOptions).then(() => true).catch(() => false)
  }

  async function confirmDuplicateData(
    data: ExportCheckResult,
    fmt: ExportFormat,
    fallbackTitle: string,
  ): Promise<boolean> {
    if (!data.duplicate) return true
    const statusName = data.last_status === 'done' ? '已完成' : data.last_status || ''
    const sizeText = data.last_file_size != null ? `（${(data.last_file_size / 1024).toFixed(1)} KB）` : ''
    const message =
      `检测到该报告已有相同的导出记录：\n` +
      `· 报告：《${data.report_title || fallbackTitle}》\n` +
      `· 导出格式：${(data.fmt || fmt).toUpperCase()}\n` +
      `· 导出版本：v${data.last_version ?? ''}\n` +
      `· 已存在记录：${dayjs(data.last_time).format('YYYY-MM-DD HH:mm:ss')}（${statusName}）\n` +
      `· 导出文件：${data.last_file_name || '-'}${sizeText}\n\n` +
      `是否仍要继续导出？`
    return await ElMessageBox.confirm(message, '检测到重复导出', {
      confirmButtonText: '继续导出',
      cancelButtonText: '取消',
      type: 'warning',
      // Element Plus 运行时支持 width，但该版本的 ElMessageBoxOptions 未声明该字段（故断言）
      width: 460,
    } as ElMessageBoxOptions).then(() => true).catch(() => false)
  }

  /** 重复导出检查：与最近一次同格式成功导出完全一致时弹确认；返回是否继续 */
  async function confirmDuplicateExport(
    reportId: number | string,
    fmt: ExportFormat,
    fallbackTitle: string,
  ): Promise<boolean> {
    const data = await fetchExportCheck(reportId, fmt)
    return data ? confirmDuplicateData(data, fmt, fallbackTitle) : true
  }

  /** 提交单个导出任务（含空字段与重复导出确认）；返回是否已提交 */
  async function submitExport(
    reportId: number | string,
    fmt: ExportFormat,
    fallbackTitle: string,
  ): Promise<boolean> {
    const check = await fetchExportCheck(reportId, fmt)
    if (check) {
      if (!(await confirmMissingFields(check, fallbackTitle))) return false
      if (!(await confirmDuplicateData(check, fmt, fallbackTitle))) return false
    }
    await client.post(`/reports/${reportId}/export`, { fmt })
    ElMessage.success('导出任务已提交，生成完成后可在导出记录中下载')
    return true
  }

  /** 批量导出前汇总空字段并弹一次确认；接口异常时不阻断导出。 */
  async function confirmBatchExportWarnings(reportIds: number[]): Promise<boolean> {
    try {
      const { data } = await client.post<BatchExportCheckResult[]>('/reports/batch-export-check', {
        report_ids: reportIds,
      })
      const warnings = data.filter((item) => item.missing_fields?.length)
      if (!warnings.length) return true
      const lines = warnings.map(
        (item) => `· 《${escapeHtml(item.title || item.report_id)}》：${escapeHtml(missingFieldText(item.missing_fields))}`,
      )
      const message =
        `<div>以下报告存在待补充信息，请补充后再导出报告：</div>` +
        `<div style="margin-top: 8px;">${lines.join('<br/>')}</div>` +
        `<div style="margin-top: 12px; color: var(--el-text-color-secondary);">如仍需导出，可继续。</div>`
      return await ElMessageBox.confirm(message, '报告信息不完整', {
        confirmButtonText: '仍要导出',
        cancelButtonText: '返回补充',
        type: 'warning',
        width: 520,
        dangerouslyUseHTMLString: true,
      } as ElMessageBoxOptions).then(() => true).catch(() => false)
    } catch {
      return true
    }
  }

  /** 下载导出文件（带鉴权）；docx 目录域为占位时提示手动更新域 */
  async function downloadJob(job: ExportJob, fallbackTitle = 'report'): Promise<void> {
    const resp = await client.get(`/reports/exports/${job.id}/download`, { responseType: 'blob' })
    saveReportBlob(resp.data, job, fallbackTitle)
  }

  /** 删除导出记录 */
  async function removeExportJob(jobId: number): Promise<void> {
    await client.delete(`/reports/exports/${jobId}`)
    ElMessage.success('导出记录已删除')
  }

  /** 批量下载已完成任务的 zip */
  async function downloadZip(jobIds: string): Promise<void> {
    const resp = await client.get('/reports/batch-download', { params: { job_ids: jobIds }, responseType: 'blob' })
    saveBlob(resp.data, '测试报告批量下载.zip')
  }

  return {
    fetchJobs,
    confirmDuplicateExport,
    submitExport,
    confirmBatchExportWarnings,
    downloadJob,
    removeExportJob,
    downloadZip,
  }
}
