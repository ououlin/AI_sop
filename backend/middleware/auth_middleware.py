"""
认证中间件
拦截所有 /api/v1/ 开头的HTTP请求，校验JWT Token
排除 PUBLIC_PATHS 中的公开端点
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth.jwt_handler import ACCESS_TOKEN_COOKIE, decode_access_token
from auth.role_checker import PUBLIC_PATHS

logger = logging.getLogger(__name__)

# 无需认证的路径前缀
PUBLIC_PREFIXES = (
    "/ws/",
    "/assets/",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/open/",  # 开放平台：由 API Key 依赖校验
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 跳过非API路径和公开端点
        if not path.startswith("/api/v1/"):
            return await call_next(request)
        if path in PUBLIC_PATHS:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return await call_next(request)

        # API 客户端优先使用 Bearer；浏览器媒体请求使用 HttpOnly Cookie。
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else None
        token = token or request.cookies.get(ACCESS_TOKEN_COOKIE)
        if not token:
            return JSONResponse(
                {"error": "未提供认证Token", "code": 401},
                status_code=401,
            )
        payload = decode_access_token(token)
        if not payload:
            return JSONResponse(
                {"error": "Token无效或已过期", "code": 401},
                status_code=401,
            )

        # 注入用户信息到request.state，供路由使用
        request.state.user = payload

        return await call_next(request)
