import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCrudDialog } from '../useCrudDialog'

// mock element-plus：仅用到 ElMessage.success
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn() },
}))

import { ElMessage } from 'element-plus'

interface Row { id: number | null; name: string }

function createState(hooks: { save?: (form: Row) => Promise<unknown>; afterSave?: () => unknown } = {}) {
  return useCrudDialog<Row>({
    empty: () => ({ id: null, name: '' }),
    save: hooks.save ?? vi.fn(async () => undefined),
    afterSave: hooks.afterSave,
    successMsg: '已保存',
  })
}

beforeEach(() => {
  vi.mocked(ElMessage.success).mockClear()
})

describe('useCrudDialog', () => {
  it('openDialog 新建：表单为 empty 工厂的全新对象', () => {
    const { form, dialogVisible, openDialog } = createState()
    openDialog()
    expect(form.value).toEqual({ id: null, name: '' })
    expect(dialogVisible.value).toBe(true)
  })

  it('openDialog 编辑：empty 重建后合并 row 字段（避免脏数据残留）', () => {
    const { form, openDialog } = createState()
    openDialog({ id: 7, name: '远程检测A' })
    expect(form.value).toEqual({ id: 7, name: '远程检测A' })
  })

  it('submit 成功：提示、关弹窗、回调 afterSave，saving 复位', async () => {
    const afterSave = vi.fn()
    const { dialogVisible, saving, submit } = createState({ afterSave })
    await submit()
    expect(ElMessage.success).toHaveBeenCalledWith('已保存')
    expect(dialogVisible.value).toBe(false)
    expect(afterSave).toHaveBeenCalledTimes(1)
    expect(saving.value).toBe(false)
  })

  it('submit 失败：保存抛错时保留弹窗，saving 仍复位', async () => {
    const { dialogVisible, saving, openDialog, submit } = createState({
      save: vi.fn(async () => {
        throw new Error('服务器错误')
      }),
    })
    openDialog()
    await expect(submit()).rejects.toThrow('服务器错误')
    expect(dialogVisible.value).toBe(true)
    expect(saving.value).toBe(false)
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('openDialog 再次打开时表单不残留上一次的编辑值', () => {
    const { form, openDialog } = createState()
    openDialog({ id: 7, name: '远程检测A' })
    openDialog()
    expect(form.value.id).toBeNull()
    expect(form.value.name).toBe('')
  })
})
