// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

// mock 路由：状态码来自路由参数。组件经 useAuthStore → stores/auth.ts → router/index.ts
// 间接依赖 createRouter/createWebHistory，故用 importOriginal 保留真实导出、仅覆盖 hook。
const replaceMock = vi.fn(() => Promise.resolve())
const backMock = vi.fn()
const route: { params: Record<string, unknown>; query: Record<string, unknown> } = {
  params: { code: '404' },
  query: {},
}

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => route,
    useRouter: () => ({ replace: replaceMock, push: vi.fn(), back: backMock }),
  }
})

import ErrorPage from '../ErrorPage.vue'

function mountPage() {
  return mount(ErrorPage, { global: { plugins: [createPinia()] } })
}

describe('ErrorPage 视图', () => {
  beforeEach(() => {
    replaceMock.mockClear()
    backMock.mockClear()
    localStorage.clear()
    route.params = { code: '404' }
    route.query = {}
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('404：渲染状态码与面向操作人员的文案', () => {
    const wrapper = mountPage()
    expect(wrapper.text()).toContain('404')
    expect(wrapper.text()).toContain('页面不存在')
    expect(document.title).toContain('404')
    wrapper.unmount()
  })

  it('未登记状态码走通用模板，非法状态码归一到 404 并改写地址', async () => {
    route.params = { code: '507' }
    let wrapper = mountPage()
    expect(wrapper.text()).toContain('服务出现异常')
    wrapper.unmount()

    route.params = { code: 'abc' }
    wrapper = mountPage()
    await Promise.resolve()
    expect(wrapper.text()).toContain('页面不存在')
    expect(replaceMock).toHaveBeenCalledWith({ name: 'error', params: { code: '404' } })
    wrapper.unmount()
  })

  it('401：主操作是「重新登录」，点击清理本地凭证并带去向回登录页', async () => {
    localStorage.setItem('access_token', 'stale-token')
    localStorage.setItem('refresh_token', 'stale-refresh')
    route.params = { code: '401' }
    route.query = { redirect: '/vulns/9' }

    const wrapper = mountPage()
    const loginBtn = wrapper.get('[data-test="error-primary"]')
    expect(loginBtn.text()).toContain('重新登录')
    await loginBtn.trigger('click')

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(replaceMock).toHaveBeenCalledWith({ path: '/login', query: { redirect: '/vulns/9' } })
    wrapper.unmount()
  })

  it('404 只保留一个主操作，并返回首页', async () => {
    const wrapper = mountPage()
    const homeBtn = wrapper.get('[data-test="error-primary"]')
    expect(homeBtn.text()).toContain('返回首页')
    await homeBtn.trigger('click')
    expect(backMock).not.toHaveBeenCalled()
    expect(replaceMock).toHaveBeenCalledWith('/dashboard')
    wrapper.unmount()
  })
})
