// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())

// mock 路由：组件内多处 router.push 跳漏洞/报告详情页；导入链会拉起 router/index.ts
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRouter: () => ({ push: vi.fn() }) }
})

// mock auth / theme store：屏蔽其导入链（router/pinia），只提供组件实际读取的字段
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, realname: '管理员', permissions: ['*'] },
    fetchMeta: vi.fn().mockResolvedValue({ testing_plan_status: {}, vul_status: {} }),
    hasPerm: () => true,
  }),
}))
vi.mock('../../stores/theme', () => ({ useThemeStore: () => ({ dark: false }) }))

// echarts 在 jsdom 下没有 canvas 上下文（setOption / dispose 会因 null context 抛 TypeError），
// 交互测试只关心「图表是否被初始化」，故以桩替换；真实渲染由浏览器构建产物与手工验证覆盖
vi.mock('echarts', () => ({
  init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }),
}))

import TestingPlanList from '../TestingPlanList.vue'

describe('TestingPlanList 工单列表页', () => {
  beforeEach(() => {
    getMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/testing-plans') {
        return {
          data: {
            items: [
              {
                id: 7, ticket_id: 'T-20260917-001', system_name: '商城系统', test_type: '黑盒',
                department: '安全部', status: 20, testers: [], asset_ids: [], target_urls: [],
                vulns: [], reports: [], create_time: '2026-09-17 10:00:00',
                receive_time: '2026-09-16', est_mandays: 1, actual_mandays: 1,
              },
            ],
            total: 1,
          },
        }
      }
      if (url === '/testing-plans/stats') {
        return { data: { total_plans: 1, retest_done_plans: 0, vulns_by_month: [] } }
      }
      if (url === '/testing-plans/conclusion') {
        return {
          data: {
            summary: '本次共测试 1 个系统。',
            departments: 1, systems: 1, vuln_systems: 0, vulns: 0,
            safe_systems: 0, fixed_systems: 0, fixing_systems: 0,
          },
        }
      }
      return { data: [] }
    })
  })

  function mountPage() {
    return mount(TestingPlanList, { global: { plugins: [ElementPlus] } })
  }

  it('挂载时并行拉取列表、统计、结论与字典，并渲染工单行', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const urls = getMock.mock.calls.map((c) => c[0])
    expect(urls).toContain('/testing-plans')
    expect(urls).toContain('/testing-plans/stats')
    expect(urls).toContain('/testing-plans/conclusion')
    expect(wrapper.text()).toContain('商城系统')
    wrapper.unmount()
  })

  it('结论接口按当前筛选参数请求，返回内容渲染进结论面板', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const call = getMock.mock.calls.find((c) => c[0] === '/testing-plans/conclusion')
    expect(call, '应请求结论接口').toBeTruthy()
    // 筛选参数由 filterParams() 统一拼装（search 至少存在，保证与列表口径一致）
    expect(call?.[1]?.params).toHaveProperty('search')
    expect(wrapper.text()).toContain('本次共测试 1 个系统。')
    wrapper.unmount()
  })
})
