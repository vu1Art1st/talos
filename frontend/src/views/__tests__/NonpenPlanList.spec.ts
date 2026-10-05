// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { reactive } from 'vue'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())

const routeState = reactive<{
  path: string
  fullPath: string
  params: Record<string, unknown>
  query: Record<string, unknown>
}>({ path: '/nonpen-plans', fullPath: '/nonpen-plans', params: {}, query: {} })

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => routeState,
    useRouter: () => ({
      push: vi.fn().mockResolvedValue(undefined),
      replace: vi.fn().mockResolvedValue(undefined),
      back: vi.fn(),
    }),
  }
})

import NonpenPlanList from '../NonpenPlanList.vue'
import NonpenPlanInfoPanel from '../../components/NonpenPlanInfoPanel.vue'
import NonpenPlanWorkflowDrawer from '../../components/NonpenPlanWorkflowDrawer.vue'

describe('NonpenPlanList 漏扫基线工单列表页', () => {
  beforeEach(() => {
    routeState.query = {}
    routeState.path = '/nonpen-plans'
    routeState.fullPath = '/nonpen-plans'
    getMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/nonpen-plans') {
        return {
          data: {
            items: [
              {
                id: 9, ticket_id: 'T-20260901-2', plan_name: '商城系统漏扫基线',
                system_name: '商城系统', test_type: '基线扫描', department: '安全部',
                receive_time: '2026-09-01', items: {},
              },
            ],
            total: 1,
          },
        }
      }
      if (url === '/nonpen-plans/stats') {
        return { data: { total: 1, retest_done: 0, baseline_times: 0, host_times: 0, web_times: 0 } }
      }
      if (url === '/nonpen-plans/9') {
        return {
          data: {
            id: 9, plan_name: '商城系统漏扫基线', system_name: '商城系统',
            ticket_id: 'T-20260901-2', asset_ids: [], items: {},
          },
        }
      }
      if (url === '/dict/test_type') return { data: [{ name: '基线扫描' }] }
      if (url === '/groups') return { data: [{ name: '安全部' }] }
      return { data: [] }
    })
  })

  function mountPage() {
    return mount(NonpenPlanList, { global: { plugins: [ElementPlus] } })
  }

  it('挂载时拉取列表与统计并渲染工单行', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const urls = getMock.mock.calls.map((c) => c[0])
    expect(urls).toContain('/nonpen-plans')
    expect(urls).toContain('/nonpen-plans/stats')
    expect(wrapper.text()).toContain('商城系统漏扫基线')
    wrapper.unmount()
  })

  it('行内「工单信息」入口打开同一抽屉并落到 info 标签', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const infoBtn = wrapper.findAll('button').find((b) => b.text() === '工单信息')
    expect(infoBtn, '工单信息入口应可见').toBeTruthy()
    await infoBtn!.trigger('click')
    await flushPromises()

    const drawer = wrapper.findComponent(NonpenPlanWorkflowDrawer)
    expect(drawer.props('visible')).toBe(true)
    expect(drawer.props('tab')).toBe('info')
    wrapper.unmount()
  })

  it('新增入口打开创建面板', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增漏扫基线工单'))
    expect(addBtn, '新增入口应可见').toBeTruthy()
    await addBtn!.trigger('click')
    await flushPromises()

    const panel = wrapper.findComponent(NonpenPlanInfoPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props('mode')).toBe('create')
    wrapper.unmount()
  })

  it('深链 ?plan=<id>&tab=info 恢复抽屉与标签', async () => {
    routeState.query = { plan: '9', tab: 'info' }
    routeState.fullPath = '/nonpen-plans?plan=9&tab=info'

    const wrapper = mountPage()
    await flushPromises()

    const drawer = wrapper.findComponent(NonpenPlanWorkflowDrawer)
    expect(drawer.props('visible')).toBe(true)
    expect(drawer.props('tab')).toBe('info')
    wrapper.unmount()
  })
})
