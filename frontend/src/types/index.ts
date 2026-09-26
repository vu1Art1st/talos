/**
 * 前端领域类型（审计 E-5）。
 *
 * 约定：
 * - 字段名与后端 API 返回一致（snake_case），**只声明代码中真实使用过的字段**，不提前虚构；
 * - 标 `?` 的为「可能不存在 / 按需返回 / 服务端派生只读」字段；
 * - 本文件是这些形状的唯一声明处 —— 页面与 composable 不应再就地复制 `any`。
 * - `any` 仅允许出现在「确实无法静态描述」的边界（如第三方库的松类型），且需注明原因。
 */

/** 查询参数（值类型随端点而异，如 filters 为 JSON 字符串） */
export type QueryParams = Record<string, unknown>

/** 分页响应（对应后端 `Page<T>`） */
export interface Page<T> {
  items: T[]
  total: number
}

/** 旧版分页响应：仅返回 items 的端点（如资产/工单下拉） */
export interface Items<T> {
  items: T[]
}

/** 通用「id + 名称」项（图表系列、下拉候选等） */
export interface IdName {
  id: number
  name: string
}

/** 用户简要信息（测试人员 / 创建人等嵌套场景） */
export interface UserBrief {
  id: number
  username?: string
  realname?: string | null
}

/** 漏洞状态流转候选（后端返回 `[{status, name}]`） */
export interface VulnTransition {
  status: number
  name: string
}

/**
 * 资产公网 URL 条目。
 *
 * 带索引签名是为与 `utils/urls.UrlLike`（`string | { url?; [key: string]: unknown }`）对齐：
 * 该工具函数按「附加字段不参与归一化」设计，故条目类型必须能承载后端扩展的额外字段。
 */
export interface AssetPublicUrl {
  url: string
  /** URL 标签码（`meta.url_tag` 映射名称） */
  tag?: number
  [key: string]: unknown
}

/** 资产端口/服务条目 */
export interface AssetPortService {
  port?: string
  service?: string
}

/** 带版本号的条目标识（中间件 / 数据库） */
export interface AssetNamedVersion {
  name?: string
  version?: string
}

/** 资产负责人条目（手工录入或从组织成员选择） */
export interface AssetOwner {
  id?: number
  name: string
  phone?: string
  email?: string
}

/** 资产（漏洞录入的测试目标 / 工单关联资产 / 资产选择器共用） */
export interface Asset {
  id: number
  name: string
  department?: string | null
  system_type?: string | null
  sub_system?: string | null
  public_urls?: AssetPublicUrl[]
  internal_urls?: string[]
  port_services?: AssetPortService[]
  middlewares?: AssetNamedVersion[]
  databases?: AssetNamedVersion[]
  owners?: AssetOwner[]
  status?: number
  remark?: string | null
}

/** 资产新增/编辑表单模型（`AssetFormDialog` 的 `emptyForm()` 形状） */
export interface AssetForm {
  id: number | null
  name: string
  sub_system: string
  department: string
  system_type: string
  public_urls: AssetPublicUrl[]
  internal_urls: string[]
  port_services: AssetPortService[]
  middlewares: AssetNamedVersion[]
  databases: AssetNamedVersion[]
  owners: AssetOwner[]
  status: number
  remark: string
}

/** 批量导出受理结果（`POST /reports/batch-export` 每份报告一项） */
export interface BatchExportResult {
  job_id: number | string
  report_id?: number
  title?: string
}

/** 组织（资产表单的部门下拉、资产负责人按组织过滤、组织管理列表） */
export interface Group {
  id: number
  name: string
  remark?: string | null
  /** 成员数（组织列表行由成员表聚合而得） */
  member_count?: number
}

/** 角色（用户管理下拉、角色管理列表） */
export interface Role {
  id: number
  name: string
  /** 权限码列表（按分组渲染勾选态） */
  permissions: string[]
  remark?: string | null
}

/** 角色新增/编辑表单模型 */
export type RoleForm = Omit<Role, 'id'> & { id: number | null }

/** 用户（用户管理列表与权限查看） */
export interface User {
  id: number
  username: string
  realname: string
  email?: string | null
  role_id?: number | null
  is_active: boolean
  /** 权限码列表（权限查看弹窗按分组渲染） */
  permissions?: string[]
}

/** 用户新增/编辑表单模型：password 仅新增时必填，编辑留空表示不改 */
export type UserForm = Omit<User, 'id' | 'permissions'> & { id: number | null; password: string }

/** API 令牌（令牌列表） */
export interface ApiToken {
  id: number
  /** 令牌前缀（仅展示用，完整值只在创建时返回一次） */
  prefix: string
  create_time?: string | null
  expires_at?: string | null
  last_used_at?: string | null
}

/** 操作审计日志条目（审计日志列表） */
export interface AuditLogEntry {
  action: string
  create_time?: string | null
  detail?: string | null
  ip?: string | null
  username?: string
  realname?: string
  user_agent?: string | null
}

/** 通知渠道（通知渠道列表 / 表单） */
export interface NotifyChannel {
  id: number
  name: string
  /** 渠道类型码（`meta.notify_channel_types` 映射名称） */
  type: string
  is_active: boolean
  /** 订阅的事件码列表（`meta.notify_events` 映射名称） */
  events: string[]
  /**
   * 渠道配置（随渠道类型不同）。此处显式声明前端实际消费的两个键，
   * 其余键（密钥等）以索引签名放行而不在类型中断言。
   */
  config?: {
    /** Webhook 地址 */
    url?: string
    /** 收件人列表（换行文本与数组互转） */
    recipients?: string[]
    [key: string]: unknown
  } | null
}

/** 漏扫基线工单（非渗透专项） */
export interface NonpenPlan {
  id: number | null
  plan_name: string
  system_name: string
  department: string
  test_type: string
  ticket_id?: string | null
  ticket_id_manual?: string
  ticket_time?: string
  receive_time?: string
  detail?: string | null
  asset_ids?: number[]
  /** 勾选的测试项（键列表） */
  test_items: string[]
  /** 各测试项执行情况：测试项键 → 状态与执行次数 */
  items?: Record<string, {
    status: string
    /** 初测次数（步骤条展示） */
    first_times?: number
    /** 复测次数 */
    retest_times?: number
  }>
  /** 关联资产名称（流程抽屉展示） */
  asset_names?: string[]
  /** 是否已关联流程（流程抽屉据此展示关联态） */
  linked?: boolean
  status?: number
  /** 服务端字段（提交表单时需剔除，故在类型中显式声明以便 Partial 化后 delete） */
  ticket_seq?: number | null
  actionable?: boolean
  testing_plan_id?: number | null
  create_time?: string | null
  update_time?: string | null
}

/** 漏扫基线工单表单模型 */
export type NonpenPlanForm = NonpenPlan & { id: number | null }

/** 组织成员（`GET /group-members/all`，资产负责人下拉数据源 / 组织成员管理） */
export interface GroupMember {
  id?: number
  name: string
  group_id?: number
  phone?: string
  email?: string
  remark?: string | null
}

/**
 * 漏洞录入/编辑表单模型（`VulnFormPanel.emptyVul()` 的形状）。
 *
 * 富文本 JSON 字段为 TipTap 文档结构：由编辑器写入、后端原样回存，前端不做结构访问，
 * 故以 `unknown` 承载（比 `any` 更严：必须显式断言才能取属性）。
 */
export interface VulnForm {
  title: string
  level: number
  vul_type: number
  layer: number
  affected_url: string
  description_html: string
  description_json: unknown
  reproduce_html: string
  reproduce_json: unknown
  solution_html: string
  solution_json: unknown
  source: number
  score: number
  risk_score: number
  left_risk_score: number
  asset_level: number
  cvss_vector: string
  cvss_sync_level: boolean
  /** 编辑态由服务端返回，保存时随 payload 回传 */
  id?: number
  /** 编辑态可改漏洞状态（表单中展示为「漏洞状态」下拉） */
  status?: number
}

/** 专项行动整改工单 */
export interface SpringAction {
  id: number
  report_no: string
  system_name: string
  year: string
  phase: string
  asset_reason?: string
  appeal_success: boolean
  est_score_deduction: number
  score_deduction: number
  doc_no?: string
  vul_ids?: number[]
  /** 关联漏洞（列表展示用；表单提交前须剔除该服务端字段） */
  vuls?: Vuln[]
  report_file_name: string
  report_file_path: string
  report_file_size: number
}

/** 专项行动新增/编辑表单模型（`useCrudDialog.empty` 形状） */
export type SpringActionForm = Omit<SpringAction, 'id'> & { id: number | null }

/** 导入批次（`GET /imports/{id}` 的 batch） */
export interface ImportBatch {
  id: number
  filename: string
  /** 文档类型（展示用） */
  doc_kind?: string | null
  /** 解析出的报告元数据（后端 JSON 列，响应中已是对象；doc_kind === 'report' 时用于展示） */
  meta_json?: {
    system_name?: string
    report_date?: string
    is_retest?: boolean
  } | null
  status?: string
}

/** 导入记录的解析结果行（预览 / 修正 / 批量确认用） */
export interface ImportRecord {
  id: number
  /** parsed 待入库 / confirmed 已入库 / discarded 已丢弃 / failed 解析失败 */
  status: string
  title: string
  level: number
  vul_type: number
  affected_url: string
  /** 已入库时关联的漏洞 ID */
  vul_id?: number | null
  description_html?: string | null
  reproduce_html?: string | null
  solution_html?: string | null
  retest_html?: string | null
  /** 解析失败原因（status === 'failed' 时展示） */
  parse_error?: string | null
}

/** 等级不一致条目（`GET /imports/level-mismatches`；预览横幅与详情弹窗共用） */
export interface ImportLevelMismatch {
  title: string
  level: number
  /** 风险问题汇总的等级 */
  level_summary: number
  level_detail_text?: string | null
  level_summary_text?: string | null
  /** 来源批次文件名（批量导入预览时展示） */
  filename?: string
}

/** 漏洞复测记录（`GET /vulns/{id}/retests`） */
export interface RetestRecord {
  id: number
  /** 自定义标题：留空时列表按创建日期自动生成标题 */
  title?: string | null
  content_html: string
  /** TipTap 富文本 JSON：编辑器写入、后端回存，前端不做结构访问 */
  content_json?: unknown
  /** 复测结论（新增时可一并选择：复测未修复 / 已修复） */
  status?: number | null
  create_time?: string | null
  username?: string
}

/** 远程检测（漏扫基线）工单 */
export interface RemoteTesting {
  id: number
  system_name: string
  notice_time: string
  department: string
  asset_belong: string
  asset_id: number | null
  notified_unit?: string
  is_external: boolean
  vuln_name: string
  /** 漏洞类型：关联漏洞时存字典码，历史数据为直接文本，故声明为 string */
  vuln_type: string
  vuln_id: number | null
  appeal_status: string
  appeal_method?: string
  appeal_file_name: string
  appeal_file_path: string
  appeal_file_size: number
  /** 关联漏洞详情（列表展示与编辑回显） */
  vuln?: Vuln | null
}

/** 远程检测表单模型（`emptyForm()` 形状；新建时 id 为 null） */
export type RemoteTestingForm = Omit<RemoteTesting, 'id' | 'vuln'> & { id: number | null }

/** 表单内待创建的漏洞草稿（远程检测「新增漏洞」快速录入的形状） */
export interface VulnDraft {
  /** 草稿尚未落库，故无 id；模板据此决定是否提供「查看详情」入口 */
  id?: number
  title: string
  level: number
  vul_type: number
  source: number
}

/** 知识库条目（列表行与新增/编辑表单共用字段） */
export interface KnowledgeEntry {
  id: number
  vulnerability_name: string
  vul_type: number
  severity_level: number
  description_html: string
  harm_html: string
  solution_html: string
  /** TipTap 富文本 JSON：编辑器写入、后端回存，前端不做结构访问 */
  description_json?: unknown
  harm_json?: unknown
  solution_json?: unknown
  /** CVSS 向量：表单输入，实时预览评分；未填写时为 ''（非可选） */
  cvss_vector: string
  references?: string[]
  /** 维护人（列表展示） */
  username?: string
  update_time?: string
}

/** 知识库新增/编辑表单模型（`emptyForm()` 形状；新建时 id 为 null） */
export type KnowledgeForm = Omit<KnowledgeEntry, 'id'> & { id: number | null }

/** 知识库模板条目（模板选择器返回；套用模板时用于回填漏洞表单） */
export interface KnowledgeTemplate {
  vulnerability_name: string
  vul_type?: number | null
  description_html?: string | null
  description_json?: unknown
  harm_html?: string | null
  solution_html?: string | null
  solution_json?: unknown
  cvss_vector?: string | null
}

/** 漏洞 */
export interface Vuln {
  id: number
  title: string
  level: number
  status: number
  vul_type?: number
  /** 网络层级（SpringActionList 按关联漏洞聚合展示用） */
  layer?: number
  is_retest?: boolean
  affected_url?: string | null
  /** 关联资产 ID（详情接口返回，编辑表单回填用） */
  asset_ids?: number[]
  /** 关联资产（漏洞列表行的「关联资产」列，仅需名称） */
  assets?: { id?: number; name: string }[]
  /** 所属部门（列表行展示；由关联工单或资产推导） */
  department?: string | null
  /** 漏洞来源码（`meta.vul_source` 映射名称） */
  source?: number
  submit_time?: string | null
  testing_plan_id?: number | null
  /** 历史复测内容（复测记录为空时的回退展示） */
  retest_html?: string | null
  /** 富文本区段（详情展示；富文本 JSON 由 `RichEditor` 写入，故不在此声明） */
  description_html?: string | null
  reproduce_html?: string | null
  solution_html?: string | null
  /** 提交人（详情页编辑权限判定：未关联计划时由提交人或漏洞管理员编辑） */
  submitter_id?: number | null
  cvss_vector?: string | null
  score?: number
  fix_time?: string | null
  notice_time?: string | null
}

/** 漏洞操作日志（`GET /vulns/{id}/logs`，详情页时间线） */
export interface VulnLog {
  id: number
  action: string
  content?: string | null
  username?: string
  realname?: string
  create_time?: string
}

/**
 * axios 错误的最小可读结构：后端业务提示在 `response.data.detail`，
 * 网络类错误只有 `message`；`status` 供版本冲突（409）等分支判定。多处错误提示共用。
 */
export interface ApiErrorShape {
  response?: { data?: { detail?: unknown }; status?: number }
  message?: unknown
}

/** 报告章节关联漏洞的即时状态（`GET /reports/{id}/vuln-states`） */
export interface VulnState {
  vul_id: number
  /** 漏洞状态码（接口必返，章节导航标签据此着色） */
  status: number
  vul_type?: number | null
  /** 等级：可空（未评级时下拉保持禁用，见章节表单的 disabled 判定） */
  level?: number | null
}

/** 透视表单元格（某等级在某部门的 计数 / 已修复 / 未修复） */
export interface VulnPivotLevelCell {
  count: number
  fixed: number
  unfixed: number
}

/** 漏洞统计的部门透视行（Excel 风格交叉表） */
export interface VulnPivotRow {
  department: string
  total: number
  fixed_total: number
  fix_rate: number
  /** 等级码 → 单元格 */
  levels: Record<number, VulnPivotLevelCell>
}

/** 透视表合计行（与数据行同构，供 el-table 的 show-summary 使用） */
export type VulnPivotTotals = Omit<VulnPivotRow, 'department'>

/** 漏洞统计聚合（`GET /vulns/stats`） */
export interface VulnStats {
  total: number
  by_level: LevelCount[]
  /** 修复状态分布：key 为状态标识（如 fixed），供「已修复」卡片取数 */
  by_fix_status: { key: string; count: number }[]
  pivot: { rows: VulnPivotRow[]; totals?: VulnPivotTotals | null }
}

/** 测试报告（工单内报告区 / 导出历史用到的字段） */
export interface Report {
  id: number
  title: string
  actual_mandays?: number | null
  create_time?: string
  /** 本报告所含漏洞是否已全部闭环（已修复/已忽略），用于「复测完成」标注 */
  all_closed?: boolean
  vul_closed?: number
  vul_total?: number
  /** 报告自身是否为复测报告（标题含「复测」） */
  is_retest?: boolean
  /** 报告维度复测状态（后端派生，`plan_service.retest_state_of`） */
  retest_state?: RetestState
}

/** 报告维度复测状态：none 未发起复测 / ongoing 复测中 / done 复测完成 */
export type RetestState = 'none' | 'ongoing' | 'done'

/**
 * 报告详情（报告编辑器用）：在列表字段基础上补基础信息与章节。
 * 描述性字段（customer / project_name / target_ip 等）由用户在编辑器中自由填写或留空。
 */
export interface ReportDetail extends Report {
  sections: ReportSection[]
  customer?: string | null
  project_name?: string | null
  target_ip?: string | null
  test_account?: string | null
  version?: number
  test_start?: string | null
  test_end?: string | null
  author?: string | null
  testing_plan_id?: number | null
  /**
   * 编辑乐观锁版本（后端每次保存 +1）：保存时必须把服务端返回的原值原样回传，
   * 与服务端不一致则 409（见 `views/ReportEditor.vue` 的冲突处理与 `composables/useAutosave.ts`）。
   */
  revision?: number
}

/** 报告导出记录（原声明在 `composables/useExportJobs.ts`，E-5 上提为领域类型） */
export interface ExportJob {
  id: number
  report_id: number
  title?: string | null
  fmt: string
  status: string
  version?: number
  toc_auto_updated?: boolean
  file_size?: number | null
  file_name?: string | null
  create_time?: string
  finish_time?: string
  has_file?: boolean
  /** 失败原因（status === 'failed' 时展示） */
  error?: string | null
}

/** 报告导出格式（与后端导出接口一致） */
export type ExportFormat = 'docx' | 'pdf'

/**
 * 测试工单。
 *
 * 前半部分与表单（`emptyForm()`）字段一一对应，可直接回写；
 * 后半部分为**服务端派生 / 列表摘要（只读）**，保存时须剔除（见 `usePlanCrud.save()`）。
 */
export interface TestingPlan {
  id: number | null
  plan_name: string
  system_name: string
  test_type: string
  department: string
  receive_time: string
  ticket_time: string
  ticket_id_manual: string
  first_test_done_time: string
  retest_notice_time: string
  retest_done_time: string
  status: number
  asset_ids: number[]
  stat_critical: number
  stat_high: number
  stat_medium: number
  stat_low: number
  est_mandays: number
  actual_mandays: number
  actual_mandays_override: boolean
  create_nonpen: boolean
  nonpen_test_items: string[]
  target_urls: string[]
  detail: string
  // ---- 服务端派生 / 列表摘要（只读，不回写）----
  ticket_id?: string
  ticket_seq?: number
  testers?: UserBrief[]
  vuls?: Vuln[]
  reports?: Report[]
  retest_rounds?: RetestRound[]
  retest_round_count?: number
  no_vul_conclusion?: string
}

/** 复测轮次记录（工单「复测轮数」弹层展示） */
export interface RetestRound {
  id: number
  round_no: number
  start_time?: string | null
  done_time?: string | null
  source?: string
  /** 发起本轮的源报告（初测报告）ID；旧数据可能为空 */
  src_report_id?: number | null
}

/** 工单统计聚合（`GET /testing-plans/stats`） */
export interface PlanStats {
  total_plans?: number
  retest_done_plans?: number
  first_test_count?: number
  retest_count?: number
  total_test_count?: number
  est_mandays_total?: number
  actual_mandays_total?: number
  remaining_est_mandays?: number
  vulns_by_month?: { month: string; count: number }[]
}

// ---------- 聚合筛选（条件树：分组嵌套 + 组内/组间 且或非） ----------

/** 聚合筛选字段的枚举/字典候选 */
export interface FilterFieldOption {
  label: string
  value: string | number
}

/** 聚合筛选可选字段定义（与后端字段白名单一一对应） */
export interface FilterFieldDef {
  key: string
  label: string
  type: 'text' | 'number' | 'date' | 'enum'
  options?: FilterFieldOption[]
}

/** 单条筛选条件（叶子节点）；`_uid` 仅供前端渲染 key，不参与请求 */
export interface FilterRule {
  kind: 'rule'
  field: string
  op: string
  value: string | number | (string | number | null)[] | null
  not: boolean
  _uid?: number
}

/** 条件分组（容器节点）：children 按 logic 连接，not 作用于整组 */
export interface FilterGroup {
  kind: 'group'
  logic: 'and' | 'or'
  not: boolean
  children: FilterNode[]
  _uid?: number
}

export type FilterNode = FilterRule | FilterGroup

/** 报告章节（报告编辑器用） */
export interface ReportSection {
  id?: number | null
  title: string
  vul_id?: number | null
  order?: number
  /**
   * 正文 / HTML 等富字段：由后端与富文本编辑器写入，字段多且形态不一，
   * 暂以宽类型承载（本文件允许在「确实无法静态描述」的边界使用 any —— 此处即该边界）。
   */
  [key: string]: any
}

/** 结论附件行（`GET /testing-plans/conclusion` 的 rows） */
export interface PlanConclusionRow {
  ticket_id?: string
  department: string
  system_name: string
  vuln_count: number
  test_type?: string
  first_test_done_time?: string
  retest_done_time?: string
  rectify_state?: string
}

/**
 * 结论聚合（`GET /testing-plans/conclusion`）；各字段可空 —— 组件以 `{}` 初始化，未加载时无值。
 *
 * 口径（2026-09-19）：统计周期命中 = 初测完成 / 复测发起 / 复测完成 / 复测报告生成 任一落入周期；
 * `systems` 为命中工单数（按工单去重），`first_test_*` 与 `retest_*` 分别对应周期内的初测与复测动作。
 */
export interface PlanConclusion {
  summary?: string
  /** 周期括注文字（快捷项名称或起止日期） */
  period_text?: string
  departments?: number
  department_names?: string[]
  systems?: number
  first_test_systems?: number
  first_test_vulns?: number
  retest_systems?: number
  retest_fixed_systems?: number
  retest_unfixed_systems?: number
  retest_started_systems?: number
  retest_report_count?: number
  rows?: PlanConclusionRow[]
}

// ---------------- 安全态势仪表盘（`GET /dashboard/stats`） ----------------

/** 名称 + 计数（状态分布等以名称取色的维度） */
export interface NameCount {
  name: string
  count: number
}

/** 等级分布项（level 码用于展示，name 用于取色） */
export interface LevelCount {
  level: number
  name: string
  count: number
}

/** 漏洞类型分布项（未知类型码归并为「其他」时 type 为 null） */
export interface TypeCount {
  type: number | null
  name: string
  count: number
}

/** 部门安全概况（对应 `stats_service._by_department_stats` 的输出） */
export interface DashboardDepartment {
  department: string
  plans: number
  vulns: number
  high: number
  fixed: number
  /** 未闭环 = 发现数 − 已修复 − 已忽略（已忽略视同闭环） */
  open: number
  /** 修复率；分母为 0（仅有手填统计、无关联漏洞）时为 null，前端展示 `-` */
  fix_rate: number | null
  mandays: number
}

/** 近 12 个月趋势点 */
export interface DashboardTrendPoint {
  month: string
  submitted: number
  fixed: number
}

/** 安全态势聚合结果 */
export interface DashboardStats {
  total_vulns: number
  total_assets: number
  open_vulns: number
  fix_rate: number
  by_status: NameCount[]
  by_level: LevelCount[]
  by_type: TypeCount[]
  by_department: DashboardDepartment[]
  trend: DashboardTrendPoint[]
}
