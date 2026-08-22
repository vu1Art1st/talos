import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useExportJobs } from '../useExportJobs'

// mock element-plus：确认框行为由用例内定义，成功提示记录调用
const confirmMock = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn() },
  ElMessageBox: { confirm: (...args: unknown[]) => confirmMock(...args) },
}))

// mock 下载工具：验证调用参数即可，不触发真实浏览器下载
const saveReportBlobMock = vi.fn()
const saveBlobMock = vi.fn()
vi.mock('../../utils/download', () => ({
  saveBlob: (...args: unknown[]) => saveBlobMock(...args),
  saveReportBlob: (...args: unknown[]) => saveReportBlobMock(...args),
}))

// mock axios client：export-check 结果由用例内定义，其余接口返回空数据
const getMock = vi.fn()
const postMock = vi.fn()
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    delete: vi.fn(),
  },
}))

import { ElMessage } from 'element-plus'

beforeEach(() => {
  vi.clearAllMocks()
  confirmMock.mockResolvedValue(undefined)
})

describe('useExportJobs', () => {
  it('fetchJobs 请求报告导出记录并透传列表', async () => {
    getMock.mockResolvedValueOnce({ data: [{ id: 3, fmt: 'docx', status: 'done' }] })
    const jobs = await useExportJobs().fetchJobs(9)
    expect(getMock).toHaveBeenCalledWith('/reports/9/exports')
    expect(jobs).toHaveLength(1)
  })

  it('confirmDuplicateExport 非重复直接放行，不弹确认框', async () => {
    postMock.mockResolvedValueOnce({ data: { duplicate: false } })
    const ok = await useExportJobs().confirmDuplicateExport(9, 'docx', '标题')
    expect(ok).toBe(true)
    expect(confirmMock).not.toHaveBeenCalled()
  })

  it('confirmDuplicateExport 重复时弹确认：确认继续返回 true，取消返回 false', async () => {
    postMock.mockResolvedValueOnce({ data: { duplicate: true, last_status: 'done' } })
    confirmMock.mockResolvedValueOnce(undefined)
    expect(await useExportJobs().confirmDuplicateExport(9, 'docx', '标题')).toBe(true)

    postMock.mockResolvedValueOnce({ data: { duplicate: true, last_status: 'done' } })
    confirmMock.mockRejectedValueOnce(new Error('cancel'))
    expect(await useExportJobs().confirmDuplicateExport(9, 'docx', '标题')).toBe(false)
  })

  it('confirmDuplicateExport 检查接口异常时不阻断导出（返回 true）', async () => {
    postMock.mockRejectedValueOnce(new Error('500'))
    const ok = await useExportJobs().confirmDuplicateExport(9, 'docx', '标题')
    expect(ok).toBe(true)
  })

  it('submitExport 取消时不提交任务；确认后提交并提示', async () => {
    postMock.mockResolvedValueOnce({ data: { duplicate: true } })
    confirmMock.mockRejectedValueOnce(new Error('cancel'))
    expect(await useExportJobs().submitExport(9, 'pdf', '标题')).toBe(false)
    expect(postMock).toHaveBeenCalledTimes(1) // 仅 export-check，未提交导出

    postMock.mockResolvedValueOnce({ data: { duplicate: false } })
    postMock.mockResolvedValueOnce({ data: {} })
    expect(await useExportJobs().submitExport(9, 'pdf', '标题')).toBe(true)
    expect(postMock).toHaveBeenLastCalledWith('/reports/9/export', { fmt: 'pdf' })
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('downloadJob 以 blob 拉取文件并交给 saveReportBlob', async () => {
    const blob = { size: 1024 }
    getMock.mockResolvedValueOnce({ data: blob })
    const job = { id: 5, report_id: 9, fmt: 'docx', status: 'done' }
    await useExportJobs().downloadJob(job as any, '兜底标题')
    expect(getMock).toHaveBeenCalledWith('/reports/exports/5/download', { responseType: 'blob' })
    expect(saveReportBlobMock).toHaveBeenCalledWith(blob, job, '兜底标题')
  })
})
