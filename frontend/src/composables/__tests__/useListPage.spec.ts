import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useListPage } from '../useListPage'

// mock axios client：仅拦截 get 并记录参数
vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(async (_url: string, config?: { params?: Record<string, unknown> }) => ({
      data: { items: [{ id: 1 }], total: 1 },
    })),
  },
 }))

import client from '../../api/client'

const get = vi.mocked(client.get)

beforeEach(() => {
  get.mockClear()
})

describe('useListPage', () => {
  it('load 携带默认分页参数并写入 items/total', async () => {
    const lp = useListPage('/assets')
    await lp.load(2)
    expect(get).toHaveBeenCalledWith('/assets', {
      params: { search: '', page: 2, size: 20, sort: '', order: '' },
    })
    expect(lp.items.value).toEqual([{ id: 1 }])
    expect(lp.total.value).toBe(1)
    expect(lp.page.value).toBe(2)
    // loading 在请求结束后回落
    expect(lp.loading.value).toBe(false)
  })

  it('onSortChange 升序/降序/清空三种形态均回到第一页', async () => {
    const lp = useListPage('/vulns')
    await lp.load(3)
    lp.onSortChange({ prop: 'level', order: 'ascending' })
    await vi.waitFor(() => {
      expect(get).toHaveBeenLastCalledWith('/vulns', {
        params: { search: '', page: 1, size: 20, sort: 'level', order: 'asc' },
      })
    })
    lp.onSortChange({ prop: 'level', order: 'descending' })
    await vi.waitFor(() => {
      expect(get).toHaveBeenLastCalledWith('/vulns', {
        params: { search: '', page: 1, size: 20, sort: 'level', order: 'desc' },
      })
    })
    lp.onSortChange({ prop: 'level', order: null })
    await vi.waitFor(() => {
      expect(get).toHaveBeenLastCalledWith('/vulns', {
        params: { search: '', page: 1, size: 20, sort: '', order: '' },
      })
    })
  })

  it('支持默认排序与 extraParams 钩子（筛选条件每次求值）', async () => {
    let actionable = false
    const lp = useListPage('/nonpen-plans', {
      defaultSort: { prop: 'receive_time', order: 'desc' },
      extraParams: () => (actionable ? { actionable: true } : {}),
    })
    await lp.load()
    expect(get).toHaveBeenLastCalledWith('/nonpen-plans', {
      params: { search: '', page: 1, size: 20, sort: 'receive_time', order: 'desc' },
    })
    actionable = true
    await lp.load()
    expect(get).toHaveBeenLastCalledWith('/nonpen-plans', {
      params: { search: '', page: 1, size: 20, sort: 'receive_time', order: 'desc', actionable: true },
    })
  })

  it('defaultSort 误传 Element Plus 词表（descending/ascending）时归一化为接口词典', async () => {
    const lp = useListPage('/audit/logs', {
      defaultSort: { prop: 'create_time', order: 'descending' },
    })
    await lp.load()
    // 回归用例：曾因 defaultSort 传 'descending' 导致后端按非 desc 处理、日志按时间升序
    expect(get).toHaveBeenLastCalledWith('/audit/logs', {
      params: { search: '', page: 1, size: 20, sort: 'create_time', order: 'desc' },
    })
    expect(lp.sort.order).toBe('desc')

    const lp2 = useListPage('/vulns', { defaultSort: { prop: 'id', order: 'ascending' } })
    await lp2.load()
    expect(lp2.sort.order).toBe('asc')
  })

  it('reload 回到第一页', async () => {
    const lp = useListPage('/reports')
    await lp.load(4)
    await lp.reload()
    expect(lp.page.value).toBe(1)
  })

  it('onSizeChange 更新 size 并携带新 size 回到第一页', async () => {
    const lp = useListPage('/vulns')
    await lp.load(3)
    lp.onSizeChange(50)
    await vi.waitFor(() => {
      expect(get).toHaveBeenLastCalledWith('/vulns', {
        params: { search: '', page: 1, size: 50, sort: '', order: '' },
      })
    })
    expect(lp.size.value).toBe(50)
  })
})
