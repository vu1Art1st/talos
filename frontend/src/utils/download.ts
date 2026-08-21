// 统一 blob 下载入口：全站文件保存必须走此处，禁止视图内散落 createElement 样板。
import { showTocNotice } from './tocNotice'

/** 触发浏览器保存 blob 到本地文件。 */
export function saveBlob(data: Blob, filename: string): void {
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** 保存报告导出文件；docx 且目录域未自动更新时提示用户手动更新域（可勾选不再提示）。 */
export function saveReportBlob(
  data: Blob,
  job: { title?: string | null; fmt: string; toc_auto_updated?: boolean },
  fallbackTitle = 'report',
): void {
  saveBlob(data, `${job.title || fallbackTitle}.${job.fmt}`)
  if (job.fmt === 'docx' && !job.toc_auto_updated) {
    showTocNotice()
  }
}
