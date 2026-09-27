"""P2-1 数据范围：把用户角色与组织成员关系转换为业务查询的统一过滤条件。

设计约束：
- 路由不得各自用 `department=` 参数模拟权限；数据范围由认证依赖写入 session.info，
  由 SQLAlchemy `do_orm_execute` 对业务实体统一注入。
- `*` 角色始终为 `all`；其余角色按 `roles.data_scope` 执行 `department/own/none`。
- 无组织归属的 department 用户不获得全量兜底，由管理员先补齐组织关系。
"""
from dataclasses import dataclass

from sqlalchemy import event, false, or_, select, true
from sqlalchemy.orm import Session, with_loader_criteria

from app.models import (
    Asset,
    DashboardView,
    ExportJob,
    GroupUser,
    ImportBatch,
    ImportRecord,
    Message,
    NotificationChannel,
    NonpenPlan,
    NotifyDelivery,
    OperationLog,
    PersonalAccessToken,
    RemoteTesting,
    Report,
    ReportSection,
    ReportTemplate,
    SlaExtension,
    SpringAction,
    TestingPlan,
    TestingPlanRetestRound,
    User,
    Vul,
    VulLog,
    VulRetestRecord,
)

_INFO_KEY = "data_scope"
_VALID_MODES = {"all", "department", "own", "none"}


@dataclass(frozen=True)
class DataScope:
    """一次请求内稳定的数据范围快照。"""

    user_id: int
    mode: str
    group_ids: tuple[int, ...] = ()
    group_names: tuple[str, ...] = ()
    group_user_ids: tuple[int, ...] = ()

    @property
    def restricted(self) -> bool:
        return self.mode != "all"


async def install_data_scope(session, user: User) -> DataScope:
    """解析用户角色 / 组织归属并写入 session.info；后续 ORM SELECT 自动应用。"""
    perms = set(user.role.permissions or []) if user.role else set()
    role_scope = getattr(user.role, "data_scope", "department") if user.role else "none"
    mode = "all" if "*" in perms or role_scope == "all" else role_scope
    if mode not in _VALID_MODES:
        mode = "none"

    groups = list(getattr(user, "groups", []) or [])
    group_ids = tuple(sorted({int(g.id) for g in groups}))
    group_names = tuple(sorted({str(g.name) for g in groups if g.name}))
    group_user_ids: tuple[int, ...] = ()
    if mode == "department" and group_ids:
        rows = (
            await session.execute(
                select(GroupUser.user_id).where(GroupUser.group_id.in_(group_ids))
            )
        ).scalars().all()
        group_user_ids = tuple(sorted({int(uid) for uid in rows}))

    scope = DataScope(
        user_id=int(user.id),
        mode=mode,
        group_ids=group_ids,
        group_names=group_names,
        group_user_ids=group_user_ids,
    )
    session.info[_INFO_KEY] = scope
    return scope


def current_data_scope(session) -> DataScope | None:
    return session.info.get(_INFO_KEY)


def _false():
    return false()


def _or(conds: list):
    return or_(*conds) if conds else _false()


def _plan_department_condition(scope: DataScope):
    conds = []
    if scope.group_names:
        conds.append(TestingPlan.department.in_(scope.group_names))
    if scope.group_user_ids:
        conds.append(TestingPlan.creator_id.in_(scope.group_user_ids))
        conds.append(TestingPlan.testers.any(User.id.in_(scope.group_user_ids)))
    return _or(conds)


def _plan_own_condition(scope: DataScope):
    return or_(
        TestingPlan.creator_id == scope.user_id,
        TestingPlan.testers.any(User.id == scope.user_id),
    )


def _asset_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode != "department":
        return _false()
    conds = []
    if scope.group_ids:
        conds.append(Asset.group_id.in_(scope.group_ids))
    if scope.group_names:
        conds.append(Asset.department.in_(scope.group_names))
    return _or(conds)


def _plan_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return _plan_own_condition(scope)
    if scope.mode == "department":
        return _plan_department_condition(scope)
    return _false()


def _vul_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return Vul.submitter_id == scope.user_id
    if scope.mode != "department":
        return _false()
    conds = [
        Vul.assets.any(_asset_condition(scope)),
        Vul.testing_plan_id.in_(select(TestingPlan.id).where(_plan_department_condition(scope))),
    ]
    if scope.group_user_ids:
        conds.append(Vul.submitter_id.in_(scope.group_user_ids))
    return _or(conds)


def _nonpen_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return NonpenPlan.creator_id == scope.user_id
    if scope.mode != "department":
        return _false()
    conds = []
    if scope.group_names:
        conds.append(NonpenPlan.department.in_(scope.group_names))
    if scope.group_user_ids:
        conds.append(NonpenPlan.creator_id.in_(scope.group_user_ids))
    return _or(conds)


def _report_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return or_(
            Report.creator_id == scope.user_id,
            Report.testing_plan_id.in_(
                select(TestingPlan.id).where(_plan_own_condition(scope))
            ),
        )
    if scope.mode != "department":
        return _false()
    conds = [
        Report.testing_plan_id.in_(
            select(TestingPlan.id).where(_plan_department_condition(scope))
        ),
    ]
    if scope.group_user_ids:
        conds.append(Report.creator_id.in_(scope.group_user_ids))
    return _or(conds)


def _import_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return ImportBatch.creator_id == scope.user_id
    if scope.mode == "department" and scope.group_user_ids:
        return ImportBatch.creator_id.in_(scope.group_user_ids)
    return _false()


def _remote_testing_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return RemoteTesting.creator_id == scope.user_id
    if scope.mode != "department":
        return _false()
    conds = []
    if scope.group_names:
        conds.append(RemoteTesting.department.in_(scope.group_names))
    conds.append(RemoteTesting.asset_id.in_(select(Asset.id).where(_asset_condition(scope))))
    if scope.group_user_ids:
        conds.append(RemoteTesting.creator_id.in_(scope.group_user_ids))
    return _or(conds)


def _spring_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return SpringAction.creator_id == scope.user_id
    if scope.mode != "department":
        return _false()
    return or_(
        SpringAction.creator_id.in_(scope.group_user_ids) if scope.group_user_ids else false(),
        SpringAction.vuls.any(Vul.id.in_(select(Vul.id).where(_vul_condition(scope)))),
    )


def _message_condition(scope: DataScope):
    return true() if scope.mode == "all" else Message.user_id == scope.user_id


def _operation_log_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    ids = set(scope.group_user_ids)
    ids.add(scope.user_id)
    return OperationLog.user_id.in_(ids)


def _dashboard_view_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    conds = [DashboardView.user_id == scope.user_id]
    if scope.mode == "department" and scope.group_names:
        conds.append(DashboardView.department.in_(scope.group_names))
    return _or(conds)


def _user_condition(scope: DataScope):
    if scope.mode == "all":
        return true()
    if scope.mode == "own":
        return User.id == scope.user_id
    if scope.mode == "department":
        return User.id.in_(scope.group_user_ids) if scope.group_user_ids else _false()
    return _false()


def _vul_child_condition(scope: DataScope):
    return select(Vul.id).where(_vul_condition(scope))


def _report_child_condition(scope: DataScope):
    return select(Report.id).where(_report_condition(scope))


def _import_child_condition(scope: DataScope):
    return select(ImportBatch.id).where(_import_condition(scope))


def _testing_round_condition(scope: DataScope):
    return select(TestingPlan.id).where(_plan_condition(scope))


def _scope_condition(scope: DataScope, model):
    if model is Asset:
        return _asset_condition(scope)
    if model is Vul:
        return _vul_condition(scope)
    if model is TestingPlan:
        return _plan_condition(scope)
    if model is NonpenPlan:
        return _nonpen_condition(scope)
    if model is Report:
        return _report_condition(scope)
    if model is ImportBatch:
        return _import_condition(scope)
    if model is RemoteTesting:
        return _remote_testing_condition(scope)
    if model is SpringAction:
        return _spring_condition(scope)
    if model is Message:
        return _message_condition(scope)
    if model is OperationLog:
        return _operation_log_condition(scope)
    if model is DashboardView:
        return _dashboard_view_condition(scope)
    if model is User:
        return _user_condition(scope)
    if model is PersonalAccessToken:
        return model.user_id == scope.user_id
    if model in (NotificationChannel, NotifyDelivery, ReportTemplate):
        return _false()
    if model is VulRetestRecord or model is VulLog or model is SlaExtension:
        return model.vul_id.in_(_vul_child_condition(scope))
    if model is ReportSection:
        return model.report_id.in_(_report_child_condition(scope))
    if model is ExportJob:
        if scope.mode == "own":
            return or_(
                ExportJob.creator_id == scope.user_id,
                ExportJob.report_id.in_(_report_child_condition(scope)),
            )
        return or_(
            ExportJob.creator_id.in_(scope.group_user_ids) if scope.group_user_ids else false(),
            ExportJob.report_id.in_(_report_child_condition(scope)),
        )
    if model is ImportRecord:
        return model.batch_id.in_(_import_child_condition(scope))
    if model is TestingPlanRetestRound:
        return model.plan_id.in_(_testing_round_condition(scope))
    return None


_SCOPED_MODELS = (
    Asset,
    Vul,
    TestingPlan,
    NonpenPlan,
    Report,
    ImportBatch,
    RemoteTesting,
    SpringAction,
    Message,
    OperationLog,
    DashboardView,
    User,
    PersonalAccessToken,
    NotificationChannel,
    NotifyDelivery,
    ReportTemplate,
    VulRetestRecord,
    VulLog,
    SlaExtension,
    ReportSection,
    ExportJob,
    ImportRecord,
    TestingPlanRetestRound,
)


@event.listens_for(Session, "do_orm_execute")
def _apply_data_scope(orm_execute_state) -> None:
    """对已安装 scope 的 session 自动注入 ORM 查询条件。"""
    if not orm_execute_state.is_select:
        return
    if orm_execute_state.execution_options.get("_talos_scope_bound"):
        return
    scope = orm_execute_state.session.info.get(_INFO_KEY)
    if not scope or not scope.restricted:
        return
    for model in _SCOPED_MODELS:
        criterion = _scope_condition(scope, model)
        if criterion is not None:
            orm_execute_state.statement = orm_execute_state.statement.options(
                with_loader_criteria(
                    model,
                    criterion,
                    include_aliases=True,
                    track_closure_variables=False,
                )
            )


def bound_scope_statement(session, stmt):
    """显式应用当前 scope，供需要严格保证的统计/导出 SQL 调用。"""
    scope = current_data_scope(session)
    if not scope or not scope.restricted:
        return stmt
    for model in _SCOPED_MODELS:
        criterion = _scope_condition(scope, model)
        if criterion is not None:
            stmt = stmt.options(
                with_loader_criteria(
                    model,
                    criterion,
                    include_aliases=True,
                    track_closure_variables=False,
                )
            )
    return stmt.execution_options(_talos_scope_bound=True)


def unscoped_statement(stmt):
    """显式绕过业务 scope：仅用于全局唯一性预检，不得用于返回业务数据。"""
    return stmt.execution_options(_talos_scope_bound=True)
