// 资产录入的部门解析：精确命中直接返回；相似部门先提示更正，拒绝后再询问是否新建。
import { ElMessageBox } from 'element-plus'
import { findSimilarDepartments } from '../utils/deptMatch'
import type { Group } from '../types'

export interface DepartmentResolution {
  /** 命中或更正后的组织 id；自动创建时为 null */
  groupId: number | null
  /** 规范化后的部门名（更正则取组织名） */
  department: string
  /** 是否请求后端自动创建组织 */
  createGroup: boolean
}

function confirm(message: string, title: string, confirmText: string, cancelText: string): Promise<boolean> {
  return ElMessageBox.confirm(message, title, {
    confirmButtonText: confirmText,
    cancelButtonText: cancelText,
    type: 'warning',
  }).then(() => true).catch(() => false)
}

export function useDepartmentResolve() {
  /** 返回 null 表示用户拒绝创建，调用方必须终止保存。 */
  async function resolveDepartment(
    name: string,
    groups: Group[],
  ): Promise<DepartmentResolution | null> {
    const department = (name ?? '').trim()
    if (!department) return { groupId: null, department: '', createGroup: false }

    const exact = groups.find((g) => g.name === department)
    if (exact) return { groupId: exact.id, department: exact.name, createGroup: false }

    const similar = findSimilarDepartments(department, groups)[0]
    if (similar) {
      const correct = await confirm(
        `当前已存在相似部门「${similar.name}」，是否自动更正？`,
        '发现相似部门', '自动更正', '不更正',
      )
      if (correct) return { groupId: similar.id, department: similar.name, createGroup: false }
    }

    const create = await confirm(
      similar
        ? `是否新建部门「${department}」？`
        : `当前无此部门「${department}」，是否自动创建？`,
      '新建部门', '自动创建', '不创建',
    )
    return create ? { groupId: null, department, createGroup: true } : null
  }

  return { resolveDepartment }
}
