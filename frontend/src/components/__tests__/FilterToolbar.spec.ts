// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'

import FilterToolbar from '../FilterToolbar.vue'

describe('FilterToolbar', () => {
  it('没有右侧操作时不留弹性空白', () => {
    const wrapper = mount(FilterToolbar, {
      slots: { default: () => h('span', '筛选条件') },
    })

    expect(wrapper.text()).toContain('筛选条件')
    expect(wrapper.find('.flex-1').exists()).toBe(false)
  })

  it('存在右侧操作时由组件补齐弹性间隔', () => {
    const wrapper = mount(FilterToolbar, {
      slots: {
        default: () => h('span', '筛选条件'),
        actions: () => h('button', '新建'),
      },
    })

    expect(wrapper.find('.flex-1').exists()).toBe(true)
    expect(wrapper.get('button').text()).toBe('新建')
  })
})
