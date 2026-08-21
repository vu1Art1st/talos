// 字典下拉数据源：测试类型 / 部门（组织）。多个视图共用。
import { ref, type Ref } from 'vue'
import client from '../api/client'

export function useDictOptions() {
  const testTypes = ref<string[]>([])
  const departments = ref<string[]>([])

  async function loadTestTypes() {
    const { data } = await client.get('/dict/test_type')
    testTypes.value = data.map((o: any) => o.name)
  }

  async function loadDepartments() {
    const { data } = await client.get('/groups')
    departments.value = data.map((g: any) => g.name)
  }

  return { testTypes, departments, loadTestTypes, loadDepartments }
}
