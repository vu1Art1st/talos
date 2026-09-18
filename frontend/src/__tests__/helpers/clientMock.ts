import { vi } from 'vitest'

/**
 * 视图/组件冒烟测试共享的 axios client 替身。
 *
 * 背景：4 个 spec 各自复制了一份完全相同的 `vi.mock('../../api/client', ...)` 样板
 * （审计 B-7），接口方法一旦调整需要改 4 处。此处集中一份：
 * - `getMock` 由用例驱动（每个用例在 beforeEach 里 mockReset + mockImplementation）；
 * - `postMock` / `putMock` / `deleteMock` 供交互类用例断言「动作是否触发接口」；
 * - 未显式 mockImplementation 时均返回 undefined（调用方按 no-op 处理）。
 *
 * 用法（spec 中）：
 *   import { clientMockFactory, getMock, postMock } from '../../__tests__/helpers/clientMock'
 *   vi.mock('../../api/client', () => clientMockFactory())
 * 注意：本 import 必须写在被测组件 import 之前，保证工厂被调用时绑定已初始化。
 */
export const getMock = vi.fn()
/** 写操作同样需要断言「接口是否被调用」，故与 getMock 一样导出（用例在 beforeEach 里 mockReset） */
export const postMock = vi.fn()
export const putMock = vi.fn()
export const deleteMock = vi.fn()

export function clientMockFactory() {
  return {
    default: {
      get: (...args: unknown[]) => getMock(...args),
      post: (...args: unknown[]) => postMock(...args),
      put: (...args: unknown[]) => putMock(...args),
      delete: (...args: unknown[]) => deleteMock(...args),
    },
  }
}
