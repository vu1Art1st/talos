// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import AffectedUrlEditor from '../AffectedUrlEditor.vue'
import { AFFECTED_URL_MAX_COUNT } from '../../utils/urls'

/** 构造带剪贴板内容的 paste 事件载荷（jsdom 不提供 clipboardData，需手动注入） */
const paste = (text: string) => ({
  clipboardData: { getData: () => text },
  bubbles: true,
  cancelable: true,
})

function mountEditor(modelValue = '') {
  return mount(AffectedUrlEditor, {
    props: { modelValue },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
}

/** 最近一次 v-model 输出（后端「换行分隔单字段」口径） */
const lastEmit = (wrapper: ReturnType<typeof mountEditor>) => {
  const events = wrapper.emitted('update:modelValue') as string[][] | undefined
  return events?.at(-1)?.[0]
}

describe('AffectedUrlEditor 影响URL 多值编辑器', () => {
  it('粘贴多行文本：自动切分、去重并插入当前行位置，同时给出识别条数反馈', async () => {
    const wrapper = mountEditor('')
    await wrapper.findAll('.tl-url-row')[0].trigger('paste', paste(
      'https://a.com/1\nhttps://b.com/2\r\nhttps://a.com/1\n\nhttps://c.com/3',
    ))

    expect(wrapper.findAll('input').length).toBe(3)
    expect(lastEmit(wrapper)).toBe('https://a.com/1\nhttps://b.com/2\nhttps://c.com/3')
    expect(wrapper.text()).toContain('已识别 3 条')
    expect(wrapper.find('.is-invalid').exists()).toBe(false)
    wrapper.unmount()
  })

  it('粘贴分号（含全角）分隔文本同样自动切分', async () => {
    const wrapper = mountEditor('')
    await wrapper.findAll('.tl-url-row')[0].trigger('paste', paste(
      'https://a.com/1; https://a.com/2；https://a.com/3',
    ))

    expect(wrapper.findAll('input').length).toBe(3)
    expect(lastEmit(wrapper)).toBe('https://a.com/1\nhttps://a.com/2\nhttps://a.com/3')
    wrapper.unmount()
  })

  it('粘贴内容与已有条目重复时去重，并提示去重条数', async () => {
    const wrapper = mountEditor('https://a.com/1')
    await wrapper.findAll('.tl-url-row')[0].trigger('paste', paste('https://a.com/1\nhttps://a.com/2'))

    expect(wrapper.findAll('input').length).toBe(2)
    expect(lastEmit(wrapper)).toBe('https://a.com/1\nhttps://a.com/2')
    expect(wrapper.text()).toContain('已去重 1 条')
    wrapper.unmount()
  })

  it('单值粘贴不接管默认行为（交给浏览器保留光标位置）', async () => {
    const wrapper = mountEditor('')
    await wrapper.findAll('.tl-url-row')[0].trigger('paste', paste('https://only.example.com/x'))

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.findAll('input').length).toBe(1)
    wrapper.unmount()
  })

  it('当前行已填内容未被整段选中时保留原内容并追加，选中时按覆盖处理', async () => {
    const appendWrapper = mountEditor('https://keep.example.com/1')
    await appendWrapper.findAll('.tl-url-row')[0].trigger('paste', paste('https://a.com/1\nhttps://a.com/2'))
    expect(lastEmit(appendWrapper)).toBe(
      'https://keep.example.com/1\nhttps://a.com/1\nhttps://a.com/2',
    )
    appendWrapper.unmount()

    const replaceWrapper = mountEditor('https://old.example.com/1')
    const input = replaceWrapper.findAll('input')[0].element as HTMLInputElement
    input.setSelectionRange(0, input.value.length)
    await replaceWrapper.findAll('.tl-url-row')[0].trigger('paste', paste('https://a.com/1\nhttps://a.com/2'))
    expect(lastEmit(replaceWrapper)).toBe('https://a.com/1\nhttps://a.com/2')
    replaceWrapper.unmount()
  })

  it('粘贴结果超过 100 条上限时整批拒绝且不静默丢弃已有内容', async () => {
    const wrapper = mountEditor('https://keep.example.com/1')
    const tooMany = Array.from({ length: AFFECTED_URL_MAX_COUNT }, (_, i) => `https://a.com/${i}`).join('\n')
    await wrapper.findAll('.tl-url-row')[0].trigger('paste', paste(tooMany))

    expect(wrapper.findAll('input').length).toBe(1)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.text()).toContain(`累计将超过 ${AFFECTED_URL_MAX_COUNT} 条上限`)
    wrapper.unmount()
  })

  it('添加URL 追加空行，删除按钮移除对应行；仅剩一行时不提供删除', async () => {
    const wrapper = mountEditor('https://a.com/1')
    expect(wrapper.findAll('button').some((b) => b.text().includes('添加URL'))).toBe(true)
    // 仅一行时不给删除入口
    expect(wrapper.find('.tl-url-row').findAll('button').length).toBe(0)

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('添加URL'))!
    await addBtn.trigger('click')
    expect(wrapper.findAll('input').length).toBe(2)
    expect(lastEmit(wrapper)).toBe('https://a.com/1\n')

    const deleteBtn = wrapper.findAll('.tl-url-row')[1].find('button')
    await deleteBtn.trigger('click')
    expect(wrapper.findAll('input').length).toBe(1)
    expect(lastEmit(wrapper)).toBe('https://a.com/1')
    wrapper.unmount()
  })

  it('逐条输入触发校验：含空格条目标红并在字段下方行内提示', async () => {
    const wrapper = mountEditor('')
    await wrapper.findAll('input')[0].setValue('https://a.com/1 描述')

    expect(wrapper.find('.is-invalid').exists()).toBe(true)
    expect(wrapper.text()).toContain('第 1 条影响URL 含空格或非法字符，请修正后再提交')

    // 修正后错误消失，输入内容不丢失
    await wrapper.findAll('input')[0].setValue('https://a.com/1')
    expect(wrapper.find('.is-invalid').exists()).toBe(false)
    expect(lastEmit(wrapper)).toBe('https://a.com/1')
    wrapper.unmount()
  })

  it('外部回显改动时重建行结构（历史数据按换行拆行展示）', async () => {
    const wrapper = mountEditor('')
    await wrapper.setProps({ modelValue: 'https://a.com/1\nhttps://a.com/2' })

    const inputs = wrapper.findAll('input')
    expect(inputs.length).toBe(2)
    expect((inputs[0].element as HTMLInputElement).value).toBe('https://a.com/1')
    expect((inputs[1].element as HTMLInputElement).value).toBe('https://a.com/2')
    wrapper.unmount()
  })
})
