import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useExportJobs } from '../useExportJobs'
import type { ExportJob } from '../useExportJobs'

// mock element-plus：确认框行为由用例内定义，成功提示记录调用
const confirmMock = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn() },
  ElMessageBox: { confirm: (...args: unknown[]) => confirmMock(...args) },
}))

// mock 下载工具：验证调用参数即可，不触发真实浏览器下载
const startUrlDownloadMock = vi.fn()
vi.mock('../../utils/download', () => ({
  startUrlDownload: (...args: unknown[]) => startUrlDownloadMock(...args),
}))

const showTocNoticeMock = vi.fn()
vi.mock('../../utils/tocNotice', () => ({
  showTocNotice: () => showTocNoticeMock(),
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
  it('fetchJobs 请求报告导出记录并透传列表（轮询请求声明错误页豁免）', async () => {
    getMock.mockResolvedValueOnce({ data: [{ id: 3, fmt: 'docx', status: 'done' }] })
    const jobs = await useExportJobs().fetchJobs(9)
    expect(getMock).toHaveBeenCalledWith('/reports/9/exports', { meta: { skipErrorPage: true } })
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

  it('submitExport 缺项提醒可继续，返回补充时中止', async () => {
    postMock.mockResolvedValueOnce({
      data: { duplicate: false, missing_fields: ['author', 'target_ip'] },
    })
    confirmMock.mockResolvedValueOnce(undefined)
    postMock.mockResolvedValueOnce({ data: {} })
    expect(await useExportJobs().submitExport(9, 'docx', '标题')).toBe(true)
    expect(String(confirmMock.mock.calls[0][0])).toContain('报告作者、被测系统IP')
    expect(String(confirmMock.mock.calls[0][0])).toContain('margin-top: 12px')
    expect(postMock).toHaveBeenLastCalledWith('/reports/9/export', { fmt: 'docx' })

    vi.clearAllMocks()
    postMock.mockResolvedValueOnce({
      data: { duplicate: false, missing_fields: ['test_account'] },
    })
    confirmMock.mockRejectedValueOnce(new Error('cancel'))
    expect(await useExportJobs().submitExport(9, 'docx', '标题')).toBe(false)
    expect(postMock).toHaveBeenCalledTimes(1)
  })

  it('submitExport 缺项与重复导出同时命中时依次确认，任一步取消均不提交', async () => {
    postMock.mockResolvedValueOnce({
      data: { duplicate: true, missing_fields: ['test_period'], last_status: 'done' },
    })
    confirmMock.mockResolvedValueOnce(undefined)
    confirmMock.mockRejectedValueOnce(new Error('cancel'))
    expect(await useExportJobs().submitExport(9, 'docx', '标题')).toBe(false)
    expect(confirmMock).toHaveBeenCalledTimes(2)
    expect(postMock).toHaveBeenCalledTimes(1)
  })

  it('confirmBatchExportWarnings 汇总报告缺项并在确认后放行', async () => {
    postMock.mockResolvedValueOnce({
      data: [
        { report_id: 1, title: '报告一', missing_fields: ['author'] },
        { report_id: 2, title: '报告二', missing_fields: ['test_account'] },
      ],
    })
    confirmMock.mockResolvedValueOnce(undefined)
    expect(await useExportJobs().confirmBatchExportWarnings([1, 2])).toBe(true)
    const message = String(confirmMock.mock.calls[0][0])
    expect(message).toContain('《报告一》：报告作者')
    expect(message).toContain('《报告二》：被测测试账号')

    postMock.mockResolvedValueOnce({
      data: [{ report_id: 1, title: '报告一', missing_fields: ['target_ip'] }],
    })
    confirmMock.mockRejectedValueOnce(new Error('cancel'))
    expect(await useExportJobs().confirmBatchExportWarnings([1])).toBe(false)
  })

  it('submitExport 取消时不提交任务；确认后提交并提示', async () => {
    postMock.mockResolvedValueOnce({ data: { duplicate: true } })
    confirmMock.mockRejectedValueOnce(new Error('cancel'))
    expect(await useExportJobs().submitExport(9, 'docx', '标题')).toBe(false)
    expect(postMock).toHaveBeenCalledTimes(1) // 仅 export-check，未提交导出

    postMock.mockResolvedValueOnce({ data: { duplicate: false } })
    postMock.mockResolvedValueOnce({ data: {} })
    expect(await useExportJobs().submitExport(9, 'docx', '标题')).toBe(true)
    expect(postMock).toHaveBeenLastCalledWith('/reports/9/export', { fmt: 'docx' })
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('downloadJob 申请短时凭证后触发浏览器原生下载', async () => {
    postMock.mockResolvedValueOnce({
      data: { url: '/api/v1/reports/downloads/abc', filename: '报告.docx', expires_in: 300 },
    })
    const job: ExportJob = { id: 5, report_id: 9, fmt: 'docx', status: 'done' }
    await useExportJobs().downloadJob(job, '兜底标题')
    expect(postMock).toHaveBeenCalledWith('/reports/download-tickets', { job_ids: [5] })
    expect(startUrlDownloadMock).toHaveBeenCalledWith('/api/v1/reports/downloads/abc', '报告.docx')
    expect(showTocNoticeMock).toHaveBeenCalledOnce()
  })

  it('downloadZip 将任务 ID 转为批量凭证下载', async () => {
    postMock.mockResolvedValueOnce({
      data: { url: '/api/v1/reports/downloads/batch', filename: '测试报告批量下载.zip', expires_in: 300 },
    })
    await useExportJobs().downloadZip('5, 7,invalid')
    expect(postMock).toHaveBeenCalledWith('/reports/download-tickets', { job_ids: [5, 7] })
    expect(startUrlDownloadMock).toHaveBeenCalledWith(
      '/api/v1/reports/downloads/batch',
      '测试报告批量下载.zip',
    )
  })
})
