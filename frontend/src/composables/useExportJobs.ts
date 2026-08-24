// 报告导出任务：重复导出确认、任务提交、文件下载（含目录域提示）、记录删除。
// 报告列表 / 报告编辑器 / 工单流程抽屉三处共用；各处的任务列表存储结构不同，留在调用方。
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import client from '../api/client'
import { saveBlob, saveReportBlob } from '../utils/download'

export interface ExportJob {
  id: number
  report_id: number
  title?: string | null
  fmt: string
  status: string
  version?: number
  toc_auto_updated?: boolean
  file_size?: number | null
  file_name?: string | null
  create_time?: string
  finish_time?: string
  has_file?: boolean
}

export function useExportJobs() {
  /** 拉取指定报告的导出记录（调用方自行决定缓存结构） */
  async function fetchJobs(reportId: number | string): Promise<ExportJob[]> {
    const { data } = await client.get(`/reports/${reportId}/exports`)
    return data
  }

  /** 重复导出检查：与最近一次同格式成功导出完全一致时弹确认；返回是否继续 */
  async function confirmDuplicateExport(reportId: number | string, fmt: string, fallbackTitle: string): Promise<boolean> {
    try {
      const { data } = await client.post(`/reports/${reportId}/export-check`, { fmt })
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
        width: 460,
      }).then(() => true).catch(() => false)
    } catch {
      // 检查接口异常时不阻断导出
      return true
    }
  }

  /** 提交导出任务（含重复确认）；返回是否已提交 */
  async function submitExport(reportId: number | string, fmt: string, fallbackTitle: string): Promise<boolean> {
    if (!(await confirmDuplicateExport(reportId, fmt, fallbackTitle))) return false
    await client.post(`/reports/${reportId}/export`, { fmt })
    ElMessage.success('导出任务已提交，生成完成后可在导出记录中下载')
    return true
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

  return { fetchJobs, confirmDuplicateExport, submitExport, downloadJob, removeExportJob, downloadZip }
}
