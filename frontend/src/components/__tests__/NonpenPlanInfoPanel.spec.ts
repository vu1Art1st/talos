// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import { clientMockFactory, getMock, putMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())

import NonpenPlanInfoPanel from '../NonpenPlanInfoPanel.vue'
import { applyDictMeta } from '../../utils/colors'
import type { NonpenPlan, NonpenPlanForm } from '../../types'

function planFixture(overrides: Partial<NonpenPlan> = {}): NonpenPlan {
  return {
    id: 9,
    plan_name: '商城系统漏扫基线',
    system_name: '商城系统',
    department: '安全部',
    test_type: '基线扫描',
    ticket_id: 'T-20260901-2',
    ticket_id_manual: '',
    ticket_time: '2026-08-30',
    receive_time: '2026-09-01',
    detail: '扫描范围：生产网',
    asset_ids: [],
    asset_names: [],
    test_items: [],
    items: {
      baseline: { status: 'testing', first_times: 1, retest_times: 0 },
      host: { status: 'ignored', first_times: 0, retest_times: 0 },
      web: { status: 'not_started', first_times: 0, retest_times: 0 },
    },
    ...overrides,
  }
}

describe('NonpenPlanInfoPanel 漏扫工单信息面板', () => {
  beforeEach(() => {
    // 测试项/状态名由 /meta 注册表下发；这里注入最小字典，验证信息面板按状态渲染
    applyDictMeta({
      vul_level: {}, vul_status: {}, asset_status: {}, url_tag: {},
      import_batch_status: {}, import_record_status: {}, export_job_status: {},
      colors: {
        vul_level: {}, vul_status: {}, vul_type: {}, testing_plan_status: {},
        asset_status: {}, url_tag: {}, nonpen_item: {},
        import_batch_status: {}, import_record_status: {}, export_job_status: {},
      },
      nonpen: {
        items: [
          { key: 'baseline', name: '基线扫描', desc: '' },
          { key: 'host', name: '主机扫描', desc: '' },
          { key: 'web', name: 'Web扫描', desc: '' },
        ],
        status: { not_started: '未开始', testing: '初测中', ignored: '已忽略' },
        actions: {},
        action_names: {},
      },
    })
    getMock.mockReset()
    putMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/dict/test_type') return { data: [{ name: '基线扫描' }] }
      if (url === '/groups') return { data: [{ name: '安全部' }] }
      if (url.startsWith('/assets/')) {
        return { data: { id: Number(url.split('/').pop()), name: '资产A', department: '安全部' } }
      }
      return { data: [] }
    })
  })

  function mountPanel(mode: 'view' | 'create' | 'edit', plan: NonpenPlan | null = planFixture()) {
    return mount(NonpenPlanInfoPanel, {
      props: { mode, plan },
      global: { plugins: [ElementPlus] },
    })
  }

  it('只读模式渲染工单字段与测试项状态，点击「编辑」发出 request-edit', async () => {
    const wrapper = mountPanel('view')
    await flushPromises()

    expect(wrapper.text()).toContain('商城系统')
    expect(wrapper.text()).toContain('T-20260901-2')
    expect(wrapper.text()).toContain('初测中')
    const editBtn = wrapper.find('[data-test="nonpen-info-edit"]')
    expect(editBtn.exists()).toBe(true)
    await editBtn.trigger('click')
    expect(wrapper.emitted('request-edit')).toHaveLength(1)
    wrapper.unmount()
  })

  it('编辑模式保存时 PUT 去除只读摘要字段并发出 saved', async () => {
    putMock.mockResolvedValue({ data: planFixture({ system_name: '商城系统V2' }) })
    const wrapper = mountPanel('edit')
    await flushPromises()

    const vm = wrapper.vm as unknown as { form: NonpenPlanForm }
    vm.form.system_name = '商城系统V2'
    await flushPromises()
    await wrapper.find('[data-test="nonpen-info-save"]').trigger('click')
    await flushPromises()

    expect(putMock).toHaveBeenCalledTimes(1)
    const [url, body] = putMock.mock.calls[0] as [string, Record<string, unknown>]
    expect(url).toBe('/nonpen-plans/9')
    expect(body.system_name).toBe('商城系统V2')
    expect(body).not.toHaveProperty('items')
    expect(body).not.toHaveProperty('linked')
    expect(wrapper.emitted('saved')).toHaveLength(1)
    wrapper.unmount()
  })

  it('新增模式缺少测试系统或工单来源时不提交', async () => {
    const wrapper = mountPanel('create', null)
    await flushPromises()

    await wrapper.find('[data-test="nonpen-info-save"]').trigger('click')
    await flushPromises()
    expect(putMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
