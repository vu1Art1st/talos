// 漏洞模板库接口封装（跨模板全局搜索 + 条目详情）。
// 仅作为 client.ts 的薄封装，统一参数序列化（多选字典以逗号分隔下发），不引入额外依赖。
import client from './client'

/** 搜索结果条目（轻量）：正文由 getKnowledgeEntry 按需获取 */
export interface KnowledgeSearchItem {
  id: number
  vulnerability_name: string
  vul_type: number
  /** 所属模板（漏洞类型）名称，服务端按 vuln_types 动态字典解析 */
  vul_type_name: string
  severity_level: number
  /** 描述（缺失时退危害/修复建议）剥离 HTML 后的纯文本摘要 */
  summary: string
  username: string
  update_time: string | null
  /** 命中位置：name / references / content */
  matched_field: string
}

export interface KnowledgeSearchParams {
  q?: string
  /** 漏洞类型字典码多选；留空即跨模板全局搜索 */
  vul_type?: number[]
  severity_level?: number[]
  creator?: string
  updated_from?: string
  updated_to?: string
  /** 是否把描述/危害/修复建议正文纳入匹配 */
  deep?: boolean
  /** relevance（默认）/ update_time / severity_level / name */
  sort?: string
  order?: 'asc' | 'desc'
  page?: number
  size?: number
}

export interface KnowledgeSearchResult {
  total: number
  items: KnowledgeSearchItem[]
}

/** 跨模板搜索漏洞模板（GET /knowledge/search） */
export function searchKnowledge(params: KnowledgeSearchParams) {
  return client.get<KnowledgeSearchResult>('/knowledge/search', {
    params: {
      ...params,
      vul_type: params.vul_type?.length ? params.vul_type.join(',') : undefined,
      severity_level: params.severity_level?.length ? params.severity_level.join(',') : undefined,
    },
  })
}

/** 按 ID 取完整条目（含描述 / 危害 / 修复建议 / CVSS 向量），用于套用模板回填 */
export function getKnowledgeEntry(id: number) {
  return client.get('/knowledge/' + id)
}
