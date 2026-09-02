"""业务字典与漏洞状态机，语义沿用洞察2.0（logic/define.py）。"""
from enum import IntEnum

# Word (.docx) 文件的标准 MIME 类型，供上传校验与导出响应统一引用
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class VulStatus(IntEnum):
    """漏洞状态码。IntEnum 成员与其整数值相等，数据库仍存整数，历史比较不受影响。"""
    UNFIXED = 10   # 未修复
    IGNORED = 20   # 已忽略
    DEFERRED = 35  # 暂不处理
    FIXING = 50    # 修复中
    RETESTING = 55  # 复测中
    FIXED = 60     # 已修复
    # 关于 DEFERRED=35 的说明：历史遗留值，与洞察2.0保持一致。
    # 优化建议：若未来可做数据迁移，可改为 DEFERRED=30 以保持10步进。


class PlanStatus(IntEnum):
    """测试计划状态码。"""
    UNTESTED = 10      # 未测试
    TESTING = 20       # 初测中
    WAIT_RETEST = 30   # 等待复测
    RETEST_APPLY = 40  # 复测申请
    RETESTING = 50     # 复测中
    RETEST_DONE = 60   # 复测完成
    PASSED = 70        # 测试通过（测试完成且确认未发现安全漏洞，无漏洞闭环终态）


class ReportStatus(IntEnum):
    """报告状态码。与字符串字段 report.status 双向映射，保持 draft/final/completed 字符串兼容。"""
    DRAFT = 1      # 草稿
    FINAL = 2      # 已定稿
    COMPLETED = 3  # 已完成（全部关联漏洞闭环）

    # 转为数据库存储的字符串值
    def to_str(self) -> str:
        return _REPORT_STATUS_TO_STR[self]

    @classmethod
    def from_str(cls, s: str) -> "ReportStatus":
        return _REPORT_STATUS_FROM_STR.get(s, cls.DRAFT)


_REPORT_STATUS_TO_STR = {
    ReportStatus.DRAFT: "draft",
    ReportStatus.FINAL: "final",
    ReportStatus.COMPLETED: "completed",
}
_REPORT_STATUS_FROM_STR = {v: k for k, v in _REPORT_STATUS_TO_STR.items()}


VUL_TYPE = {
    10: "SQL注入漏洞",
    15: "XSS跨站漏洞",
    20: "命令执行漏洞",
    25: "代码执行漏洞",
    30: "文件包含漏洞",
    35: "任意文件操作",
    40: "权限绕过",
    45: "逻辑漏洞",
    50: "存在后门",
    55: "信息泄露",
    60: "文件上传",
    65: "弱口令",
    70: "威胁情报",
    75: "其他",
}

VUL_LEVEL = {10: "严重", 20: "高危", 30: "中危", 40: "低危", 50: "安全"}

# 报告导出文案：渗透测试报告模板使用「超危」口径，仅展示层映射，字典不变
VUL_LEVEL_EXPORT = {10: "超危", 20: "高危", 30: "中危", 40: "低危", 50: "安全"}

VUL_STATUS = {
    VulStatus.UNFIXED: "未修复",
    VulStatus.IGNORED: "已忽略",
    VulStatus.DEFERRED: "暂不处理",
    VulStatus.FIXING: "修复中",
    VulStatus.RETESTING: "复测中",
    VulStatus.FIXED: "已修复",
}

# 状态机：当前状态 -> 允许流转到的状态（仅测试人员使用的简化流程）
# 未修复 --关联生成报告(自动)--> 修复中 --发起复测(自动)--> 复测中
# 复测中 --测试人员手动--> 已修复 / 复测未通过(回修复中) / 已忽略 / 暂不处理
# 注意：UNFIXED→RETESTING 支持报告复测时跨过FIXING直接流转（修复状态的冗余兜底路径）
# FIXED→RETESTING 支持已闭环漏洞需要重新复测时直接进入复测状态
VUL_TRANSITIONS = {
    VulStatus.UNFIXED: {VulStatus.IGNORED, VulStatus.DEFERRED, VulStatus.FIXING, VulStatus.RETESTING},
    VulStatus.IGNORED: {VulStatus.UNFIXED},
    VulStatus.DEFERRED: {VulStatus.UNFIXED, VulStatus.FIXING},
    VulStatus.FIXING: {VulStatus.RETESTING},
    VulStatus.RETESTING: {VulStatus.IGNORED, VulStatus.DEFERRED, VulStatus.FIXING, VulStatus.FIXED},
    VulStatus.FIXED: {VulStatus.UNFIXED, VulStatus.RETESTING},  # 已修复可重新打开为未修复，或直接重新复测
}

# 测试计划状态机：当前状态 -> 允许流转到的状态
# 未测试 --开始初测--> 初测中 --初测完成--> 等待复测 --发起复测申请--> 复测申请
# 复测申请 --确认复测--> 复测中 --全部漏洞闭环--> 复测完成
# 等待复测/复测申请 --报告发起复测--> 复测中（报告联动）
# 复测完成 --漏洞重新打开--> 复测中
# 初测中 --确认无漏洞--> 测试通过（无漏洞闭环，无需复测）
# 测试通过 --补录/关联新漏洞--> 初测中（自动重开）
PLAN_TRANSITIONS = {
    PlanStatus.UNTESTED: {PlanStatus.TESTING, PlanStatus.PASSED},
    PlanStatus.TESTING: {PlanStatus.WAIT_RETEST, PlanStatus.PASSED},
    PlanStatus.WAIT_RETEST: {PlanStatus.RETEST_APPLY, PlanStatus.RETESTING},  # 复测申请或报告直接发起复测
    PlanStatus.RETEST_APPLY: {PlanStatus.RETESTING},
    PlanStatus.RETESTING: {PlanStatus.RETEST_DONE},
    PlanStatus.RETEST_DONE: {PlanStatus.RETESTING},  # 漏洞回退时重新打开
    PlanStatus.PASSED: {PlanStatus.TESTING},  # 无漏洞确认后补录漏洞时重新打开
}

# 进入某状态时需要打点的时间字段（漏洞状态）
STATUS_TIMESTAMP = {
    VulStatus.FIXING: "notice_time",
    VulStatus.RETESTING: "notice_time",  # 复测中也记录通知时间，方便追踪复测周期
    VulStatus.IGNORED: "fix_time",
    VulStatus.DEFERRED: "fix_time",
    VulStatus.FIXED: "fix_time",
}

# 漏洞来源（2026-08-14 重构）：仅记录单独录入漏洞时的来源；关联渗透测试工单的漏洞
# 来源恒为「渗透测试工单」（由 testing_plan_id 派生展示，不落库），不在此枚举。
VUL_SOURCE = {
    10: "工信部远程检测",
    20: "春耕行动",
    30: "集团众测",
    40: "集团ASM远程检测",
    50: "数智事业部远程检测",
}

VUL_LAYER = {10: "代码", 20: "运维"}

ASSET_SEC_LEVEL = {10: "安全一级", 20: "安全二级", 30: "安全三级", 40: "其他"}
ASSET_STATUS = {10: "线上", 20: "上线前", 30: "下线"}
URL_TAG = {10: "互联网", 20: "办公网"}

# 测试计划当前状态
TESTING_PLAN_STATUS = {
    PlanStatus.UNTESTED: "未测试",
    PlanStatus.TESTING: "初测中",
    PlanStatus.WAIT_RETEST: "等待复测",
    PlanStatus.RETEST_APPLY: "复测申请",
    PlanStatus.RETESTING: "复测中",
    PlanStatus.RETEST_DONE: "复测完成",
    PlanStatus.PASSED: "测试通过",
}

# RBAC 权限目录：按功能模块分组，label 为中文名，desc 说明其控制的菜单 / 操作。
# PERMISSIONS 为其扁平化 key 列表（权限校验与 /meta 下发保持兼容）。
PERMISSION_CATALOG = [
    {"key": "dashboard:view", "label": "安全态势", "group": "态势总览", "desc": "查看安全态势总览"},
    {"key": "asset:manage", "label": "资产管理", "group": "资产与组织", "desc": "维护资产台账与组织架构"},
    {"key": "vuln:submit", "label": "漏洞提交", "group": "漏洞管理", "desc": "提交新漏洞"},
    {"key": "vuln:audit", "label": "漏洞审核", "group": "漏洞管理", "desc": "审核漏洞状态流转"},
    {"key": "vuln:manage", "label": "漏洞管理", "group": "漏洞管理", "desc": "漏洞全量增删改查"},
    {"key": "import:manage", "label": "报告导入", "group": "报告中心", "desc": "Word 报告导入入库"},
    {"key": "report:manage", "label": "报告管理", "group": "报告中心", "desc": "报告生成、编辑与导出"},
    {"key": "special:manage", "label": "专项管理", "group": "专项工作", "desc": "渗透/漏扫工单、远程检测、春耕行动"},
    {"key": "user:manage", "label": "用户与权限", "group": "系统管理", "desc": "管理用户、角色与权限配置"},
    {"key": "system:manage", "label": "系统管理", "group": "系统管理", "desc": "审计日志与通知渠道"},
]

PERMISSIONS = [p["key"] for p in PERMISSION_CATALOG]

# 审计动作（F7 登录与操作审计）：login_ 前缀为登录事件，其余为敏感操作；
# 经 /meta 下发供审计查询页筛选下拉使用，新增动作必须在此登记
AUDIT_ACTIONS = {
    "login_success": "登录成功",
    "login_failure": "登录失败",
    "login_locked": "登录锁定",
    "password_change": "修改密码",
    "user_create": "创建用户",
    "user_update": "编辑用户",
    "user_delete": "删除用户",
    "role_update": "角色变更",
    "vuln_create": "创建漏洞",
    "vuln_delete": "删除漏洞",
    "vuln_transition": "漏洞流转",
    "plan_transition": "工单流转",
    "plan_claim": "工单认领",
    "plan_create": "创建工单",
    "plan_update": "编辑工单",
    "report_export": "导出报告",
    "report_delete": "删除报告",
    "import_confirm": "导入入库",
    "knowledge_delete": "删除知识库条目",
    "pat_create": "创建访问令牌",
    "pat_revoke": "吊销访问令牌",
    "notify_update": "通知渠道变更",
}

# 通知渠道类型（F3）：webhook 走 httpx 出站 POST，邮件复用 SMTP 任务
NOTIFY_CHANNEL_TYPES = {
    "wecom": "企业微信",
    "dingtalk": "钉钉",
    "email": "邮件",
}

# 可订阅的通知事件：触发点见各路由成功响应后的 notify_service.emit 调用
NOTIFY_EVENTS = {
    "vuln_created": "漏洞创建",
    "plan_claimed": "工单认领",
    "vuln_transition": "漏洞状态流转",
    "retest_completed": "复测完成",
}

# Word 导入模板中「漏洞信息表格」的行标签 -> 字段映射
# 标签命名与报告模板「风险问题详情」章节保持一致（漏洞链接/漏洞证明），
# 同时保留旧模板标签（影响URL/复现步骤）作为兼容别名
IMPORT_LABEL_MAP = {
    "漏洞名称": "title",
    "漏洞等级": "level",
    "漏洞类型": "vul_type",
    "漏洞链接": "affected_url",
    "影响URL": "affected_url",
    "影响url": "affected_url",
    "漏洞描述": "description_html",
    "漏洞证明": "reproduce_html",
    "复现步骤": "reproduce_html",
    "修复建议": "solution_html",
}

VUL_LEVEL_REVERSE = {v: k for k, v in VUL_LEVEL.items()}
VUL_TYPE_REVERSE = {v: k for k, v in VUL_TYPE.items()}


# ---------- 界面展示色值与展示名（/meta 下发，前端唯一色源，改此处即全端生效） ----------
# 屏幕展示口径；Word/PDF 导出的打印色板在 services/report_builder.py 独立维护（打印色与屏幕色语义不同）
VUL_LEVEL_COLOR = {
    10: "#DC2626",  # 严重 红
    20: "#EA580C",  # 高危 橙
    30: "#D97706",  # 中危 琥珀
    40: "#0284C7",  # 低危 蓝
    50: "#059669",  # 安全 薄荷绿
}

VUL_STATUS_COLOR = {
    VulStatus.UNFIXED: "#DC2626",    # 未修复 红
    VulStatus.FIXING: "#D97706",     # 修复中 琥珀
    VulStatus.RETESTING: "#0284C7",  # 复测中 蓝
    VulStatus.FIXED: "#059669",      # 已修复 薄荷绿
    VulStatus.IGNORED: "#8A968F",    # 已忽略 灰
    VulStatus.DEFERRED: "#8A968F",   # 暂不处理 灰
}

VUL_TYPE_COLOR = {  # 色相分散便于区分；灰色固定留给「其他」，动态新增类型（code≥1000）由前端兜底灰色
    10: "#E0442F",   # SQL注入 朱红
    15: "#D97706",   # XSS跨站 琥珀
    20: "#8C1D18",   # 命令执行 暗红
    25: "#9333EA",   # 代码执行 紫
    30: "#DB2777",   # 文件包含 品红
    35: "#2D7DD2",   # 任意文件操作 蓝
    40: "#F59E0B",   # 权限绕过 琥珀
    45: "#0EA5E9",   # 逻辑漏洞 天蓝
    50: "#DC2626",   # 存在后门 鲜红
    55: "#059669",   # 信息泄露 翠绿
    60: "#D97706",   # 文件上传 深橙
    65: "#7C3AED",   # 弱口令 深紫
    70: "#0D9488",   # 威胁情报 青
    75: "#8A968F",   # 其他 灰
}

TESTING_PLAN_STATUS_COLOR = {
    PlanStatus.UNTESTED: "#8A968F",
    PlanStatus.TESTING: "#D97706",
    PlanStatus.WAIT_RETEST: "#0284C7",
    PlanStatus.RETEST_APPLY: "#DC2626",
    PlanStatus.RETESTING: "#D97706",
    PlanStatus.RETEST_DONE: "#059669",
    PlanStatus.PASSED: "#059669",
}

ASSET_STATUS_COLOR = {
    10: "#059669",  # 线上 薄荷绿
    20: "#D97706",  # 上线前 琥珀
    30: "#8A968F",  # 下线 灰
}

URL_TAG_COLOR = {
    10: "#0284C7",  # 互联网 蓝
    20: "#8A968F",  # 办公网 灰
}

# 报告状态展示（status 字符串 draft/final/completed）
REPORT_STATUS_NAME = {"draft": "草稿", "final": "已定稿", "completed": "已完成"}
REPORT_STATUS_COLOR = {"draft": "#8A968F", "final": "#0284C7", "completed": "#059669"}

# Word 导入批次 / 记录状态展示（imports 与 workers 的状态字符串）
IMPORT_BATCH_STATUS_NAME = {
    "pending": "排队中", "parsing": "解析中", "parsed": "待确认",
    "confirmed": "已入库", "failed": "解析失败",
}
IMPORT_BATCH_STATUS_COLOR = {
    "pending": "#8A968F", "parsing": "#D97706", "parsed": "#0284C7",
    "confirmed": "#059669", "failed": "#DC2626",
}
IMPORT_RECORD_STATUS_NAME = {
    "parsed": "待确认", "error": "解析异常", "confirmed": "已入库", "discarded": "已丢弃",
}
IMPORT_RECORD_STATUS_COLOR = {
    "parsed": "#0284C7", "error": "#D97706", "confirmed": "#059669", "discarded": "#8A968F",
}

# 导出任务状态展示（workers/export_report_task 的状态字符串）
EXPORT_JOB_STATUS_NAME = {
    "pending": "生成中", "running": "生成中", "done": "已完成", "failed": "失败",
}
EXPORT_JOB_STATUS_COLOR = {
    "pending": "#D97706", "running": "#D97706", "done": "#059669", "failed": "#DC2626",
}


# 非渗透测试项（key -> (名称, 说明)）：与测试计划平级的扫描类测试
NONPEN_ITEMS = {
    "baseline": ("基线扫描", "配置基线 / 安全基线核查"),
    "host": ("主机漏洞扫描", "服务 / 端口 / 补丁漏洞"),
    "web": ("Web漏洞扫描", "Web 应用 / 接口漏洞"),
}

# 非渗透测试项独立流转状态：未开始→初测中→等待复测→复测中→复测完成，任意阶段可忽略
NONPEN_ITEM_STATUS = {
    "not_started": "未开始",
    "testing": "初测中",
    "wait_retest": "等待复测",
    "retesting": "复测中",
    "retest_done": "复测完成",
    "ignored": "忽略",
}

# 测试项状态 → 允许的操作（后端流转校验 + 前端按钮渲染共用；元组有序，即前端按钮渲染顺序）
NONPEN_ITEM_ACTIONS = {
    "not_started": ("start", "ignore"),                    # 开始初测 / 忽略
    "testing": ("done", "direct_done", "ignore"),          # 初测完成(→等待复测) / 直接完成(→复测完成) / 忽略
    "wait_retest": ("start_retest", "ignore"),             # 发起复测 / 忽略
    "retesting": ("pass", "fail", "ignore"),               # 复测通过 / 复测未通过(退回等待复测) / 忽略
    "retest_done": ("reset",),                             # 置回未开始
    "ignored": ("unignore",),                              # 取消忽略（次数清零，回未开始）
}

# 操作名 -> 中文展示（前端按钮文案与后端错误提示共用）
NONPEN_ITEM_ACTION_NAMES = {
    "start": "开始初测",
    "done": "初测完成",
    "direct_done": "直接完成",
    "start_retest": "发起复测",
    "pass": "复测通过",
    "fail": "复测未通过",
    "reset": "置回未开始",
    "ignore": "忽略",
    "unignore": "取消忽略",
}

# 状态 -> 展示色值（明/暗双主题通用；「未开始」正常灰需关注，「忽略」更浅灰弱化）
NONPEN_ITEM_COLORS = {
    "not_started": "#8A968F",
    "testing": "#0284C7",
    "wait_retest": "#D97706",
    "retesting": "#D97706",
    "retest_done": "#059669",
    "ignored": "#A6B1AB",
}
