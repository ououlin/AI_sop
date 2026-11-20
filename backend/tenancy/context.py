"""请求级租户上下文。

多租户隔离依赖三个约定：

1. HTTP 请求由 ``TenantMiddleware`` 从 JWT 载荷解析出租户并写入上下文；
2. 数据访问层（Repository）读取上下文，自动附加 ``tenant_id`` 过滤；
3. 后台线程（识别流水线）不属于任何请求，默认落在 ``default`` 租户，
   需要时用 :func:`tenant_context` 显式切换。

使用 ``contextvars`` 而非全局变量，保证并发请求之间互不干扰。
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional, Tuple

DEFAULT_TENANT_ID: int = 1
DEFAULT_TENANT_CODE: str = os.getenv("DEFAULT_TENANT_CODE", "default")

_tenant_id: ContextVar[int] = ContextVar("tenant_id", default=DEFAULT_TENANT_ID)
_tenant_code: ContextVar[str] = ContextVar("tenant_code", default=DEFAULT_TENANT_CODE)


def get_tenant_id() -> int:
    """当前上下文的租户 ID。"""
    return _tenant_id.get()


def get_tenant_code() -> str:
    """当前上下文的租户编码。"""
    return _tenant_code.get()


@contextmanager
def tenant_context(
    tenant_id: int = DEFAULT_TENANT_ID,
    code: str = DEFAULT_TENANT_CODE,
) -> Iterator[None]:
    """在上下文内切换租户，退出时恢复原值。"""
    id_token = _tenant_id.set(int(tenant_id))
    code_token = _tenant_code.set(str(code))
    try:
        yield
    finally:
        _tenant_id.reset(id_token)
        _tenant_code.reset(code_token)


def resolve_tenant_from_payload(payload: Optional[dict]) -> Tuple[int, str]:
    """从 JWT 载荷解析租户，缺失或非法时回落到默认租户。

    老版本 Token 没有 ``tid`` 字段，升级期间按默认租户处理，避免强制重新登录。
    """
    if not payload:
        return DEFAULT_TENANT_ID, DEFAULT_TENANT_CODE

    try:
        tenant_id = int(payload.get("tid", DEFAULT_TENANT_ID))
    except (TypeError, ValueError):
        tenant_id = DEFAULT_TENANT_ID

    code = payload.get("tenant") or DEFAULT_TENANT_CODE
    return tenant_id, str(code)
