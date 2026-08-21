"""dev.db 高质量种子数据：清空全部业务数据后重建（基础账号 + 全域关联数据）。

生成口径：
- 时间线覆盖近 12 个月（支撑 Dashboard 趋势图 / 部门透视）；
- 渗透工单覆盖全部 7 种状态（含多轮复测、无漏洞闭环）；漏洞覆盖全部 6 种状态、
  5 类独立来源，等级/类型分布有区分度（支撑等级分布、类型 Top10）；
- 资产-漏洞-工单-报告关联完整，已修复漏洞带复测记录与操作日志；
- 知识库直接复用 scripts.seed_knowledge.SEED_DATA（50 条标准模板）。

用法（backend 目录下）：
    python -m scripts.seed_dev_data --reset          # 清空并重建（需显式 --reset）

账号：admin / admin123（管理员）；测试账号密码统一 Talos@2026
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 必须在导入 app 之前设置（settings 为模块级单例）
os.environ.setdefault("VP_DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
os.environ.setdefault("VP_DISABLE_QUEUE", "1")
os.environ.setdefault("VP_SECRET_KEY", "dev-secret-key-0123456789abcdef-0123456789")

from sqlalchemy import text  # noqa: E402

from app.constants import (  # noqa: E402
    NONPEN_ITEMS, PlanStatus, VulStatus,
)
from app.core.security import hash_password  # noqa: E402
from app.core.timeutil import now as tznow  # noqa: E402
from app.db import Base, async_session_maker, engine  # noqa: E402
from app.models import (  # noqa: E402
    Asset, DictOption, ExportJob, Group, GroupMember, GroupUser, KnowledgeEntry,
    Message, NonpenPlan, RemoteTesting, Report, ReportSection, Role, SpringAction,
    TestingPlan, TestingPlanRetestRound, User, Vul, VulLog, VulRetestRecord,
)
from app.models.business import vuln_assets  # noqa: E402
from app.models.special import spring_action_vulns, testing_plan_testers  # noqa: E402
from scripts.seed_knowledge import SEED_DATA  # noqa: E402

# 全部业务表（按外键依赖排序，先子后父）
ALL_TABLES = [
    "vul_logs", "vul_retest_records", "vuln_assets", "spring_action_vulns",
    "testing_plan_testers", "testing_plan_retest_rounds", "report_sections",
    "export_jobs", "messages", "group_users", "group_members",
    "import_records", "import_batches",
    "vulns", "reports", "testing_plans", "nonpen_plans", "spring_actions",
    "remote_testings", "assets", "knowledge_entries",
    "users", "roles", "groups", "dict_options", "vuln_types",
]

DEPARTMENTS = ["数智化部", "集成服务部", "公安业务部", "AI业务部", "人力资源部", "市场运营部", "财务管理部", "运维保障部"]

# (username, realname, email, 角色key)
USERS = [
    ("zhangwei", "张伟", "zhangwei@example.com", "tester"),
    ("lina", "李娜", "lina@example.com", "tester"),
    ("wangqiang", "王强", "wangqiang@example.com", "tester"),
    ("zhaomin", "赵敏", "zhaomin@example.com", "tester"),
    ("chenlei", "陈磊", "chenlei@example.com", "tester"),
    ("liuyang", "刘洋", "liuyang@example.com", "viewer"),
]

TEST_TYPES = ["渗透测试", "基线核查", "红蓝对抗", "代码审计", "App安全测试", "应急演练"]

# (名称, 子系统, 部门idx, 系统类型, 公网?, 中间件, 数据库, sec_level, status)
ASSETS = [
    ("综合办公系统", "公文管理", 0, "自有系统（正式）", True, "Nginx/1.24;Tomcat/9.0", "MySQL/8.0", 20, 10),
    ("综合办公系统", "会议管理", 0, "自有系统（正式）", False, "Nginx/1.24", "MySQL/8.0", 40, 10),
    ("人力资源管理系统", "薪酬模块", 4, "自有系统（正式）", False, "Nginx/1.22;Redis/7.0", "Oracle/19c", 20, 10),
    ("财务共享平台", "报销中心", 6, "自有系统（正式）", True, "Nginx;WebLogic/14", "Oracle/19c", 10, 10),
    ("统一身份认证平台", "", 7, "自有系统（正式）", True, "Nginx;OpenResty/1.21", "MySQL/8.0", 10, 10),
    ("营销活动平台", "优惠券中心", 5, "自有系统（正式）", True, "Nginx;SpringCloud Gateway", "MySQL/8.0;Redis", 30, 10),
    ("智能客服系统", "在线坐席", 5, "自有系统（正式）", True, "Nginx;Node.js/18", "MongoDB/6.0", 30, 10),
    ("数据中台", "数据服务网关", 0, "DCIT系统", False, "Nginx;Flink/1.17", "ClickHouse/23", 20, 10),
    ("合同管理系统", "电子签章", 1, "自有系统（正式）", False, "Nginx;Tomcat/9.0", "MySQL/8.0", 30, 10),
    ("移动办公App", "消息推送", 0, "自有系统（正式）", True, "SpringBoot/3.1", "MySQL/8.0;Redis", 30, 20),
    ("采购管理平台", "供应商门户", 1, "自有系统（正式）", True, "Nginx;Tomcat/8.5", "MySQL/5.7", 30, 10),
    ("项目管理平台", "", 1, "自有系统（测试）", False, "Nginx", "PostgreSQL/15", 40, 20),
    ("知识库系统", "文档检索", 0, "自有系统（正式）", False, "Nginx;ElasticSearch/8", "MySQL/8.0", 40, 10),
    ("运维监控平台", "告警中心", 7, "自有系统（正式）", False, "Nginx;Grafana/10", "Prometheus", 30, 10),
    ("日志审计系统", "", 7, "DCIT系统", False, "Nginx", "ClickHouse/23", 20, 10),
    ("短信网关", "", 7, "自有系统（正式）", True, "Nginx;Tomcat/8.5", "MySQL/5.7", 30, 30),
    ("API开放平台", "", 0, "DCIT系统", True, "Nginx;Kong/3.4", "PostgreSQL/15", 20, 10),
]

# 渗透工单：(计划名, 系统idx, 测试类型idx, 部门idx, 接收日期, 状态, 认领者idx列表, 预估人天, 实际人天, brief)
PLANS = [
    ("综合办公系统渗透测试", 0, 0, 0, "2025-10-13", PlanStatus.RETEST_DONE, [0, 1], 5, 6,
     "对综合办公系统公文管理子系统开展全量渗透测试，覆盖身份认证、流程审批与文件导出链路"),
    ("人力资源管理系统渗透测试", 2, 0, 4, "2025-11-10", PlanStatus.RETEST_DONE, [1], 4, 4,
     "薪酬模块上线前安全测试，重点核查越权与敏感数据展示"),
    ("财务共享平台渗透测试", 3, 0, 6, "2025-12-08", PlanStatus.RETEST_DONE, [2, 3], 6, 7.5,
     "报销中心年度例行渗透，覆盖支付接口与电子影像件存储"),
    ("统一身份认证平台渗透测试", 4, 0, 7, "2026-01-12", PlanStatus.RETESTING, [0], 5, 3,
     "SSO 升级改造后的专项渗透，聚焦会话管理与 OAuth 授权链路"),
    ("营销活动平台渗透测试", 5, 0, 5, "2026-02-09", PlanStatus.WAIT_RETEST, [3], 4, 4,
     "优惠券中心大促前安全测试，覆盖活动规则与积分兑换接口"),
    ("智能客服系统渗透测试", 6, 0, 5, "2026-03-09", PlanStatus.WAIT_RETEST, [1, 4], 3, 3,
     "在线坐席 Web 端渗透，含文件上传与知识库检索注入面"),
    ("数据中台安全测试", 7, 2, 0, "2026-04-13", PlanStatus.RETEST_APPLY, [2], 8, 5,
     "数据服务网关红蓝对抗，验证接口鉴权与数据脱敏有效性"),
    ("合同管理系统渗透测试", 8, 0, 1, "2026-05-11", PlanStatus.TESTING, [4], 4, 1,
     "电子签章模块上线前测试，重点验证签章文件校验逻辑"),
    ("移动办公App安全测试", 9, 4, 0, "2026-06-08", PlanStatus.TESTING, [0, 3], 5, 2,
     "App 客户端与服务端联动安全测试"),
    ("采购管理平台渗透测试", 10, 0, 1, "2026-07-13", PlanStatus.UNTESTED, [], 4, 0,
     "供应商门户年度例行渗透，待认领排期"),
    ("项目管理平台安全核查", 11, 1, 1, "2026-07-20", PlanStatus.PASSED, [4], 2, 2,
     "测试环境基线核查加轻度渗透，未发现安全漏洞"),
    ("知识库系统安全核查", 12, 1, 0, "2026-08-03", PlanStatus.PASSED, [1], 2, 1.5,
     "文档检索模块安全核查，未发现安全漏洞"),
]

# 漏洞模板：(标题, 工单idx|None, 来源code|None, 等级, 类型, 状态, 资产idx列表, 提交者idx, 月偏移(0=当月), is_retest, 天数后修复)
# 月偏移：相对 2026-08 的回溯月数；同一工单内漏洞按提交时间递增
VULNS = [
    # 工单0 综合办公系统（2025-10，复测完成：3已修复 1复测闭环中转已修复 1修复中 1忽略）
    ("公文导出接口未授权访问", 0, None, 10, 40, VulStatus.FIXED, [0], 0, 10, True, 18),
    ("流程审批SQL注入漏洞", 0, None, 20, 10, VulStatus.FIXED, [0], 0, 10, True, 25),
    ("会议材料任意文件下载", 0, None, 30, 35, VulStatus.FIXED, [1], 1, 10, True, 20),
    ("公文检索存储型XSS", 0, None, 30, 15, VulStatus.FIXED, [0], 1, 10, True, 22),
    ("会话注销后Token仍有效", 0, None, 40, 45, VulStatus.FIXING, [0], 0, 10, False, 0),
    ("历史版本比对页面信息泄露", 0, None, 40, 55, VulStatus.IGNORED, [1], 1, 10, False, 0),
    # 工单1 人力资源管理系统（2025-11，复测完成）
    ("薪酬查询水平越权", 1, None, 10, 40, VulStatus.FIXED, [2], 1, 9, True, 15),
    ("简历附件上传绕过", 1, None, 20, 60, VulStatus.FIXED, [2], 1, 9, True, 20),
    ("员工花名册接口未鉴权", 1, None, 20, 55, VulStatus.FIXED, [2], 2, 9, True, 16),
    ("考勤导出目录遍历", 1, None, 30, 35, VulStatus.FIXED, [2], 2, 9, True, 12),
    # 工单2 财务共享平台（2025-12，复测完成）
    ("支付回调金额篡改", 2, None, 10, 45, VulStatus.FIXED, [3], 2, 8, True, 21),
    ("报销影像件未授权访问", 2, None, 20, 55, VulStatus.FIXED, [3], 3, 8, True, 14),
    ("WebLogic控制台弱口令", 2, None, 20, 65, VulStatus.FIXED, [3], 2, 8, True, 5),
    ("电子发票重复报销逻辑缺陷", 2, None, 30, 45, VulStatus.FIXED, [3], 3, 8, True, 18),
    ("审批意见存储型XSS", 2, None, 30, 15, VulStatus.DEFERRED, [3], 3, 8, False, 0),
    # 工单3 统一身份认证平台（2026-01，复测中）
    ("OAuth授权码重放利用", 3, None, 10, 45, VulStatus.RETESTING, [4], 0, 7, False, 0),
    ("JWT算法降级绕过签名校验", 3, None, 20, 40, VulStatus.RETESTING, [4], 0, 7, False, 0),
    ("短信验证码暴力破解", 3, None, 20, 45, VulStatus.FIXING, [4], 0, 7, False, 0),
    ("登录错误信息账号枚举", 3, None, 40, 55, VulStatus.FIXING, [4], 0, 7, False, 0),
    # 工单4 营销活动平台（2026-02，等待复测）
    ("优惠券领取接口重放", 4, None, 20, 45, VulStatus.FIXING, [5], 3, 6, False, 0),
    ("活动规则前端校验绕过", 4, None, 30, 45, VulStatus.FIXING, [5], 3, 6, False, 0),
    ("积分商城订单金额篡改", 4, None, 20, 45, VulStatus.UNFIXED, [5], 3, 6, False, 0),
    ("海报图片上传SVG注入", 4, None, 40, 15, VulStatus.FIXING, [5], 3, 6, False, 0),
    # 工单5 智能客服系统（2026-03，等待复测）
    ("坐席附件上传WebShell", 5, None, 10, 60, VulStatus.FIXING, [6], 4, 5, False, 0),
    ("知识库检索EL表达式注入", 5, None, 20, 25, VulStatus.UNFIXED, [6], 1, 5, False, 0),
    ("访客会话固定攻击", 5, None, 30, 45, VulStatus.FIXING, [6], 4, 5, False, 0),
    # 工单6 数据中台（2026-04，复测申请）
    ("数据服务网关API未鉴权", 6, None, 10, 40, VulStatus.FIXING, [7], 2, 4, False, 0),
    ("ClickHouse接口SQL注入", 6, None, 20, 10, VulStatus.FIXING, [7], 2, 4, False, 0),
    ("元数据接口敏感信息泄露", 6, None, 30, 55, VulStatus.UNFIXED, [7], 2, 4, False, 0),
    # 工单7 合同管理系统（2026-05，初测中）
    ("签章文件校验绕过", 7, None, 20, 40, VulStatus.UNFIXED, [8], 4, 3, False, 0),
    ("合同模板路径穿越", 7, None, 30, 35, VulStatus.UNFIXED, [8], 4, 3, False, 0),
    ("合同编号可预测遍历", 7, None, 40, 45, VulStatus.UNFIXED, [8], 4, 3, False, 0),
    # 工单8 移动办公App（2026-06，初测中）
    ("消息推送接口越权订阅", 8, None, 20, 40, VulStatus.UNFIXED, [9], 0, 2, False, 0),
    ("App本地存储明文口令", 8, None, 30, 55, VulStatus.UNFIXED, [9], 3, 2, False, 0),
    # 独立来源漏洞（无工单，source 生效）
    ("门户首页反射型XSS", None, 10, 30, 15, VulStatus.FIXED, [4], 1, 11, True, 30),
    ("老旧Tomcat示例目录暴露", None, 10, 20, 55, VulStatus.IGNORED, [10], 0, 9, False, 0),
    ("通报CNVD命令执行漏洞", None, 10, 10, 20, VulStatus.FIXED, [3], 2, 6, True, 25),
    ("集团众测发现弱口令", None, 30, 20, 65, VulStatus.FIXED, [15], 3, 4, True, 10),
    ("众测越权修改他人资料", None, 30, 40, 40, VulStatus.RETESTING, [16], 3, 1, False, 0),
    ("ASM远程检测Fastjson反序列化", None, 40, 10, 25, VulStatus.FIXED, [6], 4, 5, True, 20),
    ("春耕通报短信网关劫持", None, 20, 20, 45, VulStatus.FIXING, [15], 4, 3, False, 0),
    ("春耕通报默认数据库口令", None, 20, 20, 65, VulStatus.FIXED, [7], 2, 7, True, 15),
    # 独立-历史遗留（更早，支撑趋势曲线）
    ("堡垒机历史低危配置项", None, 50, 40, 55, VulStatus.FIXED, [13], 2, 12, True, 40),
    ("老OA文件包含漏洞(已下线整改)", None, 50, 30, 30, VulStatus.FIXED, [1], 1, 12, True, 35),
]

REPORT_TMPL = [
    # (工单idx, 标题后缀, 状态, test_start, test_end)
    (0, "初测报告", "completed", "2025-10-13", "2025-10-17"),
    (0, "复测报告（第一轮）", "completed", "2025-11-03", "2025-11-05"),
    (1, "初测报告", "completed", "2025-11-10", "2025-11-13"),
    (3, "初测报告", "final", "2026-01-12", "2026-01-16"),
    (4, "初测报告", "final", "2026-02-09", "2026-02-12"),
    (7, "初测报告", "draft", "2026-05-11", "2026-05-14"),
]

# 漏扫基线工单：(计划名, 系统idx, 测试类型idx, 接收日期, items状态映射 key->(status, first, retest), 联动工单idx|None)
NONPEN = [
    ("综合办公系统基线核查", 0, 1, "2025-10-13",
     {"baseline": ("retest_done", 1, 1), "host": ("retest_done", 1, 1), "web": ("ignored", 0, 0)}, 0),
    ("运维监控平台主机漏扫", 13, 1, "2025-12-15",
     {"host": ("retest_done", 1, 2), "web": ("not_started", 0, 0)}, None),
    ("日志审计系统基线核查", 14, 1, "2026-02-24",
     {"baseline": ("retest_done", 1, 1), "web": ("retest_done", 1, 0)}, None),
    ("短信网关Web漏扫", 15, 1, "2026-04-20",
     {"web": ("retesting", 1, 1), "baseline": ("ignored", 0, 0)}, None),
    ("API开放平台漏扫", 16, 1, "2026-06-16",
     {"web": ("testing", 0, 0), "host": ("not_started", 0, 0)}, None),
    ("数据中台基线核查", 7, 1, "2026-04-13",
     {"baseline": ("wait_retest", 1, 0), "host": ("not_started", 0, 0)}, 6),
]

# 远程检测：(通报月份, 系统idx, 部门idx, 被通报单位, 外部?, 漏洞名, 漏洞类型, 申诉状态, 申诉方式)
REMOTE = [
    ("2025-11", 3, 6, "省通信管理局", True, "支付接口越权漏洞", "权限绕过", "success", "提交整改证明材料"),
    ("2025-12", 15, 7, "工信部网络安全威胁中心", False, "短信网关API未授权", "未授权访问", "fail", "提交申诉说明函"),
    ("2026-01", 5, 5, "集团信息安全部", False, "活动平台优惠券超发", "逻辑漏洞", "success", "提供复测报告"),
    ("2026-02", 6, 5, "省通信管理局", True, "客服系统文件上传漏洞", "文件上传", "", ""),
    ("2026-03", 7, 0, "集团信息安全部", False, "数据接口敏感信息泄露", "信息泄露", "success", "提交脱敏整改说明"),
    ("2026-05", 16, 0, "工信部网络安全威胁中心", True, "API网关Token泄露", "信息泄露", "fail", "提交申诉说明函"),
    ("2026-07", 9, 0, "省通信管理局", False, "移动App通信明文传输", "传输安全", "", ""),
    ("2026-08", 4, 7, "集团众测平台", True, "认证平台JWT密钥弱", "弱口令", "", ""),
]

# 春耕行动：(报告编号, 系统idx, 年度, 阶段, 申诉成功?, 扣分, 公文文号, 关联漏洞idx列表)
SPRING = [
    ("CG-2025-QT-012", 3, "2025", "第一阶段", True, 1.0, "移动通〔2025〕148号", [12]),
    ("CG-2025-QT-035", 15, "2025", "第二阶段", False, 3.0, "移动通〔2025〕236号", [40]),
    ("CG-2026-QT-008", 6, "2026", "第一阶段", True, 0.5, "移动通〔2026〕52号", [26]),
    ("CG-2026-QT-021", 7, "2026", "第二阶段", False, 2.0, "移动通〔2026〕97号", [41]),
]


def dt(months_ago: int, day: int, hour: int = 10) -> datetime:
    """以 2026-08-22 为基准回溯 N 个月构造时间。"""
    base = datetime(2026, 8, 22)
    month = base.month - months_ago
    year = base.year
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, min(day, 28), hour, 0, 0)


def para(*lines: str) -> str:
    return "".join(f"<p>{l}</p>" for l in lines)


async def reset_and_seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 清空全部业务表（子表优先）；自增计数随普通 INTEGER PRIMARY KEY 自动重置
        for t in ALL_TABLES:
            await conn.execute(text(f"DELETE FROM {t}"))

    async with async_session_maker() as session:
        # ---------- 角色 / 用户 ----------
        role_admin = Role(name="管理员", permissions=["*"], remark="全部权限")
        role_tester = Role(name="测试工程师", permissions=[
            "dashboard:view", "asset:manage", "vuln:submit", "vuln:audit",
            "vuln:manage", "import:manage", "report:manage", "special:manage",
        ], remark="安全测试团队")
        role_viewer = Role(name="观察员", permissions=["dashboard:view"], remark="只读看板")
        session.add_all([role_admin, role_tester, role_viewer])
        await session.flush()

        admin = User(
            username="admin", password_hash=hash_password("admin123"), realname="系统管理员",
            email="admin@example.com", role_id=role_admin.id, remark="内置管理员",
        )
        session.add(admin)
        testers: list[User] = []
        for username, realname, email, role_key in USERS:
            u = User(
                username=username, password_hash=hash_password("Talos@2026"), realname=realname,
                email=email, role_id=(role_tester if role_key == "tester" else role_viewer).id,
                last_login=dt(0, 20),
            )
            testers.append(u)
            session.add(u)
        await session.flush()

        # ---------- 组织与成员 ----------
        groups: list[Group] = []
        for i, name in enumerate(DEPARTMENTS):
            g = Group(name=name, remark=f"{name}安全接口部门")
            groups.append(g)
            session.add(g)
        await session.flush()
        member_names = {
            0: ("孙晓东", "周琳"), 1: ("吴建国", "郑洁"), 2: ("冯军", "蒋敏"),
            3: ("韩雪", "杨帆"), 4: ("朱丽华", "秦浩"), 5: ("许文强", "何佳"),
            6: ("吕明", "施婷"), 7: ("孔维", "曹阳"),
        }
        for gi, (leader, deputy) in member_names.items():
            session.add_all([
                GroupMember(group_id=groups[gi].id, name=leader, phone="13800000001",
                            email=f"{leader}@example.com"),
                GroupMember(group_id=groups[gi].id, name=deputy, phone="13800000002",
                            email=f"{deputy}@example.com"),
            ])

        # ---------- 字典 ----------
        for i, name in enumerate(TEST_TYPES):
            session.add(DictOption(category="test_type", name=name, sort=i))

        # ---------- 资产 ----------
        assets: list[Asset] = []
        slug = ["zhbg", "zhbg-meet", "hr", "fin", "sso", "mkt", "cs", "datamid",
                "contract", "app", "purchase", "pm", "kb", "ops", "audit", "sms", "api"]
        for idx, (name, sub, dept_i, stype, has_pub, mw, db, sec, status) in enumerate(ASSETS):
            a = Asset(
                name=name, sub_system=sub, department=DEPARTMENTS[dept_i], system_type=stype,
                public_urls=[{"url": f"https://{slug[idx]}.example.com", "tag": 10}] if has_pub else [],
                internal_urls=[f"http://10.20.{idx + 1}.10:8080"],
                port_services=[{"port": "443", "service": "HTTPS"}, {"port": "8080", "service": "Web服务"}],
                middlewares=[{"name": m.split("/")[0], "version": m.split("/")[-1]} for m in mw.split(";")],
                databases=[{"name": d.split("/")[0], "version": d.split("/")[-1]} for d in db.split(";")],
                owners=[{"name": member_names[dept_i][0], "phone": "13800000001",
                         "email": f"{member_names[dept_i][0]}@example.com"}],
                sec_level=sec, status=status, group_id=groups[dept_i].id,
                create_time=dt(12 - idx % 8, 15), update_time=dt(0, 15),
            )
            assets.append(a)
            session.add(a)
        await session.flush()

        # ---------- 渗透测试工单 ----------
        plans: list[TestingPlan] = []
        seq_counter: dict[str, int] = {}
        for pi, (pname, sys_i, tt_i, dept_i, recv, status, tester_idx, est, actual, brief) in enumerate(PLANS):
            seq = seq_counter.get(recv, 0) + 1
            seq_counter[recv] = seq
            plan = TestingPlan(
                plan_name=pname, system_name=assets[sys_i].name, test_type=TEST_TYPES[tt_i],
                department=DEPARTMENTS[dept_i], receive_time=recv, ticket_time=recv,
                ticket_seq=seq, asset_ids=[assets[sys_i].id, assets[sys_i + 1].id] if sys_i == 0 else [assets[sys_i].id],
                status=status, est_mandays=est, actual_mandays=actual if actual else 0,
                brief=brief, detail=f"测试人员：{'、'.join(testers[i].realname for i in tester_idx) or '待认领'}；数据来源：安全测试需求单",
                no_vul_conclusion="经核查未发现安全漏洞，测试通过。" if status == PlanStatus.PASSED else "",
                creator_id=admin.id, create_time=dt(12 - pi, 9),
            )
            if status in (PlanStatus.RETEST_DONE,):
                plan.first_test_done_time = recv
                plan.retest_notice_time = recv
                plan.retest_done_time = recv
            elif status in (PlanStatus.RETESTING, PlanStatus.RETEST_APPLY):
                plan.first_test_done_time = recv
                plan.retest_notice_time = recv
            elif status == PlanStatus.WAIT_RETEST:
                plan.first_test_done_time = recv
            plans.append(plan)
            session.add(plan)
        await session.flush()
        for pi, (_, _, _, _, _, status, tester_idx, _, _, _) in enumerate(PLANS):
            for ti in tester_idx:
                await session.execute(
                    testing_plan_testers.insert().values(testing_plan_id=plans[pi].id, user_id=testers[ti].id)
                )

        # ---------- 漏洞 ----------
        vuls: list[Vul] = []
        desc_pool = {
            10: ("攻击者可在无授权情况下访问目标接口并获取敏感业务数据，危害等级评定为严重。",
         "构造恶意请求包直接访问受影响接口，返回包中包含完整业务数据。", "接口增加统一鉴权拦截，按角色最小化授权，并对历史访问日志进行审计。"),
            20: ("目标功能点存在注入类缺陷，攻击者可构造恶意payload执行越权操作。",
         "在请求参数中拼接特殊构造的payload，服务端返回异常数据或执行了非预期逻辑。", "对输入参数进行严格校验与过滤，采用参数化方式处理，修复后回归复测。"),
            30: ("目标功能存在逻辑或信息泄露缺陷，可被利用获取非授权信息。",
         "修改请求中的关键标识参数，服务端未校验归属即返回了其他用户的数据。", "服务端校验资源归属，敏感字段展示前脱敏，补充操作审计日志。"),
            40: ("目标功能存在轻微安全缺陷，影响范围有限。",
         "按常规测试用例复现，确认存在低危风险项。", "按安全开发规范整改，纳入下个迭代验证。"),
        }
        for (title, plan_i, source, level, vtype, status, asset_idx_list,
             submitter_i, months_ago, is_retest, fix_days) in VULNS:
            submit = dt(months_ago, 8 + (len(vuls) % 12), 9 + len(vuls) % 8)
            d, r, s = desc_pool[level]
            v = Vul(
                title=title, vul_type=vtype, level=level, status=status,
                source=source or 0, layer=20 if vtype in (65, 70) else 10,
                affected_url=f"https://{slug[asset_idx_list[0]]}.example.com/api/v1/demo",
                description_html=para(f"漏洞位置：{title}。", d),
                reproduce_html=para("复现步骤：", "1. 登录测试账号进入目标功能；", f"2. {r}", "3. 多次重放确认漏洞稳定可复现。"),
                solution_html=para(s, "整改完成后通知安全组复测。"),
                score={10: 95, 20: 80, 30: 55, 40: 30}[level],
                risk_score={10: 95, 20: 80, 30: 55, 40: 30}[level],
                left_risk_score=0 if status == VulStatus.FIXED else {10: 95, 20: 80, 30: 55, 40: 30}[level],
                is_retest=is_retest,
                testing_plan_id=plans[plan_i].id if plan_i is not None else None,
                submitter_id=testers[submitter_i].id,
                submit_time=submit, audit_time=submit + timedelta(hours=2),
                update_time=submit,
            )
            if status in (VulStatus.FIXING, VulStatus.RETESTING):
                v.notice_time = submit + timedelta(days=2)
            if status in (VulStatus.FIXED,):
                v.notice_time = submit + timedelta(days=2)
                v.fix_time = submit + timedelta(days=fix_days)
                v.update_time = v.fix_time
            elif status in (VulStatus.IGNORED, VulStatus.DEFERRED):
                v.fix_time = submit + timedelta(days=3)
            vuls.append(v)
            session.add(v)
        await session.flush()
        for v, (title, plan_i, source, level, vtype, status, asset_idx_list, *_rest) in zip(vuls, VULNS):
            for ai in asset_idx_list:
                await session.execute(vuln_assets.insert().values(vul_id=v.id, asset_id=assets[ai].id))

        # 工单等级统计回填（与漏洞实际分布一致）
        for pi, plan in enumerate(plans):
            plan_vuls = [v for v, spec in zip(vuls, VULNS) if spec[1] == pi]
            plan.stat_critical = sum(1 for v in plan_vuls if v.level == 10)
            plan.stat_high = sum(1 for v in plan_vuls if v.level == 20)
            plan.stat_medium = sum(1 for v in plan_vuls if v.level == 30)
            plan.stat_low = sum(1 for v in plan_vuls if v.level == 40)

        # ---------- 复测轮次（复测完成工单打两轮，复测中打一轮） ----------
        for pi, plan in enumerate(plans):
            if plan.status == PlanStatus.RETEST_DONE:
                session.add_all([
                    TestingPlanRetestRound(plan_id=plan.id, round_no=1, start_time=dt(12 - pi, 20),
                                           done_time=dt(12 - pi, 25), source="报告发起复测", creator_id=admin.id),
                    TestingPlanRetestRound(plan_id=plan.id, round_no=2, start_time=dt(11 - pi if pi < 11 else 1, 5),
                                           done_time=dt(11 - pi if pi < 11 else 1, 9), source="报告发起复测", creator_id=admin.id),
                ])
            elif plan.status == PlanStatus.RETESTING:
                session.add(TestingPlanRetestRound(plan_id=plan.id, round_no=1,
                                                   start_time=dt(12 - pi, 20), source="报告发起复测", creator_id=admin.id))

        # ---------- 漏洞复测记录 + 操作日志 ----------
        for v, spec in zip(vuls, VULNS):
            status = spec[5]
            if v.is_retest:
                session.add(VulRetestRecord(
                    vul_id=v.id, content_html=para("复测结论：修复有效。",
                        "按原复现步骤重放，目标风险点已消除，业务功能回归正常。", "复测人签字确认，漏洞闭环。"),
                    creator_id=v.submitter_id, username=testers[spec[7]].realname,
                    create_time=(v.fix_time or v.submit_time) + timedelta(hours=1),
                ))
            session.add(VulLog(vul_id=v.id, user_id=v.submitter_id, username=testers[spec[7]].realname,
                               action="提交漏洞", content=f"录入漏洞「{v.title}」", create_time=v.submit_time))
            if v.audit_time:
                session.add(VulLog(vul_id=v.id, user_id=admin.id, username="系统管理员",
                                   action="审核通过", create_time=v.audit_time))
            if v.notice_time:
                session.add(VulLog(vul_id=v.id, user_id=admin.id, username="系统管理员",
                                   action="通知修复", create_time=v.notice_time))
            if v.fix_time and status == VulStatus.FIXED:
                session.add(VulLog(vul_id=v.id, user_id=v.submitter_id,
                                   username=testers[spec[7]].realname,
                                   action="复测通过", content="复测确认修复有效", create_time=v.fix_time))

        # ---------- 报告 ----------
        for plan_i, suffix, rstatus, t_start, t_end in REPORT_TMPL:
            plan = plans[plan_i]
            tester_idx = PLANS[plan_i][6]
            report = Report(
                title=f"{plan.system_name}渗透测试报告-{suffix}" if "复测" in suffix else f"{dt(0,1).strftime('%Y%m%d') if False else '2025' if plan_i < 3 else '2026'}{plan.system_name}渗透测试报告",
                project_name=plan.plan_name, customer="内部安全测试",
                author="、".join(testers[i].realname for i in tester_idx) or admin.realname,
                test_start=t_start, test_end=t_end, status=rstatus,
                target_ip="10.20.0.0/16", actual_mandays=plan.actual_mandays,
                testing_plan_id=plan.id, creator_id=admin.id,
                create_time=datetime.strptime(t_end, "%Y-%m-%d").replace(hour=17),
            )
            if "复测" in suffix:
                report.retest_vul_snapshot = {}
            session.add(report)
            await session.flush()
            plan_vuls = [v for v, spec in zip(vuls, VULNS) if spec[1] == plan_i]
            sections = [
                ReportSection(report_id=report.id, order=0, title="一、测试概述",
                              content_html=para(f"本次测试对象为{plan.system_name}，测试周期 {t_start} 至 {t_end}。",
                                  f"测试范围覆盖身份认证、业务逻辑、数据接口与部署配置。", "测试方法包括黑盒渗透、逻辑校验与配置核查。")),
                ReportSection(report_id=report.id, order=1, title="二、测试风险汇总",
                              content_html=para(f"共发现安全风险 {len(plan_vuls)} 项，按等级分布见正文详述。", "全部风险均已同步业务方整改。")),
            ]
            for si, v in enumerate(plan_vuls):
                sections.append(ReportSection(
                    report_id=report.id, order=2 + si, title=f"风险问题详情：{v.title}",
                    content_html=v.description_html + v.reproduce_html, vul_id=v.id,
                ))
            sections.append(ReportSection(
                report_id=report.id, order=len(sections) + 1, title="六、安全加固建议",
                content_html=para("建议建立安全开发规范并常态化开展上线前安全测试。",
                    "对本次发现的共性问题（鉴权校验、输入过滤）组织专项整改。")))
            session.add_all(sections)

        # ---------- 漏扫基线工单 ----------
        for (pname, sys_i, tt_i, recv, items_spec, link_pi) in NONPEN:
            seq = seq_counter.get(recv, 0) + 1
            seq_counter[recv] = seq
            items = {}
            for key, (label, _desc) in NONPEN_ITEMS.items():
                st, first, retest = items_spec.get(key, ("ignored", 0, 0))
                items[key] = {"status": st, "first_times": first, "retest_times": retest}
            session.add(NonpenPlan(
                plan_name=pname, system_name=assets[sys_i].name, test_type=TEST_TYPES[tt_i],
                department=assets[sys_i].department, receive_time=recv, ticket_time=recv,
                ticket_seq=seq, asset_ids=[assets[sys_i].id], items=items,
                testing_plan_id=plans[link_pi].id if link_pi is not None else None,
                detail="扫描类测试工单", creator_id=admin.id, create_time=datetime.strptime(recv, "%Y-%m-%d"),
            ))

        # ---------- 远程检测 / 春耕行动 ----------
        for (month, sys_i, dept_i, unit, ext, vname, vtype, appeal, method) in REMOTE:
            session.add(RemoteTesting(
                notice_time=month, system_name=assets[sys_i].name, department=DEPARTMENTS[dept_i],
                notified_unit=unit, is_external=ext, vuln_name=vname, vuln_type=vtype,
                appeal_status=appeal, appeal_method=method, creator_id=admin.id,
                create_time=datetime.strptime(month + "-05", "%Y-%m-%d"),
            ))
        for (no, sys_i, year, phase, ok, deduct, doc, vul_idx_list) in SPRING:
            sa = SpringAction(
                report_no=no, system_name=assets[sys_i].name, year=year, phase=phase,
                appeal_success=ok, score_deduction=deduct, doc_no=doc, creator_id=admin.id,
                create_time=datetime.strptime(f"{year}-0{4 + len(no) % 5}-15", "%Y-%m-%d"),
            )
            session.add(sa)
            await session.flush()
            for vi in vul_idx_list:
                await session.execute(spring_action_vulns.insert().values(
                    spring_action_id=sa.id, vul_id=vuls[vi].id))

        # ---------- 知识库（复用 seed_knowledge 的 50 条标准模板） ----------
        for name, vt, sl, desc, harm, sol, refs in SEED_DATA:
            session.add(KnowledgeEntry(
                vulnerability_name=name, vul_type=vt, severity_level=sl,
                description_html=f"<p>{desc}</p>", harm_html=f"<p>{harm}</p>",
                solution_html=f"<p>{sol}</p>", references=list(refs),
                creator_id=admin.id, username=admin.realname,
            ))

        # ---------- 站内消息 ----------
        for v in vuls[:4]:
            session.add(Message(
                user_id=admin.id, msg_type="vuln", title=f"新漏洞提审：{v.title}",
                content=f"{v.title} 已提交审核，请及时处理。", create_time=v.submit_time,
            ))

        await session.commit()

    # 汇总
    async with async_session_maker() as session:
        stats = {}
        for label, sql in [
            ("用户", "SELECT COUNT(*) FROM users"), ("组织", "SELECT COUNT(*) FROM groups"),
            ("资产", "SELECT COUNT(*) FROM assets"), ("渗透工单", "SELECT COUNT(*) FROM testing_plans"),
            ("漏洞", "SELECT COUNT(*) FROM vulns"), ("报告", "SELECT COUNT(*) FROM reports"),
            ("报告章节", "SELECT COUNT(*) FROM report_sections"), ("漏扫工单", "SELECT COUNT(*) FROM nonpen_plans"),
            ("远程检测", "SELECT COUNT(*) FROM remote_testings"), ("春耕行动", "SELECT COUNT(*) FROM spring_actions"),
            ("知识库", "SELECT COUNT(*) FROM knowledge_entries"), ("复测轮次", "SELECT COUNT(*) FROM testing_plan_retest_rounds"),
            ("漏洞日志", "SELECT COUNT(*) FROM vul_logs"), ("复测记录", "SELECT COUNT(*) FROM vul_retest_records"),
        ]:
            stats[label] = (await session.execute(text(sql))).scalar_one()
    print("种子数据完成：" + "，".join(f"{k} {v}" for k, v in stats.items()))


if __name__ == "__main__":
    if "--reset" not in sys.argv:
        print("本脚本会清空 dev.db 全部数据！确认请追加 --reset 参数执行。")
        sys.exit(1)
    asyncio.run(reset_and_seed())
