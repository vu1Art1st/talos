// 报告 docx 导出后目录域为占位：提示用户手动更新域，或打开 WPS/Word 自动更新域。
// 勾选「不再显示此提示」后记入 localStorage，后续不再弹出。
import { h, type VNode } from 'vue'
import { ElMessageBox } from 'element-plus'

const STORAGE_KEY = 'talos_toc_notice_dismissed'
const CHECKBOX_ID = 'talos-toc-dont-ask'

export function showTocNotice(): void {
  try {
    if (localStorage.getItem(STORAGE_KEY) === '1') return
  } catch {
    /* localStorage 不可用时始终提示 */
  }
  const content = h('div', { style: 'line-height:1.9;font-size:14px' }, [
    h('p', null, '报告的目录域尚未生成，您可通过以下任一方式更新：'),
    h('p', null, [
      '1. 手动更新：全选（Ctrl+A）后按 F9，或右键目录 →「更新域」→「更新整个目录」。',
    ]),
    h('p', null, '报告未增加编辑限制，请添加编辑限制。'),
    h('label', {
      style: 'display:flex;align-items:center;gap:6px;margin-top:14px;cursor:pointer;user-select:none',
    }, [
      h('input', {
        type: 'checkbox',
        id: CHECKBOX_ID,
        style: 'accent-color:var(--el-color-primary)',
      }),
      h('span', null, '不再显示此提示'),
    ]),
  ])
  ElMessageBox({
    title: '报告待办',
    message: content as unknown as VNode,
    type: 'warning',
    confirmButtonText: '知道了',
    beforeClose: (action, _instance, done) => {
      if (action === 'confirm') {
        const el = document.getElementById(CHECKBOX_ID) as HTMLInputElement | null
        if (el?.checked) {
          try {
            localStorage.setItem(STORAGE_KEY, '1')
          } catch {
            /* ignore */
          }
        }
      }
      done()
    },
  }).catch(() => {
    /* 用户直接关闭弹窗 */
  })
}
