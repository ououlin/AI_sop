"""
工位状态上报器
将本地工位状态定时上报到中央聚合服务
"""

import os
import asyncio
import logging
import time
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
        self._last_latency_ms = 0.0

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
        payload["app_version"] = os.getenv("APP_VERSION", "1.0.0")
        payload["model_version"] = os.getenv("MODEL_VERSION", "yolov8n@8.2.0")
        payload["camera_ok"] = camera.get_fps() > 0
        payload["latency_ms"] = self._last_latency_ms
        return payload

    async def _send(self, payload: dict):
        """发送到中央服务，并处理下发的运维命令"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                headers = {}
                station_key = os.getenv("STATION_API_KEY", "")
                if station_key:
                    headers["X-Station-Key"] = station_key
                started = time.perf_counter()
                resp = await client.post(
                    f"{self.central_url}/api/v1/station/report",
                    json=payload,
                    headers=headers,
                )
                self._last_latency_ms = (time.perf_counter() - started) * 1000
                if resp.status_code != 200:
                    logger.debug("工位上报响应异常: HTTP %d", resp.status_code)
                    return
                commands = (resp.json() or {}).get("commands") or []
                for command in commands:
                    await self._handle_command(client, command, headers)
        except ImportError:
            pass  # httpx 未安装
        except Exception as e:
            logger.debug("工位上报发送失败: %s", e)

    async def _handle_command(self, client, command: dict, headers: dict):
        """应用运维命令并回执"""
        payload = command.get("payload") or {}
        status, message = "acked", ""

        if command.get("type") == "config":
            config = payload.get("config") or {}
            interval = config.get("report_interval")
            if isinstance(interval, (int, float)) and 1 <= interval <= 60:
                self.report_interval = float(interval)
                message = "上报间隔已调整为 {:.1f}s".format(self.report_interval)
            else:
                message = "配置已接收（无本地可应用项）"
            logger.info("设备 [%s] 收到配置: %s", self.station_id, config)
        elif command.get("type") == "upgrade":
            message = "目标版本已登记，重启工位进程后生效"
            logger.warning(
                "设备 [%s] 收到升级指令: %s@%s（重启后生效）",
                self.station_id, payload.get("model_id"), payload.get("version"),
            )
        else:
            status, message = "failed", "未知命令类型"

        await self._ack(client, command.get("command_id"), status, message, headers)

    async def _ack(self, client, command_id, status: str, message: str, headers: dict):
        if not command_id:
            return
        try:
            await client.post(
                "{}/api/v1/station/ack".format(self.central_url),
                json={
                    "station_id": self.station_id,
                    "command_id": command_id,
                    "status": status,
                    "message": message,
                },
                headers=headers,
            )
        except Exception as exc:
            logger.debug("工位命令回执失败: %s", exc)
