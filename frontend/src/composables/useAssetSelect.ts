// 资产远程搜索 / 多选回显：下拉展示「系统名（子系统）（系统类型）」，
// 选中资产自动缓存供回显与差集回调。所有选择资产的表单共用。
import { ref, type Ref } from 'vue'
import client from '../api/client'

export interface AssetOption { id: number; label: string }

export interface AssetSelectState {
  assetOptions: Ref<AssetOption[]>
  assetLoading: Ref<boolean>
  assetCache: Ref<Record<number, any>>
  assetLabel: (a: any) => string
  /** 远程搜索；selectedIds 中已选但不在结果内的资产会追加进选项，保证多选回显不为纯数字 */
  searchAssets: (keyword?: string, selectedIds?: number[]) => Promise<void>
  /** 按已选 id 回显标签（编辑进入时调用） */
  loadAssetLabels: (ids: number[]) => Promise<void>
  /** 把新增/新建的资产并入缓存与选项 */
  cacheAsset: (a: any) => void
  /** 计算 ids 相对上次调用的新增差集（用于选中资产自动带出系统名/部门） */
  diffIds: (ids: number[]) => number[]
  /** 重置差集基线（如表单重置/联动填充后） */
  resetBaseline: (ids: number[]) => void
  /** 最近一次搜索关键词（供「以此为名新建资产」等入口取用） */
  lastKeyword: () => string
}

export function useAssetSelect(): AssetSelectState {
  const assetOptions = ref<AssetOption[]>([])
  const assetLoading = ref(false)
  const assetCache = ref<Record<number, any>>({})
  let prevIds: number[] = []
  let lastKeyword = ''

  // 下拉展示：系统名称 +（子系统）+（系统类型，用于区分同名系统的不同环境）
  function assetLabel(a: any) {
    const parts = [a.name]
    if (a.sub_system) parts.push(`（${a.sub_system}）`)
    if (a.system_type) parts.push(`（${a.system_type}）`)
    return parts.join('')
  }

  function cacheAsset(a: any) {
    if (!a?.id) return
    assetCache.value[a.id] = a
    if (!assetOptions.value.some((o) => o.id === a.id)) {
      assetOptions.value.push({ id: a.id, label: assetLabel(a) })
    }
  }

  async function searchAssets(keyword = '', selectedIds: number[] = []) {
    lastKeyword = keyword
    assetLoading.value = true
    try {
      const { data } = await client.get('/assets', { params: { search: keyword, page: 1, size: 50 } })
      const opts: AssetOption[] = data.items.map((a: any) => {
        assetCache.value[a.id] = a
        return { id: a.id, label: assetLabel(a) }
      })
      for (const id of selectedIds) {
        if (!opts.some((o) => o.id === id)) {
          const cached = assetCache.value[id]
          if (cached) opts.push({ id, label: assetLabel(cached) })
        }
      }
      assetOptions.value = opts
    } finally {
      assetLoading.value = false
    }
  }

  async function loadAssetLabels(ids: number[]) {
    if (!ids.length) return
    const rows = await Promise.all(
      ids.map((id) => client.get(`/assets/${id}`).catch(() => null)),
    )
    for (const r of rows) {
      if (r?.data) cacheAsset(r.data)
    }
  }

  function diffIds(ids: number[]) {
    const added = ids.filter((id) => !prevIds.includes(id))
    prevIds = [...ids]
    return added
  }

  function resetBaseline(ids: number[]) {
    prevIds = [...ids]
  }

  return {
    assetOptions, assetLoading, assetCache, assetLabel,
    searchAssets, loadAssetLabels, cacheAsset, diffIds, resetBaseline,
    lastKeyword: () => lastKeyword,
  }
}
