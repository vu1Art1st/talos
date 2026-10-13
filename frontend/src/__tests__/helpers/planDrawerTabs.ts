import { flushPromises } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

import { getMock } from './clientMock'

export interface PlanDrawerTabsSpec {
  /** describe 标题（由各 spec 自述，如「PlanWorkflowDrawer 工单流程抽屉」） */
  suite: string
  /** 抽屉内嵌的信息面板组件 */
  infoPanel: Component
  /** 工单详情接口（用于断言切标签时不重复拉取） */
  detailUrl: string
  /** 默认「测试流程」标签下应出现的文案（如「录入漏洞」） */
  defaultTabText: string
  /** 信息面板「编辑」入口的 data-test 值 */
  editTestId: string
  /** 挂载抽屉：调用点自备 props 默认值、插件、stubs 与 mock 路由 */
  mountDrawer: (props?: Record<string, unknown>) => VueWrapper
}

/**
 * 抽屉「测试流程 / 工单信息」标签契约（3 条）。
 *
 * PlanWorkflowDrawer 与 NonpenPlanWorkflowDrawer 的这三条用例逐字同构（仅 SUT 与接口路径不同），
 * 集中在此实现，避免两个 spec 各持一份拷贝。
 */
export function describePlanDrawerTabs(spec: PlanDrawerTabsSpec): void {
  describe(`${spec.suite}：标签与信息面板`, () => {
    it('默认落在「测试流程」标签，信息面板不抢先挂载', async () => {
      const wrapper = spec.mountDrawer()
      await flushPromises()

      expect(wrapper.findComponent(spec.infoPanel).exists()).toBe(false)
      expect(wrapper.text()).toContain(spec.defaultTabText)
      wrapper.unmount()
    })

    it('tab=info 时渲染只读信息面板，点击「编辑」切换为表单态', async () => {
      const wrapper = spec.mountDrawer({ tab: 'info' })
      await flushPromises()

      const panel = wrapper.findComponent(spec.infoPanel)
      expect(panel.exists()).toBe(true)
      const panelMode = () => (panel.props() as Record<string, unknown>).mode
      expect(panelMode()).toBe('view')
      expect(wrapper.text()).toContain('工单信息')

      const editBtn = wrapper.find(`[data-test="${spec.editTestId}"]`)
      expect(editBtn.exists(), '管理员应看到编辑入口').toBe(true)
      await editBtn.trigger('click')
      await flushPromises()
      expect(panelMode()).toBe('edit')
      wrapper.unmount()
    })

    it('切换标签只更新 tab，不重复拉取工单详情', async () => {
      const wrapper = spec.mountDrawer()
      await flushPromises()
      const detailCalls = () => getMock.mock.calls.filter((c) => c[0] === spec.detailUrl).length
      const before = detailCalls()

      const infoTab = wrapper.findAll('.el-tabs__item').find((n) => n.text() === '工单信息')
      expect(infoTab, '工单信息标签应可见').toBeTruthy()
      await infoTab!.trigger('click')
      await flushPromises()

      expect(wrapper.emitted('update:tab')?.at(-1)).toEqual(['info'])
      expect(detailCalls()).toBe(before)
      wrapper.unmount()
    })
  })
}
