// 列表页骨架：分页 / 排序 / 搜索 / 加载状态。所有列表视图共用，禁止再复制样板。
import { reactive, ref, type Ref } from 'vue'
import client from '../api/client'

export interface ListPageState<T> {
  items: Ref<T[]>
  total: Ref<number>
  page: Ref<number>
  search: Ref<string>
  sort: { prop: string; order: string }
  loading: Ref<boolean>
  load: (p?: number) => Promise<void>
  reload: () => Promise<void>
  onSortChange: ({ prop, order }: { prop: string; order: string | null }) => void
}

export interface ListPageOptions {
  /** 每页条数，默认 20 */
  size?: number
  /** 初始排序（如默认按时间倒序的页面） */
  defaultSort?: { prop: string; order: string }
  /** 附加查询参数（如筛选条件），每次 load 时求值 */
  extraParams?: () => Record<string, unknown>
}

export function useListPage<T = any>(url: string, options: ListPageOptions = {}): ListPageState<T> {
  const items = ref<T[]>([]) as Ref<T[]>
  const total = ref(0)
  const page = ref(1)
  const search = ref('')
  const sort = reactive<{ prop: string; order: string }>(
    options.defaultSort ? { ...options.defaultSort } : { prop: '', order: '' },
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
          size: options.size ?? 20,
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

  return { items, total, page, search, sort, loading, load, reload, onSortChange }
}
