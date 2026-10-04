// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())

// RichEditor 依赖 TipTap（jsdom 下重且与本测试无关），用轻量 stub 替代
vi.mock('../../components/RichEditor.vue', () => ({
  default: {
    name: 'RichEditor',
    props: ['modelValue'],
    template: '<div class="rich-stub" />',
  },
}))

// 组件内使用 useRouter 跳转漏洞详情；仅覆盖 hook，保留真实导出避免导入链报错
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRouter: () => ({ push: vi.fn() }) }
})

vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({
    meta: null,
    fetchMeta: vi.fn().mockResolvedValue({ colors: {}, vul_level: {}, vul_type: {} }),
    hasPerm: () => true,
  }),
}))

import SpringActionList from '../SpringActionList.vue'

describe('SpringActionList 视图', () => {
  beforeEach(() => {
    getMock.mockReset()
    getMock.mockImplementation((url: string) => {
      if (url === '/vulns') return Promise.resolve({ data: { items: [], total: 0 } })
      return Promise.resolve({ data: { items: [], total: 0 } })
    })
  })

  it('挂载不抛错，并在首屏请求列表接口', async () => {
    const wrapper = mount(SpringActionList, {
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(getMock).toHaveBeenCalledWith(
      '/spring-actions',
      expect.objectContaining({ params: expect.objectContaining({ page: 1, size: 20 }) }),
    )
    expect(wrapper.text()).toContain('新增春耕行动')
    wrapper.unmount()
  })

  it('新增春耕行动弹窗提供漏洞详情录入，并复用 Element Plus 内联校验', async () => {
    const wrapper = mount(SpringActionList, {
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增春耕行动'))
    expect(addBtn).toBeTruthy()
    await addBtn!.trigger('click')
    await flushPromises()

    const dialogText = wrapper.text() + (document.body.textContent ?? '')
    expect(dialogText).toContain('报告编号')
    expect(dialogText).toContain('涉及漏洞')
    // 报告编号已接入 Element Plus rules（必填星号由表单上下文派生）
    expect(wrapper.find('.el-form-item').classes()).toContain('is-required')

    const quickBtn = wrapper.findAll('button').find((b) => b.text().includes('新增漏洞'))
    expect(quickBtn).toBeTruthy()
    await quickBtn!.trigger('click')
    await flushPromises()

    const quickText = wrapper.text() + (document.body.textContent ?? '')
    expect(wrapper.find('.quick-vul-form').exists()).toBe(true)
    expect(quickText).toContain('漏洞详情（可选）')
    expect(quickText).toContain('影响URL')
    expect(quickText).toContain('漏洞描述')
    expect(quickText).toContain('复现步骤')
    expect(quickText).toContain('修复建议')

    wrapper.unmount()
  })
})
