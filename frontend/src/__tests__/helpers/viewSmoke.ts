import { flushPromises } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import type { Component } from 'vue'
import { expect } from 'vitest'

import { getMock } from './clientMock'

export interface MountSmokeSpec {
  /** 挂载被测视图：调用点自备 plugins / stubs / mock 路由 */
  mountView: () => VueWrapper
  /** 首屏必须请求到的接口 URL */
  expectedUrls?: string[]
  /** 首屏必须携带分页参数（page=1 / size=20）请求的接口 URL */
  pagedUrls?: string[]
  /** 首屏必须渲染出的文案 */
  expectedTexts?: string[]
}

/**
 * 列表 / 详情页通用「挂载冒烟」：挂载不抛错 + 首屏请求命中 + 关键文案渲染。
 *
 * 各列表页 spec 原先各写一份同构断言（RemoteTestingList / SpringActionList / VulnList / ReportEditor），
 * 统一由本函数承担，spec 只声明「应请求什么、应渲染什么」。
 */
export async function expectMountSmoke(spec: MountSmokeSpec): Promise<VueWrapper> {
  const wrapper = spec.mountView()
  await flushPromises()

  if (spec.expectedUrls?.length) {
    const urls = getMock.mock.calls.map((c) => c[0])
    for (const url of spec.expectedUrls) expect(urls, `首屏应请求 ${url}`).toContain(url)
  }
  for (const url of spec.pagedUrls ?? []) {
    expect(getMock).toHaveBeenCalledWith(
      url,
      expect.objectContaining({ params: expect.objectContaining({ page: 1, size: 20 }) }),
    )
  }
  for (const text of spec.expectedTexts ?? []) {
    expect(wrapper.text(), `首屏应渲染「${text}」`).toContain(text)
  }
  return wrapper
}

export interface InfoEntryDrawerSpec {
  /** 挂载列表页：调用点自备 mock 路由 */
  mountPage: () => VueWrapper
  /** 行内入口应打开的流程抽屉组件 */
  drawer: Component
}

/**
 * 行内「工单信息」入口应打开同一流程抽屉并落到 info 标签。
 *
 * 普通工单页（TestingPlanList）与漏扫基线页（NonpenPlanList）该用例逐字同名同构，集中在此。
 */
export async function expectInfoEntryOpensDrawer(spec: InfoEntryDrawerSpec): Promise<void> {
  const wrapper = spec.mountPage()
  await flushPromises()

  const infoBtn = wrapper.findAll('button').find((b) => b.text() === '工单信息')
  expect(infoBtn, '工单信息入口应可见').toBeTruthy()
  await infoBtn!.trigger('click')
  await flushPromises()

  const drawer = wrapper.findComponent(spec.drawer)
  expect(drawer.props()).toMatchObject({ visible: true, tab: 'info' })
  wrapper.unmount()
}
