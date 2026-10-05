// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())

import NonpenPlanWorkflowDrawer from '../NonpenPlanWorkflowDrawer.vue'
import NonpenPlanInfoPanel from '../NonpenPlanInfoPanel.vue'

function planFixture() {
  return {
    id: 9,
    plan_name: '商城系统漏扫基线',
    system_name: '商城系统',
    ticket_id: 'T-20260901-2',
    linked: false,
    items: {
      baseline: { status: 'testing', first_times: 1, retest_times: 0 },
      host: { status: 'ignored', first_times: 0, retest_times: 0 },
      web: { status: 'not_started', first_times: 0, retest_times: 0 },
    },
  }
}

describe('NonpenPlanWorkflowDrawer 漏扫流程抽屉', () => {
  beforeEach(() => {
    getMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/nonpen-plans/9') return { data: planFixture() }
      if (url === '/dict/test_type') return { data: [{ name: '基线扫描' }] }
      if (url === '/groups') return { data: [{ name: '安全部' }] }
      return { data: [] }
    })
  })

  function mountDrawer(props: Record<string, unknown> = {}) {
    return mount(NonpenPlanWorkflowDrawer, {
      props: { planId: 9, visible: true, ...props },
      global: { plugins: [ElementPlus] },
    })
  }

  it('默认落在「测试流程」标签，信息面板不抢先挂载', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    expect(wrapper.text()).toContain('商城系统')
    expect(wrapper.findComponent(NonpenPlanInfoPanel).exists()).toBe(false)
    wrapper.unmount()
  })

  it('tab=info 时渲染只读信息面板，点击「编辑」切换为表单态', async () => {
    const wrapper = mountDrawer({ tab: 'info' })
    await flushPromises()

    const panel = wrapper.findComponent(NonpenPlanInfoPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props('mode')).toBe('view')
    const editBtn = wrapper.find('[data-test="nonpen-info-edit"]')
    expect(editBtn.exists()).toBe(true)
    await editBtn.trigger('click')
    await flushPromises()
    expect(panel.props('mode')).toBe('edit')
    wrapper.unmount()
  })

  it('切换标签只更新 tab，不重复拉取工单详情', async () => {
    const wrapper = mountDrawer()
    await flushPromises()
    const before = getMock.mock.calls.filter((c) => c[0] === '/nonpen-plans/9').length

    const infoTab = wrapper.findAll('.el-tabs__item').find((n) => n.text() === '工单信息')
    expect(infoTab, '工单信息标签应可见').toBeTruthy()
    await infoTab!.trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:tab')?.at(-1)).toEqual(['info'])
    const after = getMock.mock.calls.filter((c) => c[0] === '/nonpen-plans/9').length
    expect(after).toBe(before)
    wrapper.unmount()
  })
})
