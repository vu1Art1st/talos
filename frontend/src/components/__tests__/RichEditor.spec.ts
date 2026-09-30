// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ElementPlus from 'element-plus'

import RichEditor from '../RichEditor.vue'

function mountEditor(modelValue = '') {
  return mount(RichEditor, {
    props: { modelValue },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
}

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
})
