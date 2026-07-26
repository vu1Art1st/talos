from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_perm
from app.db import get_session
from app.models import App, Asset, User, Vul
from app.schemas import AppIn, AppOut, AssetIn, AssetOut, Page

router = APIRouter(tags=["应用与资产"])


# ---------- 应用 ----------
@router.get("/apps", response_model=Page[AppOut])
async def list_apps(
    search: str = "",
    status: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(App.name.ilike(f"%{search}%") | App.url.ilike(f"%{search}%"))
    if status is not None:
        cond.append(App.status == status)
    total = (await session.execute(select(func.count(App.id)).where(*cond))).scalar_one()
    items = (
        await session.execute(
            select(App).where(*cond).order_by(App.id.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return Page(total=total, items=items)


@router.post("/apps", response_model=AppOut)
async def create_app_item(
    body: AppIn,
    _: User = Depends(require_perm("app:manage")),
    session: AsyncSession = Depends(get_session),
):
    app = App(**body.model_dump())
    session.add(app)
    await session.commit()
    await session.refresh(app)
    return app


@router.put("/apps/{app_id}", response_model=AppOut)
async def update_app_item(
    app_id: int,
    body: AppIn,
    _: User = Depends(require_perm("app:manage")),
    session: AsyncSession = Depends(get_session),
):
    app = await session.get(App, app_id)
    if app is None:
        raise HTTPException(404, "应用不存在")
    for k, v in body.model_dump().items():
        setattr(app, k, v)
    await session.commit()
    await session.refresh(app)
    return app


@router.delete("/apps/{app_id}")
async def delete_app_item(
    app_id: int,
    _: User = Depends(require_perm("app:manage")),
    session: AsyncSession = Depends(get_session),
):
    used = (await session.execute(select(func.count(Vul.id)).where(Vul.app_id == app_id))).scalar_one()
    if used:
        raise HTTPException(400, "该应用下存在漏洞记录，无法删除")
    app = await session.get(App, app_id)
    if app:
        await session.delete(app)
        await session.commit()
    return {"msg": "删除成功"}


# ---------- 资产 ----------
@router.get("/assets", response_model=Page[AssetOut])
async def list_assets(
    search: str = "",
    app_id: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(Asset.value.ilike(f"%{search}%"))
    if app_id is not None:
        cond.append(Asset.app_id == app_id)
    total = (await session.execute(select(func.count(Asset.id)).where(*cond))).scalar_one()
    items = (
        await session.execute(
            select(Asset).where(*cond).order_by(Asset.id.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return Page(total=total, items=items)


@router.post("/assets", response_model=AssetOut)
async def create_asset(
    body: AssetIn,
    _: User = Depends(require_perm("asset:manage")),
    session: AsyncSession = Depends(get_session),
):
    asset = Asset(**body.model_dump())
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset


@router.put("/assets/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: int,
    body: AssetIn,
    _: User = Depends(require_perm("asset:manage")),
    session: AsyncSession = Depends(get_session),
):
    asset = await session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(404, "资产不存在")
    for k, v in body.model_dump().items():
        setattr(asset, k, v)
    await session.commit()
    await session.refresh(asset)
    return asset


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: int,
    _: User = Depends(require_perm("asset:manage")),
    session: AsyncSession = Depends(get_session),
):
    asset = await session.get(Asset, asset_id)
    if asset:
        await session.delete(asset)
        await session.commit()
    return {"msg": "删除成功"}
