// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import UserAvatar from '../UserAvatar.vue'

describe('UserAvatar', () => {
  it('无头像时展示首字母色块', () => {
    const wrapper = mount(UserAvatar, { props: { name: '张三', size: 40 } })
    expect(wrapper.text()).toBe('张')
    expect(wrapper.attributes('style')).toContain('width: 40px')
  })

  it('预置头像由后端下发 avatar_url，组件只负责渲染图片', () => {
    const wrapper = mount(UserAvatar, {
      props: { avatar: 'preset:zzz/3.2/01', avatarUrl: '/storage/avatars/zzz/3.2/01.webp' },
    })
    expect(wrapper.find('img').attributes('src')).toBe('/storage/avatars/zzz/3.2/01.webp')
    expect(wrapper.text()).toBe('')
  })

  it('上传头像使用 avatar_url', () => {
    const wrapper = mount(UserAvatar, {
      props: { avatar: 'uploads/images/demo.webp', avatarUrl: '/storage/uploads/images/demo.webp' },
    })
    expect(wrapper.find('img').attributes('src')).toBe('/storage/uploads/images/demo.webp')
  })

  it('avatar 存在但拿不到 URL（如下线预设）时回落首字母', () => {
    const wrapper = mount(UserAvatar, { props: { avatar: 'preset:07', name: '李四' } })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('李')
  })
})
