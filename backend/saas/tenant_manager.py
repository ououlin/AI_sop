"""租户管理与开通。

租户是数据隔离单元：每个租户拥有独立的用户、SOP 与执行记录。
开通租户时同步创建该租户的管理员账号，保证租户创建后即可登录。
"""

import re
from typing import List, Optional

from sqlalchemy.orm import Session

from auth.jwt_handler import hash_password
from auth.role_checker import Role
from db_models import TenantDB, UserDB
from tenancy.context import DEFAULT_TENANT_ID

TENANT_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
VALID_STATUSES = ("active", "suspended")
DEFAULT_PLAN_CODE = "free"


class TenantError(ValueError):
    """租户操作失败（参数非法、状态非法等）。"""


class TenantConflict(TenantError):
    """租户标识冲突（编码已存在）。"""


def normalize_code(code: str) -> str:
    return (code or "").strip().lower()


def list_tenants(db: Session) -> List[TenantDB]:
    return db.query(TenantDB).order_by(TenantDB.id.asc()).all()


def get_tenant(
    db: Session,
    tenant_id: Optional[int] = None,
    code: Optional[str] = None,
) -> Optional[TenantDB]:
    if tenant_id is not None:
        return db.query(TenantDB).filter(TenantDB.id == tenant_id).first()
    if code:
        return db.query(TenantDB).filter(TenantDB.code == normalize_code(code)).first()
    return None


def count_users(db: Session, tenant_id: int) -> int:
    return db.query(UserDB).filter(UserDB.tenant_id == tenant_id).count()


def create_tenant(
    db: Session,
    code: str,
    name: str,
    admin_username: str,
    admin_password: str,
    plan_code: str = DEFAULT_PLAN_CODE,
) -> TenantDB:
    """开通租户并创建其管理员账号。"""
    code = normalize_code(code)
    if not TENANT_CODE_PATTERN.match(code):
        raise TenantError("租户编码需以小写字母开头，仅含小写字母、数字或连字符，长度 2-32")

    if get_tenant(db, code=code):
        raise TenantConflict("租户编码已存在: {}".format(code))

    name = (name or "").strip()
    if not name:
        raise TenantError("租户名称不能为空")

    admin_username = (admin_username or "").strip()
    if len(admin_username) < 2:
        raise TenantError("管理员账号至少 2 个字符")

    if not admin_password or len(admin_password) < 6:
        raise TenantError("管理员密码至少 6 位")

    tenant = TenantDB(
        code=code,
        name=name,
        status="active",
        plan_code=plan_code or DEFAULT_PLAN_CODE,
    )
    db.add(tenant)
    db.flush()  # 先拿到 tenant.id 再建管理员

    db.add(
        UserDB(
            tenant_id=tenant.id,
            username=admin_username,
            password_hash=hash_password(admin_password),
            role=Role.ADMIN.value,
            display_name="租户管理员",
        )
    )
    db.commit()
    db.refresh(tenant)
    return tenant


def update_tenant(
    db: Session,
    tenant_id: int,
    name: Optional[str] = None,
    status: Optional[str] = None,
    plan_code: Optional[str] = None,
) -> TenantDB:
    tenant = get_tenant(db, tenant_id=tenant_id)
    if not tenant:
        raise TenantError("租户不存在")

    if status is not None:
        if status not in VALID_STATUSES:
            raise TenantError("租户状态只能是 active 或 suspended")
        if tenant.id == DEFAULT_TENANT_ID and status != "active":
            raise TenantError("默认租户不允许停用")

    if name is not None:
        name = name.strip()
        if not name:
            raise TenantError("租户名称不能为空")
        tenant.name = name
    if status is not None:
        tenant.status = status
    if plan_code is not None:
        tenant.plan_code = plan_code

    db.commit()
    db.refresh(tenant)
    return tenant


def serialize(tenant: TenantDB, user_count: Optional[int] = None) -> dict:
    data = {
        "id": tenant.id,
        "code": tenant.code,
        "name": tenant.name,
        "status": tenant.status,
        "plan_code": tenant.plan_code,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }
    if user_count is not None:
        data["user_count"] = user_count
    return data
