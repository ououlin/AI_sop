"""订阅套餐与租户订阅 API（平台管理员）。"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import require_permission
from database import get_db
from saas import subscription, tenant_manager

router = APIRouter(prefix="/tenants", tags=["订阅"])
plans_router = APIRouter(prefix="/plans", tags=["订阅"])


class PlanInfo(BaseModel):
    code: str
    name: str
    price_month: Optional[int]
    max_stations: Optional[int]
    retention_days: Optional[int]
    features: List[str]


class SubscriptionUpdateRequest(BaseModel):
    plan_code: str
    expires_at: Optional[str] = None


@plans_router.get(
    "",
    response_model=List[PlanInfo],
    dependencies=[Depends(require_permission("tenant:view"))],
)
async def list_plans():
    """套餐目录"""
    return subscription.list_plans()


@router.get(
    "/{tenant_id}/subscription",
    dependencies=[Depends(require_permission("tenant:view"))],
)
async def get_tenant_subscription(tenant_id: int, db: Session = Depends(get_db)):
    """租户当前套餐、配额与到期状态"""
    if not tenant_manager.get_tenant(db, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail="租户不存在")
    return subscription.limits_for(db, tenant_id)


@router.put(
    "/{tenant_id}/subscription",
    dependencies=[Depends(require_permission("tenant:manage"))],
)
async def update_tenant_subscription(
    tenant_id: int,
    req: SubscriptionUpdateRequest,
    db: Session = Depends(get_db),
):
    """变更套餐（可同时设置到期时间，ISO 8601）"""
    if not tenant_manager.get_tenant(db, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail="租户不存在")

    expires_at = None
    if req.expires_at:
        try:
            expires_at = datetime.fromisoformat(req.expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="expires_at 需为 ISO 8601 时间")

    try:
        subscription.set_plan(db, tenant_id, req.plan_code, expires_at)
    except subscription.SubscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return subscription.limits_for(db, tenant_id)
