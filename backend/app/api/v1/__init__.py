from fastapi import APIRouter

from app.api.v1 import assets, auth, dashboard, imports, knowledge, misc, reports, special, users, vulns

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(assets.router)
api_router.include_router(vulns.router)
api_router.include_router(knowledge.router)
api_router.include_router(imports.router)
api_router.include_router(reports.router)
api_router.include_router(special.router)
api_router.include_router(dashboard.router)
api_router.include_router(misc.router)
