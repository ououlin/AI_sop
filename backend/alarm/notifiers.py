"""
告警通知器
支持多种通知渠道：日志、Webhook（企业微信/钉钉）、声音
"""

import os
import logging
import asyncio
from typing import List, Optional
from datetime import datetime

from models import Alarm, AlarmLevel

logger = logging.getLogger(__name__)


class BaseNotifier:
    """通知器基类"""

    async def notify(self, alarm: Alarm):
        raise NotImplementedError


class LogNotifier(BaseNotifier):
    """日志通知器（始终启用）"""

    async def notify(self, alarm: Alarm):
        level_map = {
            AlarmLevel.INFO: logging.INFO,
            AlarmLevel.WARNING: logging.WARNING,
            AlarmLevel.CRITICAL: logging.ERROR,
        }
        logger.log(
            level_map.get(alarm.level, logging.WARNING),
            "[ALARM][%s] %s (step=%s): %s",
            alarm.level.value.upper(),
            alarm.type.value,
            alarm.step_id,
            alarm.message,
        )


class WebhookNotifier(BaseNotifier):
    """Webhook 通知器（企业微信/钉钉等）"""

    def __init__(self, webhook_url: str, min_level: AlarmLevel = AlarmLevel.WARNING):
        self.webhook_url = webhook_url
        self.min_level = min_level
        self._level_order = {
            AlarmLevel.INFO: 0,
            AlarmLevel.WARNING: 1,
            AlarmLevel.CRITICAL: 2,
        }

    def _should_notify(self, alarm: Alarm) -> bool:
        return self._level_order.get(alarm.level, 0) >= self._level_order.get(self.min_level, 0)

    async def notify(self, alarm: Alarm):
        if not self._should_notify(alarm):
            return
        try:
            import httpx
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": (
                        f"### SOP工序告警\n"
                        f"> **级别**: {alarm.level.value}\n"
                        f"> **类型**: {alarm.type.value}\n"
                        f"> **步骤**: {alarm.step_name or alarm.step_id or '-'}\n"
                        f"> **内容**: {alarm.message}\n"
                        f"> **时间**: {alarm.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    )
                }
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self.webhook_url, json=payload)
                if resp.status_code != 200:
                    logger.warning("Webhook 告警推送失败: HTTP %d", resp.status_code)
        except ImportError:
            logger.debug("httpx 未安装，跳过 Webhook 告警")
        except Exception as e:
            logger.warning("Webhook 告警推送异常: %s", e)


class SoundNotifier(BaseNotifier):
    """声音告警器（Windows 系统蜂鸣）"""

    def __init__(self, enabled: bool = True, min_level: AlarmLevel = AlarmLevel.WARNING):
        self.enabled = enabled
        self.min_level = min_level
        self._level_order = {
            AlarmLevel.INFO: 0,
            AlarmLevel.WARNING: 1,
            AlarmLevel.CRITICAL: 2,
        }

    def _should_notify(self, alarm: Alarm) -> bool:
        return self.enabled and self._level_order.get(alarm.level, 0) >= self._level_order.get(self.min_level, 0)

    async def notify(self, alarm: Alarm):
        if not self._should_notify(alarm):
            return
        try:
            import winsound
            freq = 1000 if alarm.level == AlarmLevel.WARNING else 2000
            duration = 500 if alarm.level == AlarmLevel.WARNING else 1000
            await asyncio.to_thread(winsound.Beep, freq, duration)
        except Exception:
            pass  # 非 Windows 或无音频设备
