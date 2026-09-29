import { beforeEach, describe, expect, it, vi } from 'vitest'

const alertMock = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn() },
  ElMessageBox: {
    confirm: vi.fn(),
    alert: (...args: unknown[]) => alertMock(...args),
  },
}))

const postMock = vi.fn()
vi.mock('../../api/client', () => ({
  default: {
    post: (...args: unknown[]) => postMock(...args),
    delete: vi.fn(),
  },
}))

import { ElMessage } from 'element-plus'
import { usePlanReports } from '../usePlanReports'

beforeEach(() => {
  vi.clearAllMocks()
  alertMock.mockResolvedValue(undefined)
})

describe('usePlanReports', () => {
  it('无漏洞结项最终人天为 0 时展示非阻断告警', async () => {
    postMock.mockResolvedValue({
      data: { id: 7, warnings: ['工单「T-7」实际人天为 0，请补录或手工修正'] },
    })
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const reports = usePlanReports({
      getPlanId: () => 7,
      getSystemName: () => '测试系统',
      getNoVulConclusion: () => '',
      getVulnIds: () => [],
      onChanged,
    })

    await reports.completeNoVuln()

    expect(alertMock).toHaveBeenCalledWith(
      '工单「T-7」实际人天为 0，请补录或手工修正',
      '实际人天为 0',
      { type: 'warning' },
    )
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(ElMessage.success).not.toHaveBeenCalled()
  })
})
