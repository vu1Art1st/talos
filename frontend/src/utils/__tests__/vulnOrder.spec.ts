import { describe, expect, it } from 'vitest'

import { sortPlanVulns } from '../vulnOrder'

const vul = (id: number, level: number, submit_time = '', title = '') => ({
  id, level, submit_time, title,
})

describe('sortPlanVulns', () => {
  it('按危害等级升序分组（level 小=严重在前）', () => {
    const items = [vul(1, 30), vul(2, 10), vul(3, 20)]
    expect(sortPlanVulns(items).map((v) => v.id)).toEqual([2, 3, 1])
  })

  it('同等级有导入序号时按 seq（原报告序号）排序，覆盖错乱的 id 顺序', () => {
    // 历史数据：id 3 是报告第 1 条、id 1 是第 2 条、id 2 是第 3 条
    const importSeq = { 3: 1, 1: 2, 2: 3 }
    const items = [vul(1, 10), vul(2, 10), vul(3, 10)]
    expect(sortPlanVulns(items, importSeq).map((v) => v.id)).toEqual([3, 1, 2])
  })

  it('无映射的漏洞排在同等级有映射的漏洞之后，再按录入时间 / id 兜底', () => {
    const importSeq = { 2: 2, 3: 1 }
    const items = [
      vul(1, 10, '2026-07-20T14:00:00'), // 非导入漏洞
      vul(2, 10),
      vul(3, 10),
    ]
    expect(sortPlanVulns(items, importSeq).map((v) => v.id)).toEqual([3, 2, 1])
  })

  it('全部无映射时回退录入时间升序、id 兜底（原行为）', () => {
    const items = [
      vul(2, 10, '2026-07-20T14:00:00'),
      vul(1, 10, '2026-07-20T14:00:00'),
      vul(3, 10, '2026-07-01T14:00:00'),
    ]
    expect(sortPlanVulns(items).map((v) => v.id)).toEqual([3, 1, 2])
  })

  it('level 缺失视为最低优先级排最后', () => {
    const items = [vul(1, 99), vul(2, 10), { id: 3, level: null, submit_time: '' }]
    expect(sortPlanVulns(items).map((v) => v.id)).toEqual([2, 1, 3])
  })
})
