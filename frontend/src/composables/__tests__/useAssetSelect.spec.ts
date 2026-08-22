import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAssetSelect } from '../useAssetSelect'

// mock axios client：get 按 URL 分发固定数据
vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(async (url: string) => {
      if (url === '/assets') {
        return { data: { items: [{ id: 2, name: '商城系统', sub_system: '订单中心' }] } }
      }
      if (url === '/assets/1') {
        return { data: { id: 1, name: '门户系统', system_type: '自有系统（正式）' } }
      }
      return Promise.reject(new Error('404'))
    }),
  },
}))

import client from '../../api/client'

const get = vi.mocked(client.get)

beforeEach(() => {
  get.mockClear()
})

describe('useAssetSelect', () => {
  it('assetLabel 拼接：仅系统名 / +（子系统）/ +（系统类型）', () => {
    const { assetLabel } = useAssetSelect()
    expect(assetLabel({ name: '门户系统' })).toBe('门户系统')
    expect(assetLabel({ name: '商城系统', sub_system: '订单中心' })).toBe('商城系统（订单中心）')
    expect(assetLabel({ name: '门户系统', system_type: '自有系统（正式）' })).toBe('门户系统（自有系统（正式））')
  })

  it('searchAssets 写入选项并缓存结果，记录最近关键词', async () => {
    const s = useAssetSelect()
    await s.searchAssets('商城')
    expect(get).toHaveBeenCalledWith('/assets', { params: { search: '商城', page: 1, size: 50 } })
    expect(s.assetOptions.value).toEqual([{ id: 2, label: '商城系统（订单中心）' }])
    expect(s.assetCache.value[2].name).toBe('商城系统')
    expect(s.lastKeyword()).toBe('商城')
    expect(s.assetLoading.value).toBe(false)
  })

  it('searchAssets 回显合并：已选但不在结果内的缓存项追加进选项', async () => {
    const s = useAssetSelect()
    // 先搜索把 id=2 写入缓存
    await s.searchAssets()
    // 换关键词后 id=2 不在结果内，但作为已选项仍需回显
    get.mockResolvedValueOnce({ data: { items: [{ id: 3, name: '办公系统' }] } })
    await s.searchAssets('办公', [2, 99])
    expect(s.assetOptions.value.map((o) => o.id)).toEqual([3, 2])
  })

  it('loadAssetLabels 并发加载并容错：失败的 id 静默跳过', async () => {
    const s = useAssetSelect()
    // id=1 返回数据、id=9 抛 404，整体不抛错且只并入成功的资产
    await s.loadAssetLabels([1, 9])
    expect(s.assetCache.value[1].name).toBe('门户系统')
    expect(s.assetOptions.value).toEqual([{ id: 1, label: '门户系统（自有系统（正式））' }])
  })

  it('cacheAsset 并入缓存与选项，重复调用不产生重复选项', () => {
    const s = useAssetSelect()
    s.cacheAsset({ id: 5, name: '新系统' })
    s.cacheAsset({ id: 5, name: '新系统' })
    expect(s.assetOptions.value).toEqual([{ id: 5, label: '新系统' }])
    // 空 id 直接忽略
    s.cacheAsset(null)
    expect(s.assetOptions.value).toHaveLength(1)
  })

  it('diffIds 只返回新增差集并推进基线，resetBaseline 重置', () => {
    const s = useAssetSelect()
    expect(s.diffIds([1, 2])).toEqual([1, 2])
    expect(s.diffIds([2, 3])).toEqual([3])
    expect(s.diffIds([2, 3])).toEqual([])
    s.resetBaseline([2, 3])
    expect(s.diffIds([2, 3])).toEqual([])
  })
})
