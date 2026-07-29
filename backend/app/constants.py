"""业务字典与漏洞状态机，语义沿用洞察2.0（logic/define.py）。"""

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
    10: "未修复",
    20: "已忽略",
    35: "暂不处理",
    50: "修复中",
    55: "复测中",
    60: "已修复",
}

# 状态机：当前状态 -> 允许流转到的状态（仅测试人员使用的简化流程）
# 未修复 --关联生成报告(自动)--> 修复中 --点击复测(自动)--> 复测中
# 复测中 --测试人员手动--> 已修复 / 复测未通过(回修复中) / 已忽略 / 暂不处理
VUL_TRANSITIONS = {
    10: {20, 35, 50},
    20: {10},
    35: {10, 50},
    50: {55},
    55: {20, 35, 50, 60},
    60: set(),
}

# 进入某状态时需要打点的时间字段
STATUS_TIMESTAMP = {
    50: "notice_time",
    20: "fix_time",
    35: "fix_time",
    60: "fix_time",
}

VUL_SOURCE = {10: "安全部", 20: "SRC", 30: "众测", 40: "公众平台", 50: "合作伙伴", 60: "Word导入"}

VUL_LAYER = {10: "代码", 20: "运维"}

ASSET_SEC_LEVEL = {10: "安全一级", 20: "安全二级", 30: "安全三级", 40: "其他"}
ASSET_STATUS = {10: "线上", 20: "上线前", 30: "下线"}
URL_TAG = {10: "互联网", 20: "办公网"}

# 测试计划当前状态
TESTING_PLAN_STATUS = {
    10: "未测试",
    20: "初测中",
    30: "等待复测",
    40: "复测申请",
    50: "复测中",
    60: "复测完成",
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
