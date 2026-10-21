// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ElementPlus from 'element-plus'

vi.mock('../../api/client', () => ({
  default: {
    post: vi.fn(),
  },
}))

import client from '../../api/client'

import RichEditor from '../RichEditor.vue'

function mountEditor(modelValue = '') {
  return mount(RichEditor, {
    props: { modelValue },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
}

beforeEach(() => {
  vi.mocked(client.post).mockReset()
})

describe('RichEditor TipTap 3 外部内容同步', () => {
  it('渲染初始 HTML', async () => {
    const wrapper = mountEditor('<p>初始内容</p>')
    await flushPromises()

    expect(wrapper.find('.ProseMirror').html()).toContain('初始内容')
    wrapper.unmount()
  })

  it('外部 modelValue 变化只更新编辑器，不回发 update:modelValue', async () => {
    const wrapper = mountEditor('<p>初始内容</p>')
    await flushPromises()

    await wrapper.setProps({ modelValue: '<p>外部更新</p>' })
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.ProseMirror').html()).toContain('外部更新')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    wrapper.unmount()
  })

  it('上传图片时图片独占一行，且尾部仅补一个空行', async () => {
    vi.mocked(client.post).mockResolvedValue({
      data: { url: '/storage/uploads/images/standalone.png' },
    })
    const wrapper = mountEditor('<p>前置文本</p>')
    await flushPromises()

    const input = wrapper.find('input[type="file"]')
    const file = new File(['x'], 'shot.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', {
      value: [file],
      configurable: true,
    })
    await input.trigger('change')
    await nextTick()
    await flushPromises()

    const html = wrapper.find('.ProseMirror').html()
    expect(html).toContain('<p>前置文本</p>')
    expect(html).toContain('src="/storage/uploads/images/standalone.png"')
    expect((html.match(/src="\/storage\/uploads\/images\/standalone\.png"/g) || []).length).toBe(1)
    expect((html.match(/<p><br class="ProseMirror-trailingBreak"><\/p>/g) || []).length).toBe(1)
    wrapper.unmount()
  })
})
