import { describe, expect, it } from 'vitest'

import { buildKnowledgeExport, serializeKnowledgeExport } from '../knowledgeExport'
import type { KnowledgeEntry } from '../../types'

const entry = (id: number, name: string): KnowledgeEntry => ({
  id,
  vulnerability_name: name,
  vul_type: 10,
  severity_level: 20,
  description_html: `<p>${name}描述</p>`,
  description_json: { type: 'doc', content: [name] },
  harm_html: `<p>${name}危害</p>`,
  harm_json: { type: 'doc', content: [`${name}危害`] },
  solution_html: `<p>${name}建议</p>`,
  solution_json: { type: 'doc', content: [`${name}建议`] },
  references: ['https://example.com/ref'],
  cvss_vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
  username: '维护人',
  update_time: '2026-10-11T12:00:00',
})

describe('knowledgeExport', () => {
  it('保留可回导字段与富文本 JSON，剔除运行时元数据', () => {
    const [item] = buildKnowledgeExport([entry(7, 'SQL注入')])

    expect(item).toEqual({
      vulnerability_name: 'SQL注入',
      vul_type: 10,
      severity_level: 20,
      description_html: '<p>SQL注入描述</p>',
      description_json: { type: 'doc', content: ['SQL注入'] },
      harm_html: '<p>SQL注入危害</p>',
      harm_json: { type: 'doc', content: ['SQL注入危害'] },
      solution_html: '<p>SQL注入建议</p>',
      solution_json: { type: 'doc', content: ['SQL注入建议'] },
      references: ['https://example.com/ref'],
      cvss_vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
    })
    expect(item).not.toHaveProperty('id')
    expect(item).not.toHaveProperty('username')
    expect(item).not.toHaveProperty('update_time')
  })

  it('按当前列表顺序序列化，并可被 JSON.parse 直接回读', () => {
    const text = serializeKnowledgeExport([entry(1, '甲'), entry(2, '乙')])
    const parsed = JSON.parse(text)

    expect(parsed.map((item: { vulnerability_name: string }) => item.vulnerability_name)).toEqual(['甲', '乙'])
  })
})
