"""
告警管理器
- 集中管理告警生命周期
- 定期检查超时、顺序错误等异常
- 通过多渠道通知器分发告警
"""

import os
import uuid
import logging
import asyncio
import threading
from typing import List, Optional, Callable
from datetime import datetime, timedelta
from collections import deque

from models import (
    Alarm, AlarmLevel, AlarmType, StepRuntimeState, StepStatus,
    ObjectDetection, RequiredObject, HandResult,
)
from config import WORK_ZONES
from alarm.notifiers import BaseNotifier, LogNotifier, WebhookNotifier, SoundNotifier

logger = logging.getLogger(__name__)


class AlarmManager:
    """
    告警管理器
    - 维护活跃告警列表和历史记录
    - 定期检查异常条件
    - 通过通知器分发告警
    """

    def __init__(self, max_history: int = 1000):
        self._notifiers: List[BaseNotifier] = [LogNotifier()]
        self._active_alarms: List[Alarm] = []
        self._history: deque = deque(maxlen=max_history)
        self._timeout_flags: set = set()  # 已触发超时的步骤ID，避免重复告警
        self._lock = threading.Lock()  # 保护 _active_alarms 和 _history 的并发访问
        # 主事件循环引用，供 trigger 跨线程派发异步通知（在 lifespan 中 bind_loop 绑定）
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # 配置通知器
        webhook_url = os.getenv("ALARM_WEBHOOK_URL", "")
        if webhook_url:
            min_level = AlarmLevel(os.getenv("ALARM_LEVEL_FILTER", "warning").split(",")[0])
            self._notifiers.append(WebhookNotifier(webhook_url, min_level))
            logger.info("告警 Webhook 已配置")

        sound_enabled = os.getenv("ALARM_SOUND_ENABLED", "true").lower() == "true"
        if sound_enabled:
            self._notifiers.append(SoundNotifier(enabled=True))

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """绑定主事件循环，使 trigger 可在任意线程安全派发通知任务"""
        self._loop = loop

    @property
    def active_alarms(self) -> List[Alarm]:
        with self._lock:
            return list(self._active_alarms)

    @property
    def history(self) -> List[Alarm]:
        with self._lock:
            return list(self._history)

    def trigger(
        self,
        level: AlarmLevel,
        type_: AlarmType,
        message: str,
        step_id: Optional[int] = None,
        step_name: Optional[str] = None,
    ) -> Alarm:
        """触发告警"""
        alarm = Alarm(
            id=str(uuid.uuid4())[:8],
            level=level,
            type=type_,
            step_id=step_id,
            step_name=step_name,
            message=message,
            timestamp=datetime.now(),
        )
        with self._lock:
            self._active_alarms.append(alarm)
            self._history.append(alarm)

        # 异步分发通知（跨线程安全派发到主事件循环）
        self._dispatch_notifications(alarm)

        return alarm

    def _dispatch_notifications(self, alarm: Alarm) -> None:
        """安全派发告警通知任务，支持在非主循环线程调用"""
        for notifier in self._notifiers:
            try:
                loop = self._loop
                if loop is not None and loop.is_running():
                    # 跨线程安全派发：在主循环线程中创建通知任务
                    loop.call_soon_threadsafe(
                        lambda n=notifier, a=alarm: asyncio.ensure_future(n.notify(a), loop=loop)
                    )
                else:
                    # 未绑定循环或循环未运行，尝试当前线程直接创建任务
                    asyncio.ensure_future(notifier.notify(alarm))
            except RuntimeError as e:
                logger.warning("告警通知派发失败(无事件循环): %s", e)
            except Exception as e:
                logger.warning("告警通知异常: %s", e)

    def acknowledge(self, alarm_id: str) -> bool:
        """确认告警"""
        with self._lock:
            for alarm in self._active_alarms:
                if alarm.id == alarm_id:
                    alarm.acknowledged = True
                    self._active_alarms.remove(alarm)
                    return True
        return False

    def clear_active(self):
        """清除所有活跃告警"""
        with self._lock:
            self._active_alarms.clear()
            self._timeout_flags.clear()

    def check_timeout(self, states: List[StepRuntimeState], current_index: int):
        """检查当前步骤是否超时"""
        if current_index >= len(states):
            return
        state = states[current_index]
        if state.status not in (StepStatus.IN_PROGRESS, StepStatus.PENDING):
            return
        if state.started_at is None:
            return

        elapsed = (datetime.now() - state.started_at).total_seconds()
        if elapsed > state.timeout_sec:
            with self._lock:
                if state.step_id in self._timeout_flags:
                    return
                self._timeout_flags.add(state.step_id)
                state.status = StepStatus.TIMEOUT
            self.trigger(
                level=AlarmLevel.WARNING,
                type_=AlarmType.TIMEOUT,
                message=f"步骤 [{state.name}] 超时，已用时 {elapsed:.0f}秒 (阈值 {state.timeout_sec:.0f}秒)",
                step_id=state.step_id,
                step_name=state.name,
            )

    def check_object_missing(
        self,
        current_step,
        objects: List[ObjectDetection],
    ):
        """检查步骤要求的物体是否缺失"""
        if not current_step.required_objects:
            return
        for req in current_step.required_objects:
            matched = [o for o in objects if o.class_name == req.class_name]
            if req.target_zone:
                matched = [o for o in matched if o.current_zone == req.target_zone]
            if len(matched) < req.min_count:
                flag_key = (current_step.step_id, req.class_name)
                with self._lock:
                    if flag_key in self._timeout_flags:
                        return
                    self._timeout_flags.add(flag_key)
                zone_info = f"在区域[{req.target_zone}]内" if req.target_zone else ""
                self.trigger(
                    level=AlarmLevel.INFO,
                    type_=AlarmType.OBJECT_MISSING,
                    message=f"步骤 [{current_step.name}] 缺少物体: {req.class_name} {zone_info}(需要 {req.min_count}个, 检测到 {len(matched)}个)",
                    step_id=current_step.step_id,
                    step_name=current_step.name,
                )
