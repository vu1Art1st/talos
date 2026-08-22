// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'

// mock 路由：视图仅在跳转详情时使用 router
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

// mock axios client：/meta 下发最小字典，/vulns 列表与统计返回空数据
const getMock = vi.fn()
vi.mock('../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import VulnList from '../VulnList.vue'

// vitest 的 jsdom 环境未注入 localStorage（Node 内建实现不可用），用内存版替身
const storage = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => storage.get(k) ?? null,
  setItem: (k: string, v: string) => storage.set(k, v),
  removeItem: (k: string) => storage.delete(k),
})

function metaFixture() {
  return {
    vul_type: {}, vul_level: {}, vul_status: {}, vul_source: {}, vul_layer: {},
    asset_sec_level: {}, asset_status: {}, system_type: [], url_tag: {},
    testing_plan_status: {}, report_status: {}, import_batch_status: {},
    import_record_status: {}, export_job_status: {}, permissions: [],
    colors: {
      vul_level: {}, vul_status: {}, vul_type: {}, testing_plan_status: {},
      report_status: {}, asset_status: {}, url_tag: {}, nonpen_item: {},
      import_batch_status: {}, import_record_status: {}, export_job_status: {},
    },
    nonpen: { items: [], status: {}, actions: {}, action_names: {} },
  }
}

describe('VulnList 视图', () => {
  beforeEach(() => {
    getMock.mockReset()
    getMock.mockImplementation(async (url: string) => {
      if (url === '/meta') return { data: metaFixture() }
      if (url === '/vulns/stats') return { data: {} }
      if (url === '/vulns') return { data: { items: [], total: 0 } }
      if (url === '/assets') return { data: { items: [], total: 0 } }
      // /dict/test_type、/groups 等数组接口
      return { data: [] }
    })
  })

  it('挂载不抛错，并在首屏请求列表 / 统计 / 字典接口', async () => {
    const wrapper = mount(VulnList, {
      global: { plugins: [ElementPlus, createPinia()] },
    })
    await flushPromises()
    const urls = getMock.mock.calls.map((c) => c[0])
    expect(urls).toContain('/vulns')
    expect(urls).toContain('/vulns/stats')
    expect(urls).toContain('/meta')
    expect(wrapper.text()).toContain('漏洞')
    wrapper.unmount()
  })
})
