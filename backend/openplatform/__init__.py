"""开放平台：API Key、Webhook 与 MES 适配。"""

from openplatform.api_gateway import (
    VALID_SCOPES,
    authenticate,
    create_key,
    list_keys,
    require_api_key,
    revoke_key,
)
from openplatform.webhook_manager import (
    SUPPORTED_EVENTS,
    WebhookError,
    WebhookManager,
    manager as webhook_dispatcher,
)

__all__ = [
    "SUPPORTED_EVENTS",
    "VALID_SCOPES",
    "WebhookError",
    "WebhookManager",
    "authenticate",
    "create_key",
    "list_keys",
    "require_api_key",
    "revoke_key",
    "webhook_dispatcher",
]
