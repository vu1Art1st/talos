// CRUD 弹窗三件套：openDialog / 提交保存 / 保存态。消除各列表视图重复的对话框样板。
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'

export interface CrudDialogState<F> {
  dialogVisible: Ref<boolean>
  saving: Ref<boolean>
  form: Ref<F>
  /** 打开弹窗：传入 row 则为编辑（按 empty 重建后合并 row 字段），否则为新建 */
  openDialog: (row?: Partial<F> | null) => void
  /** 提交保存：成功后提示 + 关弹窗 + afterSave 刷新列表；失败保留弹窗 */
  submit: () => Promise<void>
}

export interface CrudDialogOptions<F> {
  /** 新建时的空白表单工厂（每次打开重新求值，避免残留脏数据） */
  empty: () => F
  /** 保存动作（自行区分新增/修改）；抛错时不关弹窗 */
  save: (form: F) => Promise<unknown>
  /** 保存成功后的回调（通常刷新列表） */
  afterSave?: () => unknown
  successMsg?: string
}

export function useCrudDialog<F extends object>(options: CrudDialogOptions<F>): CrudDialogState<F> {
  const dialogVisible = ref(false)
  const saving = ref(false)
  const form = ref(options.empty()) as Ref<F>

  function openDialog(row?: Partial<F> | null) {
    form.value = { ...options.empty(), ...(row ?? {}) } as F
    dialogVisible.value = true
  }

  async function submit() {
    saving.value = true
    try {
      await options.save(form.value)
      ElMessage.success(options.successMsg ?? '保存成功')
      dialogVisible.value = false
      await options.afterSave?.()
    } finally {
      saving.value = false
    }
  }

  return { dialogVisible, saving, form, openDialog, submit }
}
