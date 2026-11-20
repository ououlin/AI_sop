"""租户中间件：解析请求租户、写入上下文，并执行订阅到期拦截。

必须放在 ``AuthMiddleware`` 内层（先注册本中间件，再注册认证中间件），
这样 ``request.state.user`` 已经由认证中间件写好。

平台管理员（``platform_admin``）可通过 ``X-Tenant-Id`` 请求头进入指定租户，
便于多租户运维；普通用户忽略该请求头，防止越权。

订阅到期后租户进入只读状态：GET/HEAD/OPTIONS 放行，其余方法返回 402；
唯一的例外是套餐变更（PUT .../subscription），否则到期后无法自助续费恢复。
"""

import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from tenancy.context import resolve_tenant_from_payload, tenant_context

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_subscription_renewal(request) -> bool:
    """到期只读的例外：允许变更套餐，否则租户无法恢复。"""
    return request.method == "PUT" and request.url.path.endswith("/subscription")


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

        if (
            payload
            and request.method not in SAFE_METHODS
            and not _is_subscription_renewal(request)
            and self._subscription_expired(request, tenant_id)
        ):
            return JSONResponse(
                {"error": "订阅已到期，租户当前为只读状态", "code": 402},
                status_code=402,
            )

        with tenant_context(tenant_id, tenant_code):
            return await call_next(request)

    @staticmethod
    def _subscription_expired(request, tenant_id: int) -> bool:
        """查询订阅到期状态；数据库异常时按未到期处理，避免整站不可用。"""
        if not request.url.path.startswith("/api/v1/"):
            return False

        from database import SessionLocal
        from saas.subscription import is_tenant_expired

        factory = getattr(request.app.state, "session_factory", None) or SessionLocal
        db = None
        try:
            db = factory()
            return is_tenant_expired(db, tenant_id)
        except Exception:  # noqa: BLE001 - 可用性优先
            logger.warning("订阅状态检查失败，按未到期处理", exc_info=True)
            return False
        finally:
            if db is not None:
                db.close()
