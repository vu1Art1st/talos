"""专项管理：远程检测 / 测试计划 / 春耕行动。"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TestingPlan(Base):
    """测试计划。status 见 constants.TESTING_PLAN_STATUS。"""

    __tablename__ = "testing_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    system_name: Mapped[str] = mapped_column(String(128), index=True)
    test_type: Mapped[str] = mapped_column(String(64), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    receive_time: Mapped[str] = mapped_column(String(32), default="")
    first_test_done_time: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[int] = mapped_column(Integer, default=10)
    retest_notice_time: Mapped[str] = mapped_column(String(32), default="")
    retest_done_time: Mapped[str] = mapped_column(String(32), default="")
    stat_critical: Mapped[int] = mapped_column(Integer, default=0)
    stat_high: Mapped[int] = mapped_column(Integer, default=0)
    stat_medium: Mapped[int] = mapped_column(Integer, default=0)
    stat_low: Mapped[int] = mapped_column(Integer, default=0)
    brief: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")  # 测试人员、数据来源等
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    @property
    def tester_ids(self) -> list[int]:
        return [u.id for u in self.testers]

    @property
    def retest_round_count(self) -> int:
        return len(self.retest_rounds)


class TestingPlanRetestRound(Base):
    """测试计划复测轮次记录：每次发起复测新增一轮，全部漏洞闭环后打完成点。"""

    __tablename__ = "testing_plan_retest_rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("testing_plans.id", ondelete="CASCADE"), index=True)
    round_no: Mapped[int] = mapped_column(Integer, default=1)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    vuls: Mapped[list[Vul]] = relationship(secondary=spring_action_vulns, lazy="selectin")

    @property
    def vul_ids(self) -> list[int]:
        return [v.id for v in self.vuls]
