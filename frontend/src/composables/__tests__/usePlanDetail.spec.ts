import { beforeEach, describe, expect, it, vi } from 'vitest'

const getMock = vi.fn()
const postMock = vi.fn()
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() } }))
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}))
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({ fetchMeta: vi.fn() }),
}))

import { ElMessage } from 'element-plus'
import { usePlanDetail } from '../usePlanDetail'

beforeEach(() => {
  vi.clearAllMocks()
  getMock.mockImplementation(async (url: string) => {
    if (url === '/testing-plans/7') {
      return { data: { id: 7, system_name: '退领测试系统', status: 10, testers: [], reports: [] } }
    }
    if (url === '/vulns') return { data: { items: [], total: 0 } }
    return { data: {} }
  })
})

describe('usePlanDetail', () => {
  it('最后一名测试人员退出并回退状态时使用明确的成功提示', async () => {
    postMock.mockResolvedValue({ data: { id: 7, status: 10 } })
    const detail = usePlanDetail(() => 7)

    await detail.quit()

    expect(postMock).toHaveBeenCalledWith('/testing-plans/7/quit')
    expect(ElMessage.success).toHaveBeenCalledWith('已退出该计划，状态已回到未测试')
  })

  it('未发生状态回退时保留原退出提示', async () => {
    postMock.mockResolvedValue({ data: { id: 7, status: 20 } })
    const detail = usePlanDetail(() => 7)

    await detail.quit()

    expect(ElMessage.success).toHaveBeenCalledWith('已退出该计划')
  })
})
