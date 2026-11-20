"""租户管理 API（平台管理员专用）。

普通租户管理员没有 ``tenant:*`` 权限，调用会被 403 拒绝。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import require_permission
from database import get_db
from saas import subscription, tenant_manager

router = APIRouter(prefix="/tenants", tags=["租户管理"])


class TenantCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    admin_username: str = Field(min_length=2, max_length=50)
    admin_password: str = Field(min_length=6, max_length=72)
    plan_code: str = "free"


class TenantUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    status: Optional[str] = None
    plan_code: Optional[str] = None


class TenantInfo(BaseModel):
    id: int
    code: str
    name: str
    status: str
    plan_code: str
    created_at: Optional[str] = None
    user_count: Optional[int] = None


def _serialize(db: Session, tenant) -> TenantInfo:
    return TenantInfo(**tenant_manager.serialize(tenant, tenant_manager.count_users(db, tenant.id)))


@router.get(
    "",
    response_model=List[TenantInfo],
    dependencies=[Depends(require_permission("tenant:view"))],
)
async def list_all_tenants(db: Session = Depends(get_db)):
    """列出全部租户（平台管理员）"""
    return [_serialize(db, tenant) for tenant in tenant_manager.list_tenants(db)]


@router.post(
    "",
    response_model=TenantInfo,
    dependencies=[Depends(require_permission("tenant:manage"))],
)
async def create_tenant(req: TenantCreateRequest, db: Session = Depends(get_db)):
    """开通租户，并创建该租户的管理员账号"""
    try:
        tenant = tenant_manager.create_tenant(
            db,
            code=req.code,
            name=req.name,
            admin_username=req.admin_username,
            admin_password=req.admin_password,
            plan_code=req.plan_code,
        )
    except tenant_manager.TenantConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except tenant_manager.TenantError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    subscription.ensure_subscription(db, tenant.id)
    return _serialize(db, tenant)


@router.get(
    "/{tenant_id}",
    response_model=TenantInfo,
    dependencies=[Depends(require_permission("tenant:view"))],
)
async def get_tenant_detail(tenant_id: int, db: Session = Depends(get_db)):
    """租户详情"""
    tenant = tenant_manager.get_tenant(db, tenant_id=tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="租户不存在")
    return _serialize(db, tenant)


@router.patch(
    "/{tenant_id}",
    response_model=TenantInfo,
    dependencies=[Depends(require_permission("tenant:manage"))],
)
async def update_tenant(tenant_id: int, req: TenantUpdateRequest, db: Session = Depends(get_db)):
    """更新租户名称、状态或套餐"""
    try:
        tenant = tenant_manager.update_tenant(
            db,
            tenant_id,
            name=req.name,
            status=req.status,
        )
        if req.plan_code:
            subscription.set_plan(db, tenant_id, req.plan_code)
    except tenant_manager.TenantError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except subscription.SubscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(db, tenant)
