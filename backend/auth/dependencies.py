"""FastAPI dependencies for authenticated user and permission checks."""

from typing import Callable

from fastapi import HTTPException, Request, status

from auth.role_checker import has_permission


def get_current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
        )
    return user


def require_permission(permission: str) -> Callable[[Request], dict]:
    def dependency(request: Request) -> dict:
        user = get_current_user(request)
        if not has_permission(user.get("role", ""), permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission}",
            )
        return user

    return dependency


def require_any_permission(*permissions: str) -> Callable[[Request], dict]:
    def dependency(request: Request) -> dict:
        user = get_current_user(request)
        role = user.get("role", "")
        if not any(has_permission(role, permission) for permission in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {' 或 '.join(permissions)}",
            )
        return user

    return dependency
