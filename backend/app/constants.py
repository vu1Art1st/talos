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

VUL_STATUS = {
    10: "待审核",
    20: "已忽略",
    30: "已驳回",
    35: "暂不处理",
    40: "已确认",
    50: "修复中",
    55: "复测中",
    60: "已完成",
}

# 状态机：当前状态 -> 允许流转到的状态
VUL_TRANSITIONS = {
    10: {20, 30, 35, 40},
    20: {10},
    30: {10},
    35: {20, 30, 40},
    40: {20, 35, 50},
    50: {55},
    55: {50, 60},
    60: set(),
}

# 进入某状态时需要打点的时间字段
STATUS_TIMESTAMP = {
    40: "audit_time",
    50: "notice_time",
    20: "fix_time",
    30: "fix_time",
    35: "fix_time",
    60: "fix_time",
}

VUL_SOURCE = {10: "安全部", 20: "SRC", 30: "众测", 40: "公众平台", 50: "合作伙伴", 60: "Word导入"}

VUL_LAYER = {10: "代码", 20: "运维"}

ASSET_LEVEL = {10: "一级", 20: "二级", 30: "三级", 40: "其他"}
ASSET_TYPE = {10: "域名", 20: "IP"}

APP_TYPE = {10: "APP", 20: "WEB应用", 30: "APP和WEB应用"}
APP_SEC_LEVEL = {10: "安全一级", 20: "安全二级", 30: "安全三级", 40: "其他"}
APP_STATUS = {10: "线上", 20: "上线前", 30: "下线"}

# RBAC 权限点
PERMISSIONS = [
    "dashboard:view",
    "app:manage",
    "asset:manage",
    "vuln:submit",
    "vuln:audit",
    "vuln:manage",
    "import:manage",
    "report:manage",
    "user:manage",
    "system:manage",
]

# Word 导入模板中「漏洞信息表格」的行标签 -> 字段映射
IMPORT_LABEL_MAP = {
    "漏洞名称": "title",
    "漏洞等级": "level",
    "漏洞类型": "vul_type",
    "影响URL": "affected_url",
    "影响url": "affected_url",
    "漏洞描述": "description_html",
    "复现步骤": "reproduce_html",
    "修复建议": "solution_html",
}

VUL_LEVEL_REVERSE = {v: k for k, v in VUL_LEVEL.items()}
VUL_TYPE_REVERSE = {v: k for k, v in VUL_TYPE.items()}
