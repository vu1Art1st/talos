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

# RBAC 权限点
PERMISSIONS = [
    "dashboard:view",
    "asset:manage",
    "vuln:submit",
    "vuln:audit",
    "vuln:manage",
    "import:manage",
    "report:manage",
    "special:manage",
    "user:manage",
    "system:manage",
]

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

# 测试项状态 → 允许的操作（后端流转校验 + 前端按钮渲染共用）
NONPEN_ITEM_ACTIONS = {
    "not_started": {"start", "ignore"},                    # 开始初测 / 忽略
    "testing": {"done", "direct_done", "ignore"},          # 初测完成(→等待复测) / 直接完成(→复测完成) / 忽略
    "wait_retest": {"start_retest", "ignore"},             # 发起复测 / 忽略
    "retesting": {"pass", "fail", "ignore"},               # 复测通过 / 复测未通过(退回等待复测) / 忽略
    "retest_done": {"reset"},                              # 置回未开始
    "ignored": {"unignore"},                               # 取消忽略（次数清零，回未开始）
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
    "not_started": "#909399",
    "testing": "#409EFF",
    "wait_retest": "#E6A23C",
    "retesting": "#E6A23C",
    "retest_done": "#67C23A",
    "ignored": "#c0c4cc",
}
