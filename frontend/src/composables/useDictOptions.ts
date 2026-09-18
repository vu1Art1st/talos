// 字典下拉数据源：测试类型 / 部门（组织）。多个视图共用。
import { ref, type Ref } from 'vue'
import client from '../api/client'
import type { Group } from '../types'

export function useDictOptions() {
  const testTypes = ref<string[]>([])
  const departments = ref<string[]>([])

  async function loadTestTypes() {
    // 字典条目只需名称（后端还返回 sort 等字段，此处不消费）
    const { data } = await client.get<{ name: string }[]>('/dict/test_type')
    testTypes.value = data.map((o) => o.name)
  }

  async function loadDepartments() {
    const { data } = await client.get<Group[]>('/groups')
    departments.value = data.map((g) => g.name)
  }

  return { testTypes, departments, loadTestTypes, loadDepartments }
}
