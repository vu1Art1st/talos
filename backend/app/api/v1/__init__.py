from fastapi import APIRouter

from app.api.v1 import (
    assets,
    auth,
    dashboard,
    imports,
    knowledge,
    misc,
    nonpen,
    remote_testing,
    reports,
    spring_action,
    testing_plan,
    users,
    vulns,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(assets.router)
api_router.include_router(vulns.router)
api_router.include_router(knowledge.router)
api_router.include_router(imports.router)
api_router.include_router(reports.router)
api_router.include_router(remote_testing.router)
api_router.include_router(testing_plan.router)
api_router.include_router(spring_action.router)
api_router.include_router(nonpen.router)
api_router.include_router(dashboard.router)
api_router.include_router(misc.router)
