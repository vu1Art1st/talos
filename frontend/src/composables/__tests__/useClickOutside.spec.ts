// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, defineComponent, h, ref } from 'vue'

import { useClickOutside, type UseClickOutsideOptions } from '../useClickOutside'

/** 挂载一个探针组件：trigger / panel 为「内部」，.outside 为「外部」 */
function mountProbe(options?: UseClickOutsideOptions, initiallyOpen = true) {
  const onOutside = vi.fn()
  const enabled = ref(initiallyOpen)
  const triggerRef = ref<HTMLElement>()
  const panelRef = ref<HTMLElement>()

  const Probe = defineComponent({
    setup() {
      useClickOutside([triggerRef, panelRef], enabled, onOutside, options)
      return () => h('div', [
        h('span', { ref: triggerRef, class: 'trigger' }, '筛选'),
        h('div', { ref: panelRef, class: 'panel' }, '面板'),
        h('span', { class: 'outside' }, '外部'),
      ])
    },
  })
  const wrapper = mount(Probe, { attachTo: document.body })

  const click = (selector: string) => {
    const el = document.querySelector(selector)
    expect(el, `${selector} 应存在`).toBeTruthy()
    el!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  }

  return { wrapper, onOutside, enabled, click }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useClickOutside 浮层失焦收回', () => {
  it('点击目标元素之外触发收回，点击触发元素与浮层内部不触发', () => {
    const { wrapper, onOutside, click } = mountProbe()

    click('.outside')
    expect(onOutside).toHaveBeenCalledTimes(1)

    // 内部点击（触发按钮 / 面板）不得收回
    click('.trigger')
    click('.panel')
    expect(onOutside).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('命中 ignoreSelectors 时视为内部点击（放行 teleport 出去的子浮层）', () => {
    const { wrapper, onOutside, click } = mountProbe({ ignoreSelectors: ['.el-popper'] })

    // 模拟 el-select / el-date-picker 浮层：teleport 到 body，不在面板 DOM 内
    document.body.insertAdjacentHTML(
      'beforeend',
      '<div class="el-popper"><span class="nested-option">选项</span></div>',
    )
    click('.nested-option')
    expect(onOutside).not.toHaveBeenCalled()

    click('.outside')
    expect(onOutside).toHaveBeenCalledTimes(1)

    wrapper.unmount()
  })

  it('Esc 触发收回，可按需关闭', async () => {
    const withEscape = mountProbe()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(withEscape.onOutside).toHaveBeenCalledTimes(1)
    withEscape.wrapper.unmount()

    const withoutEscape = mountProbe({ escape: false })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(withoutEscape.onOutside).not.toHaveBeenCalled()
    withoutEscape.wrapper.unmount()
  })

  it('enabled 为假时不挂监听，置真后生效；卸载后解绑', async () => {
    const { wrapper, onOutside, enabled, click } = mountProbe(undefined, false)

    click('.outside')
    expect(onOutside).not.toHaveBeenCalled()

    enabled.value = true
    await nextTick()
    click('.outside')
    expect(onOutside).toHaveBeenCalledTimes(1)

    // 卸载后即使外部元素仍在文档中也不再响应
    wrapper.unmount()
    document.body.insertAdjacentHTML('beforeend', '<span class="outside">外部</span>')
    click('.outside')
    expect(onOutside).toHaveBeenCalledTimes(1)
  })
})
