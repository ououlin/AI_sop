"""Webhook 订阅与事件投递。

v1 支持的事件：``execution.started`` / ``execution.completed`` /
``execution.failed`` / ``alarm.triggered``。
投递为尽力而为（3 秒超时、线程内异步），失败只记录在内存投递日志里，
不阻塞识别主链路。
"""

import json
import logging
import threading
from collections import deque
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from database import SessionLocal
from db_models import WebhookDB

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = (
    "execution.started",
    "execution.completed",
    "execution.failed",
    "alarm.triggered",
)


class WebhookError(ValueError):
    """Webhook 参数非法。"""


class WebhookManager:
    def __init__(self, timeout: float = 3.0, keep: int = 50):
        self.timeout = timeout
        self._deliveries = deque(maxlen=keep)
        self._lock = threading.Lock()

    # ---------- 订阅管理 ----------
    def list_subscriptions(self, db: Session, tenant_id: int) -> List[WebhookDB]:
        return (
            db.query(WebhookDB)
            .filter(WebhookDB.tenant_id == tenant_id)
            .order_by(WebhookDB.id.desc())
            .all()
        )

    def create_subscription(
        self,
        db: Session,
        tenant_id: int,
        url: str,
        events: Optional[List[str]] = None,
        secret: str = "",
    ) -> WebhookDB:
        parsed = urlparse(url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise WebhookError("回调地址必须是 http(s) URL")

        events = list(events) if events else list(SUPPORTED_EVENTS)
        invalid = [item for item in events if item not in SUPPORTED_EVENTS]
        if invalid:
            raise WebhookError("未知事件: {}".format(", ".join(invalid)))

        record = WebhookDB(
            tenant_id=tenant_id,
            url=url,
            events=json.dumps(events),
            secret=secret or "",
            active=True,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def delete_subscription(self, db: Session, tenant_id: int, sub_id: int) -> bool:
        record = (
            db.query(WebhookDB)
            .filter(WebhookDB.tenant_id == tenant_id, WebhookDB.id == sub_id)
            .first()
        )
        if not record:
            return False
        db.delete(record)
        db.commit()
        return True

    # ---------- 事件投递 ----------
    def dispatch(self, tenant_id: int, event: str, payload: dict) -> None:
        """异步投递事件，不阻塞调用方。"""
        if event not in SUPPORTED_EVENTS:
            logger.debug("忽略未登记事件: %s", event)
            return
        thread = threading.Thread(
            target=self._deliver,
            args=(tenant_id, event, payload),
            daemon=True,
        )
        thread.start()

    def _deliver(self, tenant_id: int, event: str, payload: dict) -> None:
        subscriptions = []
        db = SessionLocal()
        try:
            subscriptions = [
                item
                for item in db.query(WebhookDB)
                .filter(WebhookDB.tenant_id == tenant_id, WebhookDB.active.is_(True))
                .all()
                if event in self._events_of(item)
            ]
        except Exception:  # noqa: BLE001 - 投递线程不能因查询失败而崩溃
            logger.warning("Webhook 订阅查询失败，跳过本次投递", exc_info=True)
        finally:
            db.close()

        for subscription in subscriptions:
            self._post(subscription.url, subscription.secret, event, payload)

    @staticmethod
    def _events_of(subscription: WebhookDB) -> List[str]:
        try:
            return json.loads(subscription.events or "[]")
        except json.JSONDecodeError:
            return []

    def _post(self, url: str, secret: str, event: str, payload: dict) -> None:
        import time

        started = time.perf_counter()
        status = "failed"
        detail = ""
        try:
            import httpx

            headers = {"X-AI-SOP-Event": event}
            if secret:
                headers["X-AI-SOP-Secret"] = secret
            response = httpx.post(
                url,
                json={"event": event, "data": payload},
                headers=headers,
                timeout=self.timeout,
            )
            status = "ok" if 200 <= response.status_code < 300 else "failed"
            detail = "HTTP {}".format(response.status_code)
        except ImportError:
            detail = "httpx 未安装"
        except Exception as exc:  # noqa: BLE001 - 投递失败不影响主流程
            detail = str(exc)

        with self._lock:
            self._deliveries.appendleft(
                {
                    "event": event,
                    "url": url,
                    "status": status,
                    "detail": detail,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                    "at": datetime.now().isoformat(timespec="seconds"),
                }
            )

    def recent_deliveries(self) -> List[dict]:
        with self._lock:
            return list(self._deliveries)


manager = WebhookManager()
