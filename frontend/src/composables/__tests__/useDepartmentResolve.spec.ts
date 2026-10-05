import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'
import { useDepartmentResolve } from '../useDepartmentResolve'
import type { Group } from '../../types'

vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: vi.fn() },
}))

function group(id: number, name: string): Group {
  return { id, name, remark: '' }
}

const groups = [group(1, '集成服务部'), group(2, '财务部')]

beforeEach(() => {
  vi.mocked(ElMessageBox.confirm).mockReset()
})

describe('useDepartmentResolve', () => {
  it('精确命中：直接返回组织，不弹窗', async () => {
    const { resolveDepartment } = useDepartmentResolve()
    await expect(resolveDepartment('集成服务部', groups)).resolves.toEqual({
      groupId: 1, department: '集成服务部', createGroup: false,
    })
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
  })

  it('相似部门选择更正：使用既有组织，不创建', async () => {
    vi.mocked(ElMessageBox.confirm).mockResolvedValueOnce('confirm' as never)
    const { resolveDepartment } = useDepartmentResolve()
    await expect(resolveDepartment('集成部', groups)).resolves.toEqual({
      groupId: 1, department: '集成服务部', createGroup: false,
    })
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
  })

  it('相似部门拒绝更正后选择创建：进入自动创建分支', async () => {
    vi.mocked(ElMessageBox.confirm)
      .mockRejectedValueOnce(new Error('cancel'))
      .mockResolvedValueOnce('confirm' as never)
    const { resolveDepartment } = useDepartmentResolve()
    await expect(resolveDepartment('集成部', groups)).resolves.toEqual({
      groupId: null, department: '集成部', createGroup: true,
    })
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(2)
  })

  it('无相似部门：一次确认后自动创建', async () => {
    vi.mocked(ElMessageBox.confirm).mockResolvedValueOnce('confirm' as never)
    const { resolveDepartment } = useDepartmentResolve()
    await expect(resolveDepartment('市场部', groups)).resolves.toEqual({
      groupId: null, department: '市场部', createGroup: true,
    })
  })

  it('两次都拒绝：返回 null，调用方终止保存', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue(new Error('cancel'))
    const { resolveDepartment } = useDepartmentResolve()
    await expect(resolveDepartment('集成部', groups)).resolves.toBeNull()
  })

  it('部门为空：不弹窗，返回空解析', async () => {
    const { resolveDepartment } = useDepartmentResolve()
    await expect(resolveDepartment('  ', groups)).resolves.toEqual({
      groupId: null, department: '', createGroup: false,
    })
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
  })
})
