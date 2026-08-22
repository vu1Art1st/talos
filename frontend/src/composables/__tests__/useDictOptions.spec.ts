import { describe, expect, it, vi } from 'vitest'
import { useDictOptions } from '../useDictOptions'

// mock axios client：字典接口与组织接口各回固定数据
vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(async (url: string) => {
      if (url === '/dict/test_type') {
        return { data: [{ name: '渗透测试' }, { name: '漏扫基线' }] }
      }
      if (url === '/groups') {
        return { data: [{ name: '电商事业部' }, { name: '金融事业部' }] }
      }
      return { data: [] }
    }),
  },
}))

describe('useDictOptions', () => {
  it('loadTestTypes 拉取字典并映射为名称数组', async () => {
    const { testTypes, loadTestTypes } = useDictOptions()
    await loadTestTypes()
    expect(testTypes.value).toEqual(['渗透测试', '漏扫基线'])
  })

  it('loadDepartments 拉取组织并映射为名称数组', async () => {
    const { departments, loadDepartments } = useDictOptions()
    await loadDepartments()
    expect(departments.value).toEqual(['电商事业部', '金融事业部'])
  })
})
