import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clientMockFactory, getMock } from '../../__tests__/helpers/clientMock'

vi.mock('../../api/client', () => clientMockFactory())
vi.mock('../../utils/download', () => ({ saveBlob: vi.fn() }))

import { saveBlob } from '../../utils/download'
import { useVulnExport } from '../useVulnExport'

describe('useVulnExport', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('按当前筛选与排序请求漏洞导出并保存文件', async () => {
    const blob = new Blob(['xlsx'])
    getMock.mockResolvedValue({ data: blob })
    const { exporting, exportExcel } = useVulnExport()

    const pending = exportExcel(
      { search: 'SQL注入', levels: '10,20', statuses: '10', mine: true },
      { prop: 'level', order: 'desc' },
    )
    expect(exporting.value).toBe(true)
    await pending

    expect(getMock).toHaveBeenCalledWith('/vulns/export', {
      params: {
        search: 'SQL注入', levels: '10,20', statuses: '10', mine: true,
        sort: 'level', order: 'desc',
      },
      responseType: 'blob',
    })
    expect(saveBlob).toHaveBeenCalledWith(blob, '历史漏洞库导出.xlsx')
    expect(exporting.value).toBe(false)
  })

  it('传入勾选 ID 时只导出选中漏洞', async () => {
    const blob = new Blob(['xlsx'])
    getMock.mockResolvedValue({ data: blob })
    const { exportExcel } = useVulnExport()

    await exportExcel({ search: 'SQL注入' }, { prop: '', order: '' }, [7, 9])

    expect(getMock).toHaveBeenCalledWith('/vulns/export', {
      params: { search: 'SQL注入', ids: '7,9', sort: '', order: '' },
      responseType: 'blob',
    })
  })
})
