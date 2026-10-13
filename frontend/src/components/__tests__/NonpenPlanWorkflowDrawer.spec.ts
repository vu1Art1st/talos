// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'
import { describePlanDrawerTabs } from '../../__tests__/helpers/planDrawerTabs'

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

  // 标签与信息面板契约的 3 条用例与工单流程抽屉逐字同构，集中到共享 helper
  describePlanDrawerTabs({
    suite: 'NonpenPlanWorkflowDrawer 漏扫流程抽屉',
    infoPanel: NonpenPlanInfoPanel,
    detailUrl: '/nonpen-plans/9',
    defaultTabText: '商城系统',
    editTestId: 'nonpen-info-edit',
    mountDrawer,
  })
})
