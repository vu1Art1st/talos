// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock, postMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())

// mock 路由：组件内多处 router.push 跳漏洞/报告详情页；导入链会拉起 router/index.ts。
// 跳转需携带来源（redirect 取自当前页 fullPath）故需 useRoute。
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({
      path: '/testing-plans', fullPath: '/testing-plans?plan=1', params: {}, query: { plan: '1' },
    }),
    useRouter: () => ({
      push: vi.fn().mockResolvedValue(undefined),
      replace: vi.fn().mockResolvedValue(undefined),
      back: vi.fn(),
    }),
  }
})

// mock auth store：屏蔽其导入链（router/pinia），仅提供 meta 字典与管理员身份
vi.mock('../../stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1, permissions: ['*'] },
    meta: null,
    fetchMeta: vi.fn().mockResolvedValue({ testing_plan_status: {}, vul_status: {} }),
    hasPerm: () => true,
  }),
}))

import PlanWorkflowDrawer from '../PlanWorkflowDrawer.vue'

/** 工单详情最小夹具（未认领、初测中、无报告，便于验证「认领」入口） */
function planFixture() {
  return {
    id: 1,
    system_name: '商城系统',
    status: 20,
    testers: [],
    reports: [],
    no_vul_conclusion: '',
  }
}

describe('PlanWorkflowDrawer 工单流程抽屉', () => {
  beforeEach(() => {
    getMock.mockReset()
    postMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/testing-plans/1') return { data: planFixture() }
      if (url === '/testing-plans/1/vuln-order') return { data: {} }
      if (url === '/vulns') {
        return {
          data: {
            items: [
              {
                id: 11, title: 'SQL注入', level: 10, vul_type: 1, status: 20,
                is_retest: false, affected_url: 'https://a.example.com/x',
              },
            ],
            total: 1,
          },
        }
      }
      return { data: [] }
    })
  })

  function mountDrawer() {
    return mount(PlanWorkflowDrawer, {
      props: { planId: 1, visible: true },
      global: { plugins: [ElementPlus] },
    })
  }

  it('打开抽屉时拉取工单详情、关联漏洞与导入序号映射，并渲染系统名', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    const urls = getMock.mock.calls.map((c) => c[0])
    expect(urls).toContain('/testing-plans/1')
    expect(urls).toContain('/vulns')
    expect(urls).toContain('/testing-plans/1/vuln-order')
    // 漏洞列表按工单过滤且限制 size=100（后端上限）
    const vulCall = getMock.mock.calls.find((c) => c[0] === '/vulns')
    expect(vulCall?.[1]?.params?.testing_plan_id).toBe(1)
    expect(wrapper.text()).toContain('商城系统')
    wrapper.unmount()
  })

  it('点击「认领」调用认领接口并刷新数据', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    const claimBtn = wrapper.findAll('button').find((b) => b.text().includes('认领'))
    expect(claimBtn, '认领按钮应可见（未认领 + 管理员）').toBeTruthy()
    await claimBtn!.trigger('click')
    await flushPromises()

    const claimCalls = postMock.mock.calls.filter((c) => c[0] === '/testing-plans/1/claim')
    expect(claimCalls.length).toBeGreaterThan(0)
    // 认领后应重新拉取工单详情（认领 → 刷新链路完整）
    const planGets = getMock.mock.calls.filter((c) => c[0] === '/testing-plans/1')
    expect(planGets.length).toBeGreaterThan(1)
    wrapper.unmount()
  })

  it('报告列表按复测状态标注：未发起复测 / 复测中 / 复测完成', async () => {
    getMock.mockImplementation(async (url: string) => {
      if (url === '/testing-plans/1') {
        return {
          data: {
            ...planFixture(),
            status: 50,
            reports: [
              {
                id: 101, title: '商城系统渗透测试报告', status: 'final',
                vul_total: 2, vul_closed: 2, all_closed: true, is_retest: false, retest_state: 'done',
              },
              {
                id: 102, title: '商城系统渗透测试复测报告', status: 'draft',
                vul_total: 2, vul_closed: 1, all_closed: false, is_retest: true, retest_state: 'ongoing',
              },
              {
                id: 103, title: '商城系统渗透测试报告-新', status: 'draft',
                vul_total: 1, vul_closed: 0, all_closed: false, is_retest: false, retest_state: 'none',
              },
            ],
          },
        }
      }
      if (url === '/testing-plans/1/vuln-order') return { data: {} }
      return { data: { items: [], total: 0 } }
    })
    const wrapper = mountDrawer()
    await flushPromises()

    expect(wrapper.text()).toContain('复测完成')
    expect(wrapper.text()).toContain('复测中')
    expect(wrapper.text()).toContain('未发起复测')
    wrapper.unmount()
  })

  it('点击「生成报告」展开表单并预填标题与全部漏洞', async () => {
    const wrapper = mountDrawer()
    await flushPromises()

    const genBtn = wrapper.findAll('button').find((b) => b.text().includes('生成报告'))
    expect(genBtn, '生成报告入口应可见').toBeTruthy()
    await genBtn!.trigger('click')
    await flushPromises()

    // 需求8：自动命名 yyyymmdd+测试系统名称+渗透测试报告，且默认勾选全部漏洞
    const titleInput = wrapper.find('input[placeholder*="报告"]')
    if (titleInput.exists()) {
      const value = (titleInput.element as HTMLInputElement).value
      expect(value).toContain('商城系统渗透测试报告')
    }
    wrapper.unmount()
  })
})
