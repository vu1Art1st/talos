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

// 屏蔽 auth store（其导入链会拉起 router/pinia）：仅需 fetchMeta 返回可用字典结构
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({
    meta: null,
    fetchMeta: vi.fn().mockResolvedValue({ colors: {} }),
    hasPerm: () => true,
  }),
}))

import RemoteTestingList from '../RemoteTestingList.vue'

describe('RemoteTestingList 视图', () => {
  beforeEach(() => {
    getMock.mockReset()
    // /groups 与 /group-members/all 返回数组（AssetFormDialog 挂载时会请求），其余走分页结构
    getMock.mockImplementation((url: string) => {
      if (url === '/groups' || url === '/group-members/all') return Promise.resolve({ data: [] })
      if (url === '/meta') return Promise.resolve({ data: { colors: {} } })
      return Promise.resolve({ data: { items: [], total: 0 } })
    })
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

  // 2026-09-11 需求：系统名称后新增「部门」列与「资产归属」列；漏洞名称改为关联漏洞（可新增）
  it('列表包含部门/资产归属列，新增弹窗提供「新增漏洞」录入', async () => {
    const wrapper = mount(RemoteTestingList, {
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    const pageText = wrapper.text()
    expect(pageText).toContain('部门')
    expect(pageText).toContain('资产归属')
    expect(pageText).toContain('漏洞类型')

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增远程检测'))
    expect(addBtn).toBeTruthy()
    await addBtn!.trigger('click')
    await flushPromises()

    const dialogText = wrapper.text() + (document.body.textContent ?? '')
    expect(dialogText).toContain('关联资产')
    expect(dialogText).toContain('新增漏洞')
    wrapper.unmount()
  })
})
