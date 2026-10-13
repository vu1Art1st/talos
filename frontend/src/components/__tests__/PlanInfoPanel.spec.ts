// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock, putMock } from '../../__tests__/helpers/clientMock'
import { describePlanPanelCommon } from '../../__tests__/helpers/planPanelCommon'

vi.mock('../../api/client', () => clientMockFactory())

const authState = vi.hoisted(() => ({ id: 1, permissions: ['*'] as string[] }))
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: authState.id, permissions: authState.permissions },
    meta: null,
    fetchMeta: vi.fn().mockResolvedValue({}),
    hasPerm: () => true,
  }),
}))

import PlanInfoPanel from '../PlanInfoPanel.vue'
import type { TestingPlan } from '../../types'

function planFixture(overrides: Partial<TestingPlan> = {}): TestingPlan {
  return {
    id: 7,
    plan_name: '商城系统渗透测试计划',
    system_name: '商城系统',
    test_type: '黑盒',
    department: '安全部',
    receive_time: '2026-09-01',
    ticket_time: '2026-08-30',
    ticket_id_manual: '',
    ticket_id: 'T-20260901-1',
    first_test_done_time: '',
    retest_notice_time: '',
    retest_done_time: '',
    status: 20,
    asset_ids: [],
    stat_critical: 0,
    stat_high: 0,
    stat_medium: 0,
    stat_low: 0,
    est_mandays: 1,
    actual_mandays: 1,
    actual_mandays_override: false,
    create_nonpen: false,
    nonpen_test_items: [],
    target_urls: [],
    detail: '',
    testers: [{ id: 1, username: 'admin' }],
    vuls: [],
    reports: [],
    retest_rounds: [],
    retest_round_count: 0,
    ...overrides,
  }
}

describe('PlanInfoPanel 工单信息面板', () => {
  beforeEach(() => {
    authState.permissions = ['*']
    getMock.mockReset()
    putMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/dict/test_type') return { data: [{ name: '黑盒' }] }
      if (url === '/groups') return { data: [{ name: '安全部' }] }
      if (url.startsWith('/assets/')) {
        return { data: { id: Number(url.split('/').pop()), name: '资产A', department: '安全部' } }
      }
      return { data: [] }
    })
  })

  function mountPanel(mode: 'view' | 'create' | 'edit', plan: TestingPlan | null = planFixture()) {
    return mount(PlanInfoPanel, {
      props: { mode, plan },
      global: { plugins: [ElementPlus] },
    })
  }

  it('无操作权限时只读模式不显示编辑入口', async () => {
    authState.permissions = []
    const wrapper = mountPanel('view', planFixture({ testers: [] }))
    await flushPromises()

    expect(wrapper.find('[data-test="plan-info-edit"]').exists()).toBe(false)
    wrapper.unmount()
  })

  // 只读渲染与编辑保存契约与漏扫信息面板逐字同构，集中到共享 helper
  describePlanPanelCommon({
    suite: 'PlanInfoPanel 工单信息面板',
    readOnlyTexts: ['商城系统', 'T-20260901-1'],
    editTestId: 'plan-info-edit',
    saveTestId: 'plan-info-save',
    putUrl: '/testing-plans/7',
    readonlyFields: ['testers', 'vuls', 'reports'],
    editedSystemName: '商城系统V2',
    putResponse: () => planFixture({ system_name: '商城系统V2' }),
    mountPanel,
  })

  it('存在业务进展时禁用「未测试」回退选项', async () => {
    const wrapper = mountPanel('edit', planFixture({ vuls: [{ id: 11 } as never] }))
    await flushPromises()

    const vm = wrapper.vm as unknown as { statusOptionDisabled: (code: number) => boolean }
    expect(vm.statusOptionDisabled(10)).toBe(true)
    wrapper.unmount()
  })

  it('无业务进展时允许管理员回退为「未测试」', async () => {
    // 回退口径：无测试人员且无漏洞/报告/复测轮次
    const wrapper = mountPanel('edit', planFixture({ testers: [] }))
    await flushPromises()

    const vm = wrapper.vm as unknown as { statusOptionDisabled: (code: number) => boolean }
    expect(vm.statusOptionDisabled(10)).toBe(false)
    wrapper.unmount()
  })
})
