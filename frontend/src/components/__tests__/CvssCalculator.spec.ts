// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import CvssCalculator from '../CvssCalculator.vue'

const LEGACY_VECTOR = 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'

describe('CvssCalculator', () => {
  it('默认提供 CVSS 4.0 的 11 项基础指标', () => {
    const wrapper = mount(CvssCalculator, {
      props: { vector: '', score: 0 },
      global: { plugins: [ElementPlus] },
    })

    expect(wrapper.text()).toContain('CVSS 4.0')
    expect(wrapper.text()).toContain('请完整选择 11 项指标后计算评分')
    expect(wrapper.findAll('.el-select')).toHaveLength(11)
    wrapper.unmount()
  })

  it('存量 CVSS 3.1 只读展示，不自动覆盖原向量和评分', async () => {
    const wrapper = mount(CvssCalculator, {
      props: { vector: LEGACY_VECTOR, score: 9.8 },
      global: { plugins: [ElementPlus] },
    })

    expect(wrapper.text()).toContain('存量 CVSS 3.1')
    expect(wrapper.text()).toContain('9.8')
    expect(wrapper.emitted('update:vector')).toBeUndefined()
    expect(wrapper.emitted('update:score')).toBeUndefined()
    wrapper.unmount()
  })

  it('显式切换后清空旧向量，交由用户重新选择 CVSS 4.0 指标', async () => {
    const wrapper = mount(CvssCalculator, {
      props: { vector: LEGACY_VECTOR, score: 9.8 },
      global: { plugins: [ElementPlus] },
    })

    const upgrade = wrapper.findAll('button').find((button) => button.text().includes('按 CVSS 4.0 重新评分'))
    expect(upgrade).toBeTruthy()
    await upgrade!.trigger('click')

    const vectorEvents = wrapper.emitted('update:vector')
    const scoreEvents = wrapper.emitted('update:score')
    expect(vectorEvents?.[vectorEvents.length - 1]).toEqual([''])
    expect(scoreEvents?.[scoreEvents.length - 1]).toEqual([0])
    expect(wrapper.text()).toContain('请完整选择 11 项指标后计算评分')
    wrapper.unmount()
  })
})
