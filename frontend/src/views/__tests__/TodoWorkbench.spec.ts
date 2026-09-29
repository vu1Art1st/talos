// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())

// 「查看全部」只允许在卡片内展开：路由替身暴露 push 供断言「未发生任何跳转」
const pushSpy = vi.fn().mockResolvedValue(undefined)
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRouter: () => ({ push: pushSpy }) }
})

import TodoWorkbench from '../TodoWorkbench.vue'

const PREVIEW = 8
const TOTAL = 25

function mkItem(id: number) {
  return { id, title: `待办漏洞 ${id}`, level: 20, level_name: '高危', link: `/vulns/${id}` }
}

describe('TodoWorkbench 个人待办', () => {
  beforeEach(() => {
    pushSpy.mockClear()
    getMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/todos') {
        return {
          data: {
            total: TOTAL,
            groups: [{
              category: 'my_vulns', name: '我提交的漏洞', count: TOTAL,
              items: Array.from({ length: PREVIEW }, (_, i) => mkItem(i + 1)),
            }],
          },
        }
      }
      if (url === '/todos/my_vulns') {
        return {
          data: {
            category: 'my_vulns', name: '我提交的漏洞', total: TOTAL,
            items: Array.from({ length: 20 }, (_, i) => mkItem(i + 1)),
          },
        }
      }
      return { data: [] }
    })
  })

  function mountPage() {
    return mount(TodoWorkbench, { global: { plugins: [ElementPlus] } })
  }

  function findButton(wrapper: ReturnType<typeof mountPage>, text: string) {
    return wrapper.findAll('button').find((b) => b.text().includes(text))
  }

  it('「查看全部」在卡片内展开全部待办，且不触发任何路由跳转', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.findAll('.todo-list li')).toHaveLength(PREVIEW)

    const viewAll = findButton(wrapper, '查看全部')
    expect(viewAll, '卡片头应提供「查看全部」').toBeTruthy()
    await viewAll!.trigger('click')
    await flushPromises()

    // 明细通过分页接口拉取（page=1, size=20），展开后展示的是服务端返回的完整条目
    const detail = getMock.mock.calls.find((c) => c[0] === '/todos/my_vulns')
    expect(detail, '应请求单分类明细接口').toBeTruthy()
    expect(detail?.[1]?.params).toEqual({ page: 1, size: 20 })
    expect(wrapper.findAll('.todo-list li')).toHaveLength(20)
    expect(wrapper.text()).toContain('加载更多（20 / 25）')

    // 核心回归：不得跳到渗透测试工单页或任何其他路由
    expect(pushSpy).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('展开态可继续「加载更多」，再次点击转为「收起」且仍未跳转', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await findButton(wrapper, '查看全部')!.trigger('click')
    await flushPromises()

    getMock.mockImplementation(async (url: string) => {
      if (url === '/todos/my_vulns') {
        return {
          data: {
            category: 'my_vulns', name: '我提交的漏洞', total: TOTAL,
            items: Array.from({ length: 5 }, (_, i) => mkItem(i + 21)),
          },
        }
      }
      return { data: { total: TOTAL, groups: [] } }
    })
    await findButton(wrapper, '加载更多')!.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.todo-list li')).toHaveLength(TOTAL)
    expect(wrapper.text()).toContain('已显示全部 25 条')

    await findButton(wrapper, '收起')!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.todo-list li')).toHaveLength(PREVIEW)
    expect(pushSpy).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('点工单条目按后端深链直达该工单（?plan=<id>），而非只跳工单列表页', async () => {
    getMock.mockImplementation(async (url: string) => {
      if (url === '/todos') {
        return {
          data: {
            total: 1,
            groups: [{
              category: 'plan_unclaimed', name: '待认领工单', count: 1,
              items: [{ id: 5, ticket_id: 'T-20260928-001', system_name: '深链系统', department: '安全部', link: '/testing-plans?plan=5' }],
            }],
          },
        }
      }
      return { data: [] }
    })
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.findAll('.todo-list li')[0].trigger('click')
    await flushPromises()

    expect(pushSpy).toHaveBeenCalledWith('/testing-plans?plan=5')
    wrapper.unmount()
  })
})
