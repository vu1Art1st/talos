// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'
import { expectMountSmoke } from '../../__tests__/helpers/viewSmoke'

// mock 路由：视图仅在跳转详情时使用 router。组件经 useAuthStore → stores/auth.ts → router/index.ts
// 间接依赖 createRouter/createWebHistory，故用 importOriginal 保留真实导出、仅覆盖 hook。
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn() }),
  }
})

// mock axios client：/meta 下发最小字典，/vulns 列表与统计返回空数据
vi.mock('../../api/client', () => clientMockFactory())

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
    testing_plan_status: {}, import_batch_status: {},
    import_record_status: {}, export_job_status: {}, permissions: [],
    colors: {
      vul_level: {}, vul_status: {}, vul_type: {}, testing_plan_status: {},
      asset_status: {}, url_tag: {}, nonpen_item: {},
      import_batch_status: {}, import_record_status: {}, export_job_status: {},
    },
    nonpen: { items: [], status: {}, actions: {}, action_names: {} },
  }
}

describe('VulnList 视图', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

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
    const wrapper = await expectMountSmoke({
      mountView: () => mount(VulnList, { global: { plugins: [ElementPlus, createPinia()] } }),
      expectedUrls: ['/vulns', '/vulns/stats', '/meta'],
      expectedTexts: ['漏洞'],
    })
    wrapper.unmount()
  })

  it('can_edit=false 时禁用行内编辑入口', async () => {
    getMock.mockImplementation(async (url: string) => {
      if (url === '/meta') return { data: metaFixture() }
      if (url === '/vulns/stats') return { data: {} }
      if (url === '/vulns') {
        return {
          data: {
            items: [{
              id: 1, title: '待认领漏洞', level: 20, vul_type: 75, status: 10,
              source: 0, assets: [], department: '', submit_time: null, can_edit: false,
            }],
            total: 1,
          },
        }
      }
      if (url === '/assets') return { data: { items: [], total: 0 } }
      return { data: [] }
    })
    const wrapper = mount(VulnList, {
      global: { plugins: [ElementPlus, createPinia()] },
    })
    await flushPromises()

    const editButton = wrapper.findAll('button').find((b) => b.text().includes('编辑'))
    expect(editButton).toBeTruthy()
    expect(editButton!.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('筛选面板内点击 teleported 日期浮层不会误关，点击外部才关闭', async () => {
    const wrapper = mount(VulnList, {
      attachTo: document.body,
      global: { plugins: [ElementPlus, createPinia()] },
    })
    await flushPromises()

    const filterButton = wrapper.findAll('button').find((b) => b.text().includes('筛选'))
    expect(filterButton).toBeTruthy()
    await filterButton!.trigger('click')
    await flushPromises()

    const filterPopper = () =>
      document.querySelector<HTMLElement>('.vuln-filter-panel')?.closest<HTMLElement>('.el-popper')

    expect(filterPopper()?.style.display).not.toBe('none')
    expect(document.querySelector('.vuln-filter-panel .el-date-editor--daterange')).not.toBeNull()

    // 模拟 Element Plus 日期面板 teleport 到 body 后的真实点击目标。
    document.body.insertAdjacentHTML(
      'beforeend',
      '<div class="el-popper el-picker__popper"><span class="date-cell">18</span></div>',
    )
    document.querySelector('.date-cell')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    expect(filterPopper()?.style.display).not.toBe('none')

    document.body.insertAdjacentHTML('beforeend', '<div class="outside-target"></div>')
    document.querySelector('.outside-target')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await vi.waitFor(() => {
      expect(filterPopper()?.style.display).toBe('none')
    })

    wrapper.unmount()
  })
})
