/**
 * 聚合筛选条件树工具（纯逻辑，无框架依赖）。
 *
 * 结构：分组（`FilterGroup`，可嵌套，上限 `MAX_FILTER_DEPTH`）内含「条件（`FilterRule`）或子分组」；
 * 组内子节点按组自身 `logic`（且 / 或）连接，组的 `not` 作用于整组，组与组之间再由父级 `logic` 连接。
 * **优先级完全由嵌套层级表达**（先算括号内），不存在隐式优先级 —— 与后端
 * `app/core/filters.py` 的解析与表达式构造口径一一对应，改这里必须同步改后端与两侧单测。
 *
 * 兼容历史扁平格式 `[{field, op, value, not, connector}]`：规则间 connector 左结合
 * （`a AND b OR c` ≡ `(a AND b) OR c`），归一化时折叠为等价嵌套树。
 */
import type { FilterFieldDef, FilterGroup, FilterNode, FilterRule } from '../types'

/** 分组嵌套上限（与后端 `core/filters.MAX_FILTER_DEPTH` 保持一致） */
export const MAX_FILTER_DEPTH = 5

export interface FilterOpOption {
  value: string
  label: string
}

/** 各字段类型可用操作符（下拉与表达式预览共用同一份文案） */
export const OP_OPTIONS_BY_TYPE: Record<FilterFieldDef['type'], FilterOpOption[]> = {
  text: [
    { value: 'contains', label: '包含' },
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'starts_with', label: '开头为' },
    { value: 'ends_with', label: '结尾为' },
    { value: 'is_empty', label: '为空' },
  ],
  enum: [
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'is_empty', label: '为空' },
  ],
  number: [
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'gt', label: '大于' },
    { value: 'gte', label: '大于等于' },
    { value: 'lt', label: '小于' },
    { value: 'lte', label: '小于等于' },
    { value: 'between', label: '区间' },
    { value: 'is_empty', label: '为空' },
  ],
  date: [
    { value: 'eq', label: '等于' },
    { value: 'ne', label: '不等于' },
    { value: 'gt', label: '晚于' },
    { value: 'gte', label: '不早于' },
    { value: 'lt', label: '早于' },
    { value: 'lte', label: '不晚于' },
    { value: 'between', label: '区间' },
    { value: 'is_empty', label: '为空' },
  ],
}

/** 操作符展示名（历史数据的未知操作符兜底显示原值） */
export const OP_LABELS: Record<string, string> = Object.fromEntries(
  Object.values(OP_OPTIONS_BY_TYPE).flat().map((o) => [o.value, o.label] as const),
)

/** 各字段类型切换字段时的默认操作符 */
export const DEFAULT_OP_BY_TYPE: Record<FilterFieldDef['type'], string> = {
  text: 'contains',
  enum: 'eq',
  number: 'eq',
  date: 'eq',
}

/** 序列化载荷（请求体形态：仅保留后端需要的字段） */
export interface FilterRulePayload {
  kind: 'rule'
  field: string
  op: string
  value: FilterRule['value']
  not: boolean
}

export interface FilterGroupPayload {
  logic: 'and' | 'or'
  not: boolean
  children: (FilterGroupPayload | FilterRulePayload)[]
}

let uidSeq = 1
function nextUid(): number {
  return uidSeq++
}

export function isFilterGroup(node: FilterNode): node is FilterGroup {
  return node.kind === 'group'
}

/** 需要填写取值的操作符（为空类操作符不需要） */
export function filterOpNeedsValue(op: string): boolean {
  return !['is_empty', 'is_not_empty'].includes(op)
}

export function createFilterGroup(): FilterGroup {
  return { kind: 'group', logic: 'and', not: false, children: [], _uid: nextUid() }
}

function defaultRuleValue(field: FilterFieldDef | undefined, op: string): FilterRule['value'] {
  if (op === 'between') return [null, null]
  if (!filterOpNeedsValue(op)) return null
  return field?.type === 'number' ? null : ''
}

export function createFilterRule(fields: FilterFieldDef[]): FilterRule {
  const field = fields[0]
  const op = DEFAULT_OP_BY_TYPE[field?.type ?? 'text']
  return {
    kind: 'rule',
    field: field?.key ?? '',
    op,
    value: defaultRuleValue(field, op),
    not: false,
    _uid: nextUid(),
  }
}

export function fieldOf(fields: FilterFieldDef[], key: string): FilterFieldDef | undefined {
  return fields.find((f) => f.key === key)
}

/** 规则当前字段可用的操作符列表 */
export function opOptionsOf(rule: FilterRule, fields: FilterFieldDef[]): FilterOpOption[] {
  return OP_OPTIONS_BY_TYPE[fieldOf(fields, rule.field)?.type ?? 'text']
}

/** 切换字段：操作符与取值一并重置为该字段类型的默认形态 */
export function applyFilterRuleField(rule: FilterRule, fields: FilterFieldDef[]): void {
  const field = fieldOf(fields, rule.field)
  rule.op = DEFAULT_OP_BY_TYPE[field?.type ?? 'text']
  rule.value = defaultRuleValue(field, rule.op)
}

/** 切换操作符：取值重置（区间 → 双值数组，为空类 → 无值） */
export function applyFilterRuleOp(rule: FilterRule, fields: FilterFieldDef[]): void {
  rule.value = defaultRuleValue(fieldOf(fields, rule.field), rule.op)
}

/** 条件是否填写完整（不完整的规则不参与请求，但仍保留在界面上供继续编辑） */
export function isFilterRuleComplete(rule: FilterRule): boolean {
  if (!filterOpNeedsValue(rule.op)) return true
  if (rule.op === 'between') {
    if (!Array.isArray(rule.value) || rule.value.length !== 2) return false
    const [lo, hi] = rule.value
    return lo !== null && lo !== '' && hi !== null && hi !== ''
  }
  return rule.value !== null && rule.value !== ''
}

function normalizeValue(value: unknown): FilterRule['value'] {
  if (Array.isArray(value)) {
    return value.map((v) => (typeof v === 'number' || typeof v === 'string' ? v : null))
  }
  if (typeof value === 'number' || typeof value === 'string') return value
  // 空值保持 null：数值字段的 el-input-number 只接受 Number | Null，转成空串会触发 prop 校验告警
  return value == null ? null : String(value)
}

function toRule(raw: Record<string, unknown>, allowedFields?: ReadonlySet<string>): FilterRule | null {
  const field = typeof raw.field === 'string' ? raw.field : ''
  const op = typeof raw.op === 'string' ? raw.op : ''
  if (!field || !op) return null
  if (allowedFields && !allowedFields.has(field)) return null
  return { kind: 'rule', field, op, value: normalizeValue(raw.value), not: raw.not === true, _uid: nextUid() }
}

/** 把新规则并入左结合折叠结果：同逻辑同层级继续平铺，否则另起一层分组 */
function appendLegacyRule(node: FilterNode, leaf: FilterRule, logic: 'and' | 'or'): FilterNode {
  if (node.kind === 'group' && node.logic === logic && !node.not) {
    node.children.push(leaf)
    return node
  }
  return { kind: 'group', logic, not: false, children: [node, leaf], _uid: nextUid() }
}

/** 历史扁平格式 → 等价嵌套树（逐条左结合折叠） */
function foldLegacyRules(rules: unknown, allowedFields?: ReadonlySet<string>): FilterGroup {
  let node: FilterNode | null = null
  for (const raw of Array.isArray(rules) ? rules : []) {
    if (!raw || typeof raw !== 'object') continue
    const item = raw as Record<string, unknown>
    const leaf = toRule(item, allowedFields)
    if (!leaf) continue
    if (!node) {
      node = leaf
      continue
    }
    node = appendLegacyRule(node, leaf, item.connector === 'or' ? 'or' : 'and')
  }
  if (!node) return createFilterGroup()
  return node.kind === 'group'
    ? node
    : { kind: 'group', logic: 'and', not: false, children: [node], _uid: nextUid() }
}

function normalizeGroup(node: unknown, allowedFields: ReadonlySet<string> | undefined, depth: number): FilterGroup {
  const group = createFilterGroup()
  if (!node || typeof node !== 'object' || depth > MAX_FILTER_DEPTH) return group
  const raw = node as Record<string, unknown>
  group.logic = raw.logic === 'or' ? 'or' : 'and'
  group.not = raw.not === true
  for (const child of Array.isArray(raw.children) ? raw.children : []) {
    if (!child || typeof child !== 'object') continue
    const item = child as Record<string, unknown>
    if (item.kind === 'group' || Array.isArray(item.children)) {
      group.children.push(normalizeGroup(item, allowedFields, depth + 1))
    } else {
      const rule = toRule(item, allowedFields)
      if (rule) group.children.push(rule)
    }
  }
  return group
}

/**
 * 任意来源（localStorage / 接口 / 手改数据）→ 规范化条件树。
 *
 * @param input        历史扁平数组、`{rules}` 或 v2 分组对象
 * @param allowedFields 传入时按字段白名单过滤（用于不可信来源，如 localStorage）
 */
export function normalizeFilterTree(input: unknown, allowedFields?: ReadonlySet<string>): FilterGroup {
  if (Array.isArray(input)) return foldLegacyRules(input, allowedFields)
  if (input && typeof input === 'object') {
    const raw = input as Record<string, unknown>
    if (!('children' in raw) && 'rules' in raw) return foldLegacyRules(raw.rules, allowedFields)
  }
  return normalizeGroup(input, allowedFields, 1)
}

/** 深拷贝（避免编辑器改动污染父级持有的对象） */
export function cloneFilterNode<T extends FilterNode>(node: T): T {
  if (isFilterGroup(node)) {
    return { ...node, children: node.children.map(cloneFilterNode) } as T
  }
  return { ...node, value: Array.isArray(node.value) ? [...node.value] : node.value } as T
}

/** 结构比较（忽略 `_uid`）：用于判断外部传入值是否需要重建内部状态 */
export function filterTreeEquals(a: FilterNode | undefined, b: FilterNode | undefined): boolean {
  if (!a || !b) return a === b
  if (isFilterGroup(a) || isFilterGroup(b)) {
    if (!isFilterGroup(a) || !isFilterGroup(b)) return false
    if (a.logic !== b.logic || a.not !== b.not || a.children.length !== b.children.length) return false
    return a.children.every((child, i) => filterTreeEquals(child, b.children[i]))
  }
  return a.field === b.field && a.op === b.op && a.not === b.not
    && JSON.stringify(a.value ?? null) === JSON.stringify(b.value ?? null)
}

export function countFilterRules(node: FilterNode): number {
  if (!isFilterGroup(node)) return 1
  return node.children.reduce((sum, child) => sum + countFilterRules(child), 0)
}

/** 剔除未填完整的条件与随之变空的分组（请求与计数都以剪枝后的树为准） */
export function pruneFilterTree(group: FilterGroup): FilterGroup {
  const children: FilterNode[] = []
  for (const child of group.children) {
    if (isFilterGroup(child)) {
      const kept = pruneFilterTree(child)
      if (kept.children.length) children.push(kept)
    } else if (isFilterRuleComplete(child)) {
      children.push(child)
    }
  }
  return { ...group, children }
}

/** 条件树 → 请求载荷（剥离 `_uid` 等前端字段） */
export function filterTreeToPayload(group: FilterGroup): FilterGroupPayload {
  return {
    logic: group.logic,
    not: group.not,
    children: group.children.map((child) => (
      isFilterGroup(child)
        ? filterTreeToPayload(child)
        : { kind: 'rule' as const, field: child.field, op: child.op, value: child.value, not: child.not }
    )),
  }
}

function optionLabel(field: FilterFieldDef | undefined, value: FilterRule['value']): string {
  if (Array.isArray(value) || value === null) return '?'
  const hit = field?.options?.find((o) => String(o.value) === String(value))
  return hit ? hit.label : String(value)
}

/**
 * 操作符展示名（**按字段类型取词**）。
 *
 * 同一操作符在不同字段类型下文案不同（number 的 `gte` 是「大于等于」、date 的是「不早于」），
 * 而全局 `OP_LABELS` 按操作符做键、后写入者覆盖前者（date 覆盖 number），
 * 直接用会让人天等数值字段的预览与操作符下拉文案不一致 —— 故先按当前字段类型取词。
 */
function opLabelOf(rule: FilterRule, fields: FilterFieldDef[]): string {
  return opOptionsOf(rule, fields).find((o) => o.value === rule.op)?.label
    ?? OP_LABELS[rule.op]
    ?? rule.op
}

function describeRule(rule: FilterRule, fields: FilterFieldDef[]): string {
  const field = fieldOf(fields, rule.field)
  const name = field?.label ?? rule.field
  const op = opLabelOf(rule, fields)
  if (!filterOpNeedsValue(rule.op)) return `${name} ${op}`
  if (rule.op === 'between') {
    const [lo, hi] = Array.isArray(rule.value) ? rule.value : [null, null]
    return `${name} ${op} ${lo ?? '?'} ~ ${hi ?? '?'}`
  }
  return `${name} ${op} ${optionLabel(field, rule.value)}`
}

/**
 * 条件树 → 可读表达式（「(需求接收 晚于 2026-01-01 且 (状态 等于 初测完成 或 状态 等于 提请复测))」）。
 *
 * 空文本表示当前没有任何有效条件；分组用括号包裹以直观呈现优先级。
 */
export function describeFilterTree(group: FilterGroup, fields: FilterFieldDef[]): string {
  const parts: string[] = []
  for (const child of group.children) {
    if (isFilterGroup(child)) {
      const text = describeFilterTree(child, fields) // 组级「非」已在递归内施加
      if (text) parts.push(text)
      continue
    }
    const text = describeRule(child, fields)
    if (text) parts.push(child.not ? `非(${text})` : text)
  }
  if (!parts.length) return ''
  const joined = parts.join(group.logic === 'or' ? ' 或 ' : ' 且 ')
  const wrapped = parts.length > 1 ? `(${joined})` : joined
  return group.not ? `非(${wrapped})` : wrapped
}
