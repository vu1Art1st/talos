import type { KnowledgeEntry } from '../types'

/** 漏洞模板库导出条目：与后端 KnowledgeBatchIn.items 对齐，可原样再次导入。 */
export interface KnowledgeExportItem {
  vulnerability_name: string
  vul_type: number
  severity_level: number
  description_html: string
  description_json: unknown
  harm_html: string
  harm_json: unknown
  solution_html: string
  solution_json: unknown
  references: string[]
  cvss_vector: string
}

/** 仅保留可回导字段，剔除主键、维护人与时间等运行期元数据。 */
export function buildKnowledgeExport(items: KnowledgeEntry[]): KnowledgeExportItem[] {
  return items.map((item) => ({
    vulnerability_name: item.vulnerability_name,
    vul_type: item.vul_type,
    severity_level: item.severity_level,
    description_html: item.description_html,
    description_json: item.description_json ?? null,
    harm_html: item.harm_html,
    harm_json: item.harm_json ?? null,
    solution_html: item.solution_html,
    solution_json: item.solution_json ?? null,
    references: [...(item.references ?? [])],
    cvss_vector: item.cvss_vector,
  }))
}

/** 生成供下载的 UTF-8 JSON 文本。 */
export function serializeKnowledgeExport(items: KnowledgeEntry[]): string {
  return JSON.stringify(buildKnowledgeExport(items), null, 2)
}
