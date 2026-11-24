import { afterEach, describe, expect, it, vi } from 'vitest'
import { saveBlob, startUrlDownload } from '../download'

// 浏览器下载 API 在 node 环境不存在，stub 出可断言的替身
function stubDownloadApis() {
  const anchor = { href: '', download: '', rel: '', click: vi.fn() }
  const created: typeof anchor[] = []
  vi.stubGlobal('URL', {
    createObjectURL: vi.fn(() => 'blob:mock-url'),
    revokeObjectURL: vi.fn(),
  })
  vi.stubGlobal('document', {
    createElement: vi.fn(() => {
      created.push(anchor)
      return anchor
    }),
  })
  return { anchor, created }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('startUrlDownload', () => {
  it('直接交给浏览器原生下载管理器，不创建 blob URL', () => {
    const { anchor } = stubDownloadApis()
    startUrlDownload('/api/v1/reports/downloads/abc', '报告.docx')
    expect(anchor.href).toBe('/api/v1/reports/downloads/abc')
    expect(anchor.download).toBe('报告.docx')
    expect(anchor.rel).toBe('noopener')
    expect(anchor.click).toHaveBeenCalledOnce()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
})

describe('saveBlob', () => {
  it('触发一次点击下载并释放 objectURL', () => {
    const { anchor } = stubDownloadApis()
    saveBlob(new Blob(['x']), '资产导出.xlsx')
    expect(anchor.click).toHaveBeenCalledOnce()
    expect(anchor.download).toBe('资产导出.xlsx')
    expect(anchor.href).toBe('blob:mock-url')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })
})
