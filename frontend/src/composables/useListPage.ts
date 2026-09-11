// 列表页骨架：分页 / 排序 / 搜索 / 加载状态。所有列表视图共用，禁止再复制样板。
import { reactive, ref, type Ref } from 'vue'
import client from '../api/client'

export interface ListPageState<T> {
  items: Ref<T[]>
  total: Ref<number>
  page: Ref<number>
  size: Ref<number>
  search: Ref<string>
  sort: { prop: string; order: string }
  loading: Ref<boolean>
  load: (p?: number) => Promise<void>
  reload: () => Promise<void>
  onSortChange: ({ prop, order }: { prop: string; order: string | null }) => void
  onSizeChange: (n: number) => void
}

export interface ListPageOptions {
  /** 每页条数，默认 20 */
  size?: number
  /** 初始排序（如默认按时间倒序的页面）；order 用接口词典 asc/desc（误传 ascending/descending 会自动归一化） */
  defaultSort?: { prop: string; order: string }
  /** 附加查询参数（如筛选条件），每次 load 时求值 */
  extraParams?: () => Record<string, unknown>
}

/** 归一化排序方向：接口只认 asc/desc，兼容误传 Element Plus 的 ascending/descending */
function normalizeOrder(order: string): string {
  if (order === 'ascending') return 'asc'
  if (order === 'descending') return 'desc'
  return order
}

export function useListPage<T = any>(url: string, options: ListPageOptions = {}): ListPageState<T> {
  const items = ref<T[]>([]) as Ref<T[]>
  const total = ref(0)
  const page = ref(1)
  const size = ref(options.size ?? 20)
  const search = ref('')
  const sort = reactive<{ prop: string; order: string }>(
    options.defaultSort
      ? { prop: options.defaultSort.prop, order: normalizeOrder(options.defaultSort.order) }
      : { prop: '', order: '' },
  )
  const loading = ref(false)

  async function load(p = page.value) {
    page.value = p
    loading.value = true
    try {
      const { data } = await client.get(url, {
        params: {
          search: search.value,
          page: p,
          size: size.value,
          sort: sort.prop,
          order: sort.order,
          ...options.extraParams?.(),
        },
      })
      items.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  function reload() {
    return load(1)
  }

  function onSortChange({ prop, order }: { prop: string; order: string | null }) {
    sort.prop = order ? prop : ''
    sort.order = order === 'ascending' ? 'asc' : order === 'descending' ? 'desc' : ''
    load(1)
  }

  function onSizeChange(n: number) {
    size.value = n
    load(1)
  }

  return { items, total, page, size, search, sort, loading, load, reload, onSortChange, onSizeChange }
}
