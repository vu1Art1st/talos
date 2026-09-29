import { beforeEach, describe, expect, it, vi } from 'vitest'

const alertMock = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn() },
  ElMessageBox: { alert: (...args: unknown[]) => alertMock(...args) },
}))
vi.mock('../../utils/download', () => ({
  saveBlob: vi.fn(),
}))

const postMock = vi.fn()
vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(),
    post: (...args: unknown[]) => postMock(...args),
  },
}))

import { ElMessage } from 'element-plus'
import { usePlanImportExport } from '../usePlanImportExport'

beforeEach(() => {
  vi.clearAllMocks()
  alertMock.mockResolvedValue(undefined)
})

describe('usePlanImportExport', () => {
  it('无初测报告且人天为 0 时展示非阻断告警并刷新列表', async () => {
    postMock.mockResolvedValue({
      data: {
        total: 1, created: 1, updated: 0, failed: 0, errors: [],
        warnings: ['第2行（零人天工单）：无初测报告且实际人天为 0'],
      },
    })
    const onImported = vi.fn().mockResolvedValue(undefined)
    const { doImport } = usePlanImportExport({
      getFilterParams: () => ({}),
      onImported,
    })

    await doImport({ file: {} as File })

    expect(alertMock).toHaveBeenCalledWith(
      expect.stringContaining('无初测报告且实际人天为 0'),
      '导入完成，存在 0 人天风险',
      expect.objectContaining({ type: 'warning' }),
    )
    expect(onImported).toHaveBeenCalledTimes(1)
  })

  it('无告警时维持成功提示', async () => {
    postMock.mockResolvedValue({
      data: { total: 1, created: 1, updated: 0, failed: 0, errors: [], warnings: [] },
    })
    const { doImport } = usePlanImportExport({
      getFilterParams: () => ({}),
      onImported: vi.fn(),
    })

    await doImport({ file: {} as File })

    expect(ElMessage.success).toHaveBeenCalledWith('导入完成：新增 1 条，更新 0 条')
    expect(alertMock).not.toHaveBeenCalled()
  })
})
