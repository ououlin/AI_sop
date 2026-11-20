"""开放平台 API Key。

- 明文只在创建时返回一次，库里只存 SHA-256 摘要与前缀
- 调用方用 ``X-API-Key`` 访问 ``/api/v1/open/*``
- 作用域：``read`` / ``write``（当前开放接口均为只读，write 预留）
"""

import hashlib
import json
import secrets
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from db_models import ApiKeyDB, TenantDB
from openplatform.rate_limiter import limiter
from tenancy.context import tenant_context

KEY_PREFIX_LEN = 8
VALID_SCOPES = ("read", "write")
DEFAULT_SCOPES = ("read",)


class ApiKeyError(ValueError):
    """API Key 参数非法。"""


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_key(
    db: Session,
    tenant_id: int,
    name: str,
    scopes: Optional[List[str]] = None,
) -> Tuple[ApiKeyDB, str]:
    name = (name or "").strip()
    if not name:
        raise ApiKeyError("名称不能为空")

    scopes = list(scopes) if scopes else list(DEFAULT_SCOPES)
    invalid = [item for item in scopes if item not in VALID_SCOPES]
    if invalid:
        raise ApiKeyError("未知作用域: {}".format(", ".join(invalid)))

    raw = "sk_" + secrets.token_hex(24)
    record = ApiKeyDB(
        tenant_id=tenant_id,
        name=name,
        key_prefix=raw[:KEY_PREFIX_LEN],
        key_hash=_digest(raw),
        scopes=json.dumps(scopes),
        active=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, raw


def list_keys(db: Session, tenant_id: int) -> List[ApiKeyDB]:
    return (
        db.query(ApiKeyDB)
        .filter(ApiKeyDB.tenant_id == tenant_id)
        .order_by(ApiKeyDB.id.desc())
        .all()
    )


def revoke_key(db: Session, tenant_id: int, key_id: int) -> bool:
    record = (
        db.query(ApiKeyDB)
        .filter(ApiKeyDB.tenant_id == tenant_id, ApiKeyDB.id == key_id)
        .first()
    )
    if not record:
        return False
    record.active = False
    db.commit()
    return True


def authenticate(db: Session, raw: str) -> Optional[ApiKeyDB]:
    if not raw or len(raw) < KEY_PREFIX_LEN:
        return None
    candidates = (
        db.query(ApiKeyDB)
        .filter(ApiKeyDB.key_prefix == raw[:KEY_PREFIX_LEN], ApiKeyDB.active.is_(True))
        .all()
    )
    digest = _digest(raw)
    for record in candidates:
        if secrets.compare_digest(record.key_hash, digest):
            record.last_used_at = datetime.now()
            db.commit()
            return record
    return None


def scopes_of(record: ApiKeyDB) -> List[str]:
    try:
        return json.loads(record.scopes or "[]")
    except json.JSONDecodeError:
        return []


def require_api_key(scope: str = "read"):
    """FastAPI 依赖：校验 X-API-Key，并在请求期间切换到该 Key 所属租户。"""

    async def dependency(request: Request, db: Session = Depends(get_db)):
        raw = (request.headers.get("x-api-key") or "").strip()
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少 X-API-Key",
            )
        record = authenticate(db, raw)
        if not record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key 无效或已吊销",
            )
        if scope not in scopes_of(record):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API Key 缺少作用域: {}".format(scope),
            )

        allowed, remaining, retry_after = limiter.hit(str(record.id))
        request.state.rate_limit_remaining = remaining
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="请求过于频繁，请稍后重试",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

        tenant = db.query(TenantDB).filter(TenantDB.id == record.tenant_id).first()
        request.state.api_key = record
        with tenant_context(record.tenant_id, tenant.code if tenant else ""):
            yield record

    return dependency
