// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import UserAvatar from '../UserAvatar.vue'

describe('UserAvatar', () => {
  it('无头像时展示姓名首字回退', () => {
    const wrapper = mount(UserAvatar, { props: { name: '张三', size: 40 } })
    expect(wrapper.text()).toBe('张')
    expect(wrapper.attributes('style')).toContain('width: 40px')
  })

  it('预置头像按 preset 标识渲染 SVG', () => {
    const wrapper = mount(UserAvatar, { props: { avatar: 'preset:07', name: '张三' } })
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.text()).toBe('')
  })

  it('上传头像优先使用 avatar_url', () => {
    const wrapper = mount(UserAvatar, {
      props: { avatar: 'uploads/images/demo.webp', avatarUrl: '/storage/uploads/images/demo.webp' },
    })
    expect(wrapper.find('img').attributes('src')).toBe('/storage/uploads/images/demo.webp')
  })
})
