"""
工位状态上报器
将本地工位状态定时上报到中央聚合服务
"""

import os
import asyncio
import logging
from typing import Optional
from datetime import datetime

from models import StepStatus

logger = logging.getLogger(__name__)


class StationReporter:
    """
    工位状态上报器
    - 定时将本地识别状态上报到中央服务
    - 中央服务不可用时本地继续运行
    """

    def __init__(
        self,
        station_id: str,
        central_url: str = "",
        station_name: str = "",
        report_interval: float = 1.0,
    ):
        self.station_id = station_id
        self.station_name = station_name or station_id
        self.central_url = central_url.rstrip("/")
        self.report_interval = report_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self, sop_manager, alarm_manager, camera):
        """启动上报循环"""
        if self._running or not self.central_url:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(sop_manager, alarm_manager, camera))
        logger.info("工位 [%s] 状态上报已启动，目标: %s", self.station_id, self.central_url)

    async def stop(self):
        """停止上报"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("工位 [%s] 状态上报已停止", self.station_id)

    async def _loop(self, sop_manager, alarm_manager, camera):
        """上报循环"""
        while self._running:
            try:
                payload = self._build_payload(sop_manager, alarm_manager, camera)
                await self._send(payload)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("工位上报异常: %s", e)
            await asyncio.sleep(self.report_interval)

    def _build_payload(self, sop_manager, alarm_manager, camera) -> dict:
        """构建上报数据"""
        payload = {
            "station_id": self.station_id,
            "station_name": self.station_name,
            "status": "idle",
            "sop_name": "",
            "current_step_index": 0,
            "total_steps": 0,
            "current_step_name": "",
            "step_status": "pending",
            "matched_duration": 0.0,
            "hold_duration_sec": 1.0,
            "alarms": [],
            "fps": camera.get_fps(),
            "timestamp": datetime.now().isoformat(),
        }

        if sop_manager.is_loaded():
            rec = sop_manager.recognizer
            step = rec.current_step()
            payload["sop_name"] = sop_manager.definition.sop_name
            payload["total_steps"] = len(sop_manager.definition.steps)
            payload["current_step_index"] = rec.current_index

            if step:
                payload["current_step_name"] = step.name
                state = rec.states[rec.current_index]
                payload["step_status"] = state.status.value
                payload["matched_duration"] = state.matched_duration
                payload["hold_duration_sec"] = step.hold_duration_sec

            if rec.all_done:
                payload["status"] = "idle"
            elif sop_manager.paused:
                payload["status"] = "paused"
            else:
                payload["status"] = "running"

        payload["alarms"] = [a.model_dump() for a in alarm_manager.active_alarms]
        return payload

    async def _send(self, payload: dict):
        """发送到中央服务"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                headers = {}
                station_key = os.getenv("STATION_API_KEY", "")
                if station_key:
                    headers["X-Station-Key"] = station_key
                resp = await client.post(
                    f"{self.central_url}/api/v1/station/report",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code != 200:
                    logger.debug("工位上报响应异常: HTTP %d", resp.status_code)
        except ImportError:
            pass  # httpx 未安装
        except Exception as e:
            logger.debug("工位上报发送失败: %s", e)
