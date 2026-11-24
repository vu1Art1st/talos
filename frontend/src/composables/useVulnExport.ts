import { ref } from 'vue'

import client from '../api/client'
import type { QueryParams } from '../types'
import { saveBlob } from '../utils/download'

/** 历史漏洞库 Excel 导出：请求与列表同口径的筛选和排序参数。 */
export function useVulnExport() {
  const exporting = ref(false)

  async function exportExcel(
    params: QueryParams,
    sort: { prop: string; order: string },
    ids: number[] = [],
  ): Promise<void> {
    exporting.value = true
    try {
      const selected = ids.length ? { ids: ids.join(',') } : {}
      const { data } = await client.get<Blob>('/vulns/export', {
        params: { ...params, ...selected, sort: sort.prop, order: sort.order },
        responseType: 'blob',
      })
      saveBlob(data, '历史漏洞库导出.xlsx')
    } finally {
      exporting.value = false
    }
  }

  return { exporting, exportExcel }
}
