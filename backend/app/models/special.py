"""专项管理：远程检测 / 测试计划 / 春耕行动。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import now
from app.db import Base
from app.models.business import Vul
from app.models.user import User

# 春耕行动-漏洞多对多关联表
spring_action_vulns = Table(
    "spring_action_vulns",
    Base.metadata,
    Column("spring_action_id", ForeignKey("spring_actions.id", ondelete="CASCADE"), primary_key=True),
    Column("vul_id", ForeignKey("vulns.id"), primary_key=True),
    UniqueConstraint("spring_action_id", "vul_id", name="uq_spring_action_vul"),
)

# 测试计划-测试人员（认领者）多对多关联表
testing_plan_testers = Table(
    "testing_plan_testers",
    Base.metadata,
    Column("testing_plan_id", ForeignKey("testing_plans.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    UniqueConstraint("testing_plan_id", "user_id", name="uq_testing_plan_tester"),
)


class RemoteTesting(Base):
    """远程检测记录。"""

    __tablename__ = "remote_testings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    system_name: Mapped[str] = mapped_column(String(128), default="")
    test_time: Mapped[str] = mapped_column(String(32), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    appeal_success: Mapped[bool] = mapped_column(Boolean, default=False)
    appeal_report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class TestingPlan(Base):
    """测试计划。status 见 constants.TESTING_PLAN_STATUS。"""

    __tablename__ = "testing_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_name: Mapped[str] = mapped_column(String(128), index=True)
    plan_name: Mapped[str] = mapped_column(String(128), default="")  # 测试计划名称，与测试系统区分
    test_type: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    receive_time: Mapped[str] = mapped_column(String(32), default="")
    ticket_time: Mapped[str] = mapped_column(String(32), default="")  # 工单提起时间
    ticket_seq: Mapped[int] = mapped_column(Integer, default=0)  # 当日录入次序，配合 receive_time 生成 ticket_id
    ticket_id_manual: Mapped[str] = mapped_column(String(64), default="")  # 手动指定的工单ID，优先于自动生成
    first_test_done_time: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[int] = mapped_column(Integer, default=10)
    retest_notice_time: Mapped[str] = mapped_column(String(32), default="")
    retest_done_time: Mapped[str] = mapped_column(String(32), default="")
    stat_critical: Mapped[int] = mapped_column(Integer, default=0)
    stat_high: Mapped[int] = mapped_column(Integer, default=0)
    stat_medium: Mapped[int] = mapped_column(Integer, default=0)
    stat_low: Mapped[int] = mapped_column(Integer, default=0)
    est_mandays: Mapped[float] = mapped_column(Float, default=0)  # 预估人天
    actual_mandays: Mapped[float] = mapped_column(Float, default=0)  # 实际人天
    # 实际人天手动修正标志：修正后不再被初测报告自动覆盖；取消修正后恢复自动计算
    actual_mandays_override: Mapped[bool] = mapped_column(Boolean, default=False)
    asset_ids: Mapped[list | None] = mapped_column(JSON, default=list)  # 关联资产ID数组，前置至计划编制
    brief: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")  # 测试人员、数据来源等
    # 无漏洞闭环：确认「测试通过（未发现安全漏洞）」时记录的测试结论，重开计划时保留以便追溯
    no_vul_conclusion: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    testers: Mapped[list[User]] = relationship(secondary=testing_plan_testers, lazy="selectin")
    vuls: Mapped[list[Vul]] = relationship(
        primaryjoin="Vul.testing_plan_id == TestingPlan.id",
        foreign_keys="Vul.testing_plan_id",
        viewonly=True,
        lazy="selectin",
    )
    retest_rounds: Mapped[list["TestingPlanRetestRound"]] = relationship(
        back_populates="plan",
        order_by="TestingPlanRetestRound.round_no",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # 反向展示已关联报告（Report.testing_plan_id 外键）。删除计划时在 API 层解除外键，故 viewonly。
    reports: Mapped[list["Report"]] = relationship(  # noqa: F821
        primaryjoin="Report.testing_plan_id == TestingPlan.id",
        foreign_keys="Report.testing_plan_id",
        viewonly=True,
        order_by="Report.id",
        lazy="selectin",
    )

    @property
    def tester_ids(self) -> list[int]:
        return [u.id for u in self.testers]

    @property
    def retest_round_count(self) -> int:
        return len(self.retest_rounds)

    @property
    def ticket_id(self) -> str:
        """工单ID：优先返回手动指定值；否则按需求接收日期自动生成 YYYYMMDD-N。"""
        if self.ticket_id_manual:
            return self.ticket_id_manual
        if not self.receive_time or self.ticket_seq == 0:
            return ""
        date_str = self.receive_time.replace("-", "")[:8]
        return f"{date_str}-{self.ticket_seq}"


class TestingPlanRetestRound(Base):
    """测试计划复测轮次记录：每次发起复测新增一轮，全部漏洞闭环后打完成点。

    report_id 记录触发该轮次的复测报告：删除该报告时回退对应轮次，保证复测轮数与报告一致。
    """

    __tablename__ = "testing_plan_retest_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("testing_plans.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id", ondelete="SET NULL"), nullable=True, index=True,
    )  # 触发轮次的复测报告ID，删除该报告时回退对应轮次
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    done_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="")  # 触发来源，如报告发起/手动流转
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    plan: Mapped[TestingPlan] = relationship(back_populates="retest_rounds")


class NonpenPlan(Base):
    """漏扫基线工单：主机/Web/基线扫描类测试，与测试计划平级、独立统计。

    - 工单ID（ticket_id）与测试计划共享当日序号序列：ticket_seq / ticket_id_manual
      语义与 TestingPlan 完全一致（手动指定优先，否则 receive_time 日期 + 当日序号）。
    - items 为 JSON 容器：{key: {status, first_times, retest_times}}，三类测试项
      （baseline/host/web）独立流转：未开始→初测中→等待复测→复测中→复测完成，
      任意阶段可忽略（ignored，取消忽略回未开始且次数清零）；未勾选项 status='ignored'。
    - testing_plan_id 非空表示由「测试计划」联动创建（列表展示「联动」角标）：
      编辑公共字段与来源测试计划双向同步，删除任一方互相级联。
    - 不关联漏洞/报告/人天，保持扫描类业务逻辑独立。
    """

    __tablename__ = "nonpen_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_name: Mapped[str] = mapped_column(String(128), default="")  # 计划名称，与测试系统区分
    system_name: Mapped[str] = mapped_column(String(128), index=True)
    test_type: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    ticket_time: Mapped[str] = mapped_column(String(32), default="")  # 工单提起时间
    receive_time: Mapped[str] = mapped_column(String(32), default="")  # 需求接收时间
    ticket_seq: Mapped[int] = mapped_column(Integer, default=0)  # 当日序号（与测试计划共享序列）
    ticket_id_manual: Mapped[str] = mapped_column(String(64), default="")  # 手动指定工单ID
    asset_ids: Mapped[list | None] = mapped_column(JSON, default=list)  # 关联资产ID数组
    items: Mapped[dict | None] = mapped_column(JSON, default=dict)  # 测试项状态与次数容器
    testing_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("testing_plans.id"), nullable=True, index=True,
    )  # 联动来源测试计划ID
    detail: Mapped[str] = mapped_column(Text, default="")  # 详细描述
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    @property
    def ticket_id(self) -> str:
        """工单ID：优先返回手动指定值；否则按需求接收日期自动生成 YYYYMMDD-N（与测试计划同序列）。"""
        if self.ticket_id_manual:
            return self.ticket_id_manual
        if not self.receive_time or self.ticket_seq == 0:
            return ""
        date_str = self.receive_time.replace("-", "")[:8]
        return f"{date_str}-{self.ticket_seq}"

    @property
    def linked(self) -> bool:
        """是否由测试计划联动创建（列表展示「联动」角标）。"""
        return self.testing_plan_id is not None

    @property
    def actionable(self) -> bool:
        """「可进行」判定：存在至少一个非忽略测试项处于可测试状态（未开始/初测中/复测中）。
        等待复测不视作可进行——测试人员在等待业务系统提交复测，无测试人员可执行的操作。"""
        for state in (self.items or {}).values():
            if state.get("status") in ("not_started", "testing", "retesting"):
                return True
        return False


class SpringAction(Base):
    """春耕行动记录。"""

    __tablename__ = "spring_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_no: Mapped[str] = mapped_column(String(128), index=True)  # 原始报告编号
    system_name: Mapped[str] = mapped_column(String(128), default="")
    year: Mapped[str] = mapped_column(String(8), default="")  # 年度，如 2026
    phase: Mapped[str] = mapped_column(String(64), default="")  # 阶段，如 第一阶段
    appeal_success: Mapped[bool] = mapped_column(Boolean, default=False)
    score_deduction: Mapped[float] = mapped_column(Float, default=0)  # 最终扣分数值
    doc_no: Mapped[str] = mapped_column(String(128), default="")  # 对应公文文号
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    vuls: Mapped[list[Vul]] = relationship(secondary=spring_action_vulns, lazy="selectin")

    @property
    def vul_ids(self) -> list[int]:
        return [v.id for v in self.vuls]
