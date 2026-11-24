// 统一文件下载入口：报告走原生 URL 下载，其余小文件走 blob 保存。

/** 触发浏览器原生下载：由浏览器下载管理器负责进度、暂停与断点续传。 */
export function startUrlDownload(url: string, filename: string): void {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  a.click()
}

/** 触发浏览器保存 blob 到本地文件。 */
export function saveBlob(data: Blob, filename: string): void {
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
