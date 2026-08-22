// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const getMock = vi.fn()
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import RemoteTestingList from '../RemoteTestingList.vue'

describe('RemoteTestingList 视图', () => {
  beforeEach(() => {
    getMock.mockReset()
    getMock.mockResolvedValue({ data: { items: [], total: 0 } })
  })

  // 回归：2.0.2 重构后 onMounted 未从 vue 导入，setup 阶段抛 ReferenceError 导致整页白屏
  it('挂载不抛错，并在首屏请求列表接口', async () => {
    const wrapper = mount(RemoteTestingList, {
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(getMock).toHaveBeenCalledWith(
      '/remote-testings',
      expect.objectContaining({ params: expect.objectContaining({ page: 1, size: 20 }) }),
    )
    expect(wrapper.text()).toContain('新增远程检测')
    wrapper.unmount()
  })
})
