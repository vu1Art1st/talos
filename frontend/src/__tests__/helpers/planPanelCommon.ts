import { flushPromises } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

import { putMock } from './clientMock'

export interface PlanPanelCommonSpec {
  /** describe 标题（由各 spec 自述，如「PlanInfoPanel 工单信息面板」） */
  suite: string
  /** 只读模式必须渲染出的文案（系统名、工单号、测试项状态等） */
  readOnlyTexts: string[]
  /** 「编辑」入口的 data-test 值 */
  editTestId: string
  /** 「保存」按钮的 data-test 值 */
  saveTestId: string
  /** 保存时 PUT 的目标 URL */
  putUrl: string
  /** PUT body 中必须被剔除的只读摘要字段 */
  readonlyFields: string[]
  /** 保存前写入表单的系统名（用于断言提交值） */
  editedSystemName: string
  /** 保存响应夹具（组件保存后会据此刷新表单） */
  putResponse: () => unknown
  /** 挂载面板：调用点自备 plan 夹具、插件与 mock 路由 */
  mountPanel: (mode: 'view' | 'create' | 'edit') => VueWrapper
}

/**
 * 信息面板「只读渲染 / 编辑保存」契约（2 条）。
 *
 * PlanInfoPanel 与 NonpenPlanInfoPanel 的同名用例逐字同构（仅字段与接口路径不同），
 * 集中在此实现，避免两个 spec 各持一份拷贝。
 */
export function describePlanPanelCommon(spec: PlanPanelCommonSpec): void {
  describe(`${spec.suite}：只读与保存契约`, () => {
    it('只读模式渲染工单字段，点击「编辑」发出 request-edit', async () => {
      const wrapper = spec.mountPanel('view')
      await flushPromises()

      for (const text of spec.readOnlyTexts) expect(wrapper.text()).toContain(text)
      const editBtn = wrapper.find(`[data-test="${spec.editTestId}"]`)
      expect(editBtn.exists()).toBe(true)
      await editBtn.trigger('click')
      expect(wrapper.emitted('request-edit')).toHaveLength(1)
      wrapper.unmount()
    })

    it('编辑模式保存时 PUT 去除只读摘要字段并发出 saved', async () => {
      putMock.mockResolvedValue({ data: spec.putResponse() })
      const wrapper = spec.mountPanel('edit')
      await flushPromises()

      const vm = wrapper.vm as unknown as { form: Record<string, unknown> }
      vm.form.system_name = spec.editedSystemName
      await flushPromises()
      await wrapper.find(`[data-test="${spec.saveTestId}"]`).trigger('click')
      await flushPromises()

      expect(putMock).toHaveBeenCalledTimes(1)
      const [url, body] = putMock.mock.calls[0] as [string, Record<string, unknown>]
      expect(url).toBe(spec.putUrl)
      expect(body.system_name).toBe(spec.editedSystemName)
      for (const field of spec.readonlyFields) expect(body).not.toHaveProperty(field)
      expect(wrapper.emitted('saved')).toHaveLength(1)
      wrapper.unmount()
    })
  })
}
