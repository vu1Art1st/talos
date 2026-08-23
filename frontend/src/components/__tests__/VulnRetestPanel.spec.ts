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

// RichEditor 依赖 TipTap（jsdom 下重且与本测试无关），用轻量 stub 替代
vi.mock('../RichEditor.vue', () => ({
  default: {
    name: 'RichEditor',
    props: ['modelValue'],
    emits: ['update:modelValue', 'update:json'],
    template: '<div class="rich-editor-stub" />',
  },
}))

import VulnRetestPanel from '../VulnRetestPanel.vue'

describe('VulnRetestPanel 复测记录面板', () => {
  beforeEach(() => {
    getMock.mockReset()
    // 初始无复测记录：GET /vulns/{id}/retests 返回空数组；回退请求 /vulns/{id} 同样给空数据
    getMock.mockResolvedValue({ data: [] })
    document.body.innerHTML = ''
  })

  // 回归：新增复测记录弹窗缺少 append-to-body 时被渲染在测试计划抽屉表格展开行 td 内，
  // 固定定位失效导致页面闪烁、按钮点击失灵；弹窗必须挂载到 document.body
  it('新增复测记录弹窗通过 append-to-body 挂载到 document.body', async () => {
    const wrapper = mount(VulnRetestPanel, {
      props: { vulId: 1 },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增复测记录'))
    expect(addBtn).toBeTruthy()
    await addBtn!.trigger('click')
    await flushPromises()

    const overlay = document.body.querySelector('.el-overlay')
    expect(overlay).toBeTruthy()
    expect(document.body.textContent).toContain('复测标题')
    // 弹窗脱离组件根节点、直接挂在 body 下（append-to-body 生效）
    expect(wrapper.element.contains(overlay!)).toBe(false)
    expect(document.body.contains(overlay!)).toBe(true)

    wrapper.unmount()
  })
})
