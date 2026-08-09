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
    """测试计划复测轮次记录：每次发起复测新增一轮，全部漏洞闭环后打完成点。"""

    __tablename__ = "testing_plan_retest_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("testing_plans.id", ondelete="CASCADE"), index=True)
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    done_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="")  # 触发来源，如报告发起/手动流转
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    plan: Mapped[TestingPlan] = relationship(back_populates="retest_rounds")


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
