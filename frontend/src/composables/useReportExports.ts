import { onBeforeUnmount, ref } from 'vue'

import type { ExportFormat, ExportJob, Report } from '../types'
import { useExportJobs } from './useExportJobs'

/**
 * 报告导出任务管理（工单流程抽屉使用，审计 E-1 从 PlanWorkflowDrawer.vue 抽出）。
 *
 * 职责：每个报告的导出历史列表与展开态、提交导出后轮询至完成、下载与删除导出记录。
 * 提交/下载等单任务能力复用 `useExportJobs`，本 composable 只维护「多报告视图态 + 轮询」。
 *
 * @param getSystemName 取当前系统名，用于导出文件名兜底（抽屉内 plan 可能尚未加载）
 */
export function useReportExports(getSystemName: () => string) {
  const { fetchJobs, submitExport, downloadJob, removeExportJob: deleteExportJob } = useExportJobs()

  const exportJobs = ref<Record<number, ExportJob[]>>({})
  const exporting = ref<Record<number, string>>({})
  // 当前展开导出历史的报告 ID（点击箭头展示该报告的导出版本列表）
  const expandedExportId = ref<number | null>(null)
  let pollTimer: number | undefined

  async function loadJobs(reportId: number) {
    exportJobs.value[reportId] = await fetchJobs(reportId)
    return exportJobs.value[reportId]
  }

  // 展开/收起报告的导出历史版本列表；首次展开时懒加载导出记录
  async function toggleExportList(r: Report) {
    if (expandedExportId.value === r.id) {
      expandedExportId.value = null
      return
    }
    expandedExportId.value = r.id
    if (!exportJobs.value[r.id]?.length) {
      await loadJobs(r.id)
    }
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer)
      pollTimer = undefined
    }
  }

  function pollJobs(reportId: number) {
    stopPolling()
    let ticks = 0
    pollTimer = window.setInterval(async () => {
      ticks += 1
      const jobs = await loadJobs(reportId)
      const pending = jobs.some((j) => j.status !== 'done' && j.status !== 'failed')
      if (!pending || ticks >= 30) stopPolling()
    }, 2000)
  }

  async function doExport(r: Report, fmt: ExportFormat) {
    exporting.value[r.id] = fmt
    try {
      const ok = await submitExport(r.id, fmt, r.title || getSystemName() || 'report')
      if (ok) {
        await loadJobs(r.id)
        pollJobs(r.id)
      }
    } finally {
      delete exporting.value[r.id]
    }
  }

  function download(job: ExportJob) {
    downloadJob(job, getSystemName() || 'report')
  }

  async function removeExportJob(r: Report, job: ExportJob) {
    await deleteExportJob(job.id)
    exportJobs.value[r.id] = (exportJobs.value[r.id] || []).filter((j) => j.id !== job.id)
  }

  /** 抽屉打开时重置临时态（导出历史按需求重新拉取） */
  function resetExportState() {
    stopPolling()
    exportJobs.value = {}
    expandedExportId.value = null
  }

  /** 报告被删除后回收其导出记录与展开态（由报告动作回调触发） */
  function dropReport(reportId: number) {
    delete exportJobs.value[reportId]
    if (expandedExportId.value === reportId) expandedExportId.value = null
  }

  onBeforeUnmount(stopPolling)

  return {
    exportJobs,
    exporting,
    expandedExportId,
    loadJobs,
    toggleExportList,
    stopPolling,
    pollJobs,
    doExport,
    download,
    removeExportJob,
    resetExportState,
    dropReport,
  }
}
