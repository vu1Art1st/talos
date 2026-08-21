import { afterEach, describe, expect, it, vi } from 'vitest'
import { saveBlob, saveReportBlob } from '../download'

// 浏览器下载 API 在 node 环境不存在，stub 出可断言的替身
function stubDownloadApis() {
  const anchor = { href: '', download: '', click: vi.fn() }
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

describe('saveReportBlob', () => {
  it('docx 且目录域未自动更新时提示手动更新域', async () => {
    const { anchor } = stubDownloadApis()
    const toc = await import('../tocNotice')
    const spy = vi.spyOn(toc, 'showTocNotice').mockImplementation(() => {})
    saveReportBlob(new Blob(['x']), { title: '周报', fmt: 'docx', toc_auto_updated: false })
    expect(anchor.download).toBe('周报.docx')
    expect(spy).toHaveBeenCalledOnce()
    spy.mockRestore()
  })

  it('pdf 或已自动更新目录时不提示', async () => {
    stubDownloadApis()
    const toc = await import('../tocNotice')
    const spy = vi.spyOn(toc, 'showTocNotice').mockImplementation(() => {})
    saveReportBlob(new Blob(['x']), { fmt: 'pdf', toc_auto_updated: false }, 'fallback')
    saveReportBlob(new Blob(['x']), { fmt: 'docx', toc_auto_updated: true }, 'fallback')
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('无标题时使用 fallbackTitle', () => {
    const { anchor } = stubDownloadApis()
    saveReportBlob(new Blob(['x']), { fmt: 'docx', toc_auto_updated: true }, '某系统')
    expect(anchor.download).toBe('某系统.docx')
  })
})
