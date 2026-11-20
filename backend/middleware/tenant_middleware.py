"""租户中间件：把请求所属租户写入上下文。

必须放在 ``AuthMiddleware`` 内层（先注册、后注册认证中间件），
这样 ``request.state.user`` 已经由认证中间件写好。

平台管理员（``platform_admin``）可通过 ``X-Tenant-Id`` 请求头进入指定租户，
便于多租户运维；普通用户忽略该请求头，防止越权。
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware

from tenancy.context import resolve_tenant_from_payload, tenant_context

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        payload = getattr(request.state, "user", None)
        tenant_id, tenant_code = resolve_tenant_from_payload(payload)

        override = request.headers.get("x-tenant-id")
        if override and payload and payload.get("role") == "platform_admin":
            try:
                tenant_id = int(override)
                tenant_code = ""
            except (TypeError, ValueError):
                logger.warning("忽略非法的 X-Tenant-Id 请求头: %s", override)

        request.state.tenant_id = tenant_id
        request.state.tenant_code = tenant_code

        with tenant_context(tenant_id, tenant_code):
            return await call_next(request)
