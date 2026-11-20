"""订阅套餐与配额。

套餐目录内置在代码里（``PLANS``），租户订阅记录在 ``subscriptions`` 表
（一个租户一条有效订阅）。配额目前约束两项：可接入工位数、数据保留天数。

``tenants.plan_code`` 是当前套餐的冗余副本，由 :func:`set_plan` 统一维护，
避免出现两处不一致。
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from db_models import SubscriptionDB, TenantDB

PLANS = {
    "free": {
        "code": "free",
        "name": "体验版",
        "price_month": 0,
        "max_stations": 1,
        "retention_days": 7,
        "features": ["基础识别", "单工位", "7 天数据保留"],
    },
    "standard": {
        "code": "standard",
        "name": "标准版",
        "price_month": 999,
        "max_stations": 5,
        "retention_days": 30,
        "features": ["基础识别", "异常告警", "报告导出", "30 天数据保留"],
    },
    "pro": {
        "code": "pro",
        "name": "专业版",
        "price_month": 2999,
        "max_stations": 20,
        "retention_days": 365,
        "features": ["异常告警", "报告导出", "多工位看板", "1 年数据保留"],
    },
    "enterprise": {
        "code": "enterprise",
        "name": "企业版",
        "price_month": None,
        "max_stations": None,
        "retention_days": None,
        "features": ["私有部署", "定制开发", "不限工位与存储"],
    },
}

DEFAULT_PLAN_CODE = "free"
_ACTIVE_STATUSES = ("active",)


class SubscriptionError(ValueError):
    """订阅操作失败（未知套餐、时间格式错误等）。"""


def list_plans() -> List[dict]:
    return [dict(plan) for plan in PLANS.values()]


def get_plan(plan_code: str) -> dict:
    plan = PLANS.get((plan_code or "").strip().lower())
    if not plan:
        raise SubscriptionError("未知套餐: {}".format(plan_code))
    return dict(plan)


def get_subscription(db: Session, tenant_id: int) -> Optional[SubscriptionDB]:
    return (
        db.query(SubscriptionDB)
        .filter(SubscriptionDB.tenant_id == tenant_id)
        .first()
    )


def ensure_subscription(db: Session, tenant_id: int) -> SubscriptionDB:
    subscription = get_subscription(db, tenant_id)
    if subscription:
        return subscription
    subscription = SubscriptionDB(
        tenant_id=tenant_id,
        plan_code=DEFAULT_PLAN_CODE,
        status="active",
        started_at=datetime.now(),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def set_plan(
    db: Session,
    tenant_id: int,
    plan_code: str,
    expires_at: Optional[datetime] = None,
) -> SubscriptionDB:
    plan = get_plan(plan_code)
    subscription = ensure_subscription(db, tenant_id)

    subscription.plan_code = plan["code"]
    subscription.status = "active"
    subscription.expires_at = expires_at

    tenant = db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    if tenant is not None:
        tenant.plan_code = plan["code"]

    db.commit()
    db.refresh(subscription)
    return subscription


def is_expired(subscription: Optional[SubscriptionDB]) -> bool:
    if subscription is None:
        return False
    if subscription.status not in _ACTIVE_STATUSES:
        return True
    if subscription.expires_at is not None and subscription.expires_at < datetime.now():
        return True
    return False


def is_tenant_expired(db: Session, tenant_id: int) -> bool:
    return is_expired(get_subscription(db, tenant_id))


def limits_for(db: Session, tenant_id: int) -> dict:
    subscription = ensure_subscription(db, tenant_id)
    plan = get_plan(subscription.plan_code)
    return {
        "tenant_id": tenant_id,
        "plan_code": plan["code"],
        "plan_name": plan["name"],
        "price_month": plan["price_month"],
        "max_stations": plan["max_stations"],
        "retention_days": plan["retention_days"],
        "features": plan["features"],
        "status": subscription.status,
        "started_at": subscription.started_at.isoformat() if subscription.started_at else None,
        "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
        "expired": is_expired(subscription),
    }
