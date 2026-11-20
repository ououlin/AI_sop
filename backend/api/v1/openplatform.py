"""开放平台 API。

- ``/api-keys``、``/webhooks``：租户管理员用 JWT 管理凭据与订阅
- ``/open/*``：第三方系统用 ``X-API-Key`` 访问，租户由 Key 决定
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from analytics.metrics_calculator import compute_overview
from auth.dependencies import require_permission
from database import get_db
from db_models import ExecutionRecord, StepRecord
from openplatform import api_gateway, webhook_dispatcher
from openplatform.webhook_manager import WebhookError
from openplatform.adapters import execution_to_mes
from repositories.record_repo import RecordRepository
from repositories.sop_repo import SOPRepository
from tenancy.context import get_tenant_id

api_keys_router = APIRouter(prefix="/api-keys", tags=["开放平台"])
webhooks_router = APIRouter(prefix="/webhooks", tags=["开放平台"])
open_router = APIRouter(prefix="/open", tags=["开放平台"])


# ============ 请求/响应模型 ============

class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: List[str] = Field(default_factory=lambda: ["read"])


class ApiKeyInfo(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: List[str]
    active: bool
    created_at: Optional[str] = None
    last_used_at: Optional[str] = None


class WebhookCreateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    events: List[str] = Field(default_factory=list)
    secret: str = ""


class WebhookInfo(BaseModel):
    id: int
    url: str
    events: List[str]
    active: bool
    created_at: Optional[str] = None


def _key_info(record) -> ApiKeyInfo:
    return ApiKeyInfo(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        scopes=api_gateway.scopes_of(record),
        active=bool(record.active),
        created_at=record.created_at.isoformat() if record.created_at else None,
        last_used_at=record.last_used_at.isoformat() if record.last_used_at else None,
    )


def _webhook_info(record) -> WebhookInfo:
    try:
        events = json.loads(record.events or "[]")
    except json.JSONDecodeError:
        events = []
    return WebhookInfo(
        id=record.id,
        url=record.url,
        events=events,
        active=bool(record.active),
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


# ============ API Key 管理 ============

@api_keys_router.get(
    "",
    response_model=List[ApiKeyInfo],
    dependencies=[Depends(require_permission("user:manage"))],
)
async def list_api_keys(db: Session = Depends(get_db)):
    return [_key_info(item) for item in api_gateway.list_keys(db, get_tenant_id())]


@api_keys_router.post(
    "",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def create_api_key(req: ApiKeyCreateRequest, db: Session = Depends(get_db)):
    """创建 API Key，明文只在本次响应返回"""
    try:
        record, raw = api_gateway.create_key(
            db, get_tenant_id(), req.name, req.scopes
        )
    except api_gateway.ApiKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": record.id, "name": record.name, "key": raw, "scopes": api_gateway.scopes_of(record)}


@api_keys_router.delete(
    "/{key_id}",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def revoke_api_key(key_id: int, db: Session = Depends(get_db)):
    if not api_gateway.revoke_key(db, get_tenant_id(), key_id):
        raise HTTPException(status_code=404, detail="API Key 不存在")
    return {"ok": True}


# ============ Webhook 管理 ============

@webhooks_router.get(
    "",
    response_model=List[WebhookInfo],
    dependencies=[Depends(require_permission("user:manage"))],
)
async def list_webhooks(db: Session = Depends(get_db)):
    records = webhook_dispatcher.list_subscriptions(db, get_tenant_id())
    return [_webhook_info(item) for item in records]


@webhooks_router.post(
    "",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def create_webhook(req: WebhookCreateRequest, db: Session = Depends(get_db)):
    try:
        record = webhook_dispatcher.create_subscription(
            db,
            get_tenant_id(),
            req.url,
            events=req.events or None,
            secret=req.secret,
        )
    except WebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _webhook_info(record)


@webhooks_router.delete(
    "/{sub_id}",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def delete_webhook(sub_id: int, db: Session = Depends(get_db)):
    if not webhook_dispatcher.delete_subscription(db, get_tenant_id(), sub_id):
        raise HTTPException(status_code=404, detail="订阅不存在")
    return {"ok": True}


@webhooks_router.get(
    "/deliveries/recent",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def recent_deliveries():
    """最近的投递记录（内存，最多 50 条）"""
    return {"deliveries": webhook_dispatcher.recent_deliveries()}


# ============ 开放接口（X-API-Key） ============

@open_router.get("/sop")
async def open_list_sop(
    db: Session = Depends(get_db),
    _key=Depends(api_gateway.require_api_key("read")),
):
    """SOP 列表"""
    items = []
    for sop in SOPRepository(db).get_all():
        try:
            steps = json.loads(sop.steps_json)
        except json.JSONDecodeError:
            steps = []
        items.append(
            {
                "id": sop.id,
                "name": sop.name,
                "version": sop.version,
                "step_count": len(steps),
                "updated_at": sop.updated_at.isoformat() if sop.updated_at else None,
            }
        )
    return {"sops": items}


@open_router.get("/execution")
async def open_list_execution(
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _key=Depends(api_gateway.require_api_key("read")),
):
    """执行记录（分页）"""
    records, total = RecordRepository(db).get_all(
        status=status, page=page, limit=limit
    )
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "records": [
            {
                "id": record.id,
                "sop_name": record.sop_name,
                "status": record.status,
                "start_time": record.start_time.isoformat() if record.start_time else None,
                "end_time": record.end_time.isoformat() if record.end_time else None,
                "total_duration": record.total_duration,
            }
            for record in records
        ],
    }


def _load_record(db: Session, record_id: int):
    record = RecordRepository(db).get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    steps = db.query(StepRecord).filter(StepRecord.record_id == record.id).all()
    return record, steps


@open_router.get("/execution/{record_id}")
async def open_execution_detail(
    record_id: int,
    db: Session = Depends(get_db),
    _key=Depends(api_gateway.require_api_key("read")),
):
    record, steps = _load_record(db, record_id)
    payload = execution_to_mes(record, steps)
    return payload


@open_router.get("/analytics/overview")
async def open_analytics(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    _key=Depends(api_gateway.require_api_key("read")),
):
    """OEE / FPY / CT / DPMO / MTBF"""
    return compute_overview(db, days=days)


@open_router.get("/mes/execution/{record_id}")
async def open_mes_execution(
    record_id: int,
    db: Session = Depends(get_db),
    _key=Depends(api_gateway.require_api_key("read")),
):
    """MES 报文预览（与 /execution/{id} 同构，显式标注适配层）"""
    record, steps = _load_record(db, record_id)
    return execution_to_mes(record, steps)
