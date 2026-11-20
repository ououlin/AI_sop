"""
认证 API 路由
- 用户登录/登出
- 获取当前用户信息
- 用户管理（管理员）
"""

import logging
import os
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, status, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from db_models import UserDB
from auth.jwt_handler import (
    ACCESS_TOKEN_COOKIE, JWT_EXPIRE_HOURS, hash_password, verify_password,
    create_access_token, decode_access_token,
)
from auth.role_checker import Role, has_permission, get_role_permissions
from auth.dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ============ 请求/响应模型 ============

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str
    permissions: List[str] = Field(default_factory=list)


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    display_name: str
    is_active: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = Role.OPERATOR.value
    display_name: str = ""


# ============ 默认用户初始化 ============

def init_default_users():
    """初始化默认用户（仅当用户表为空时）"""
    db = SessionLocal()
    try:
        if db.query(UserDB).count() > 0:
            return
        defaults = [
            ("admin", "admin123", Role.ADMIN, "管理员"),
            ("supervisor", "super123", Role.SUPERVISOR, "线长"),
            ("operator", "op123", Role.OPERATOR, "操作员"),
        ]
        for username, pwd, role, name in defaults:
            user = UserDB(
                username=username,
                password_hash=hash_password(pwd),
                role=role.value,
                display_name=name,
            )
            db.add(user)
        db.commit()
        logger.info("默认用户已初始化: admin/supervisor/operator")
    finally:
        db.close()


# ============ 路由 ============

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """用户登录"""
    user = db.query(UserDB).filter(UserDB.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已禁用",
        )

    # 更新最后登录时间
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # 生成Token
    token = create_access_token({
        "sub": user.username,
        "role": user.role,
        "uid": user.id,
    })
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=JWT_EXPIRE_HOURS * 3600,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/",
    )

    return LoginResponse(
        access_token=token,
        role=user.role,
        display_name=user.display_name,
        permissions=list(get_role_permissions(user.role)),
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserInfo)
async def get_me(request: Request, db: Session = Depends(get_db)):
    """获取当前用户信息（从Authorization头解析Token）"""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供Token")
    token = auth_header[7:]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token无效或已过期")

    user = db.query(UserDB).filter(UserDB.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserInfo(
        id=user.id,
        username=user.username,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login=user.last_login.isoformat() if user.last_login else None,
    )


@router.get(
    "/users",
    response_model=List[UserInfo],
    dependencies=[Depends(require_permission("user:manage"))],
)
async def list_users(db: Session = Depends(get_db)):
    """获取所有用户列表"""
    users = db.query(UserDB).all()
    return [
        UserInfo(
            id=u.id,
            username=u.username,
            role=u.role,
            display_name=u.display_name,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else None,
            last_login=u.last_login.isoformat() if u.last_login else None,
        )
        for u in users
    ]


@router.post(
    "/users",
    response_model=UserInfo,
    dependencies=[Depends(require_permission("user:manage"))],
)
async def create_user(req: CreateUserRequest, db: Session = Depends(get_db)):
    """创建新用户"""
    if req.role not in [r.value for r in Role]:
        raise HTTPException(status_code=400, detail="无效的角色")

    existing = db.query(UserDB).filter(UserDB.username == req.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = UserDB(
        username=req.username,
        password_hash=hash_password(req.password),
        role=req.role,
        display_name=req.display_name or req.username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserInfo(
        id=user.id,
        username=user.username,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
    )


@router.delete(
    "/users/{user_id}",
    dependencies=[Depends(require_permission("user:manage"))],
)
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    """删除用户"""
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账户")
    db.delete(user)
    db.commit()
    return {"ok": True}
