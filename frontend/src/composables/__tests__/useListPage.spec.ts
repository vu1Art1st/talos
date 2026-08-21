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

  it('reload 回到第一页', async () => {
    const lp = useListPage('/reports')
    await lp.load(4)
    await lp.reload()
    expect(lp.page.value).toBe(1)
  })
})
