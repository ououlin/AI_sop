"""
中央聚合服务
接收多工位Agent上报的状态，聚合后提供给产线看板。

AggregationServer 实例由 app.state 持有（见 dependencies.init_app_state），
路由通过 Depends 获取，避免模块级单例导致的进程内自调用风险。
"""

import logging
import os
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from dependencies import get_aggregation_server
from auth.dependencies import require_permission

logger = logging.getLogger(__name__)


# ============ 数据模型 ============

class StationReport(BaseModel):
    """工位上报数据"""
    station_id: str
    station_name: str = ""
    status: str = "idle"              # idle / running / paused / error / offline
    sop_name: str = ""
    current_step_index: int = 0
    total_steps: int = 0
    current_step_name: str = ""
    step_status: str = "pending"
    matched_duration: float = 0.0
    hold_duration_sec: float = 1.0
    alarms: List[dict] = Field(default_factory=list)
    fps: float = 0.0
    timestamp: str = ""


class StationInfo(StationReport):
    """工位完整信息（含在线状态）"""
    is_online: bool = True
    last_heartbeat: datetime = Field(default_factory=datetime.now)
    registered_at: Optional[datetime] = None


# ============ 聚合服务 ============

class AggregationServer:
    """
    中央聚合服务
    - 管理工位注册与心跳
    - 聚合多工位实时状态
    - 提供产线看板查询接口
    """

    def __init__(self, heartbeat_timeout: float = 10.0):
        self._stations: Dict[str, StationInfo] = {}
        self._heartbeat_timeout = heartbeat_timeout

    def register(self, station_id: str, station_name: str = "") -> StationInfo:
        """注册工位"""
        info = StationInfo(
            station_id=station_id,
            station_name=station_name or station_id,
            registered_at=datetime.now(),
        )
        self._stations[station_id] = info
        logger.info("工位注册: %s (%s)", station_id, station_name)
        return info

    def report(self, report: StationReport) -> StationInfo:
        """接收工位上报"""
        if report.station_id not in self._stations:
            self.register(report.station_id, report.station_name)

        info = self._stations[report.station_id]
        # 更新字段
        info.station_name = report.station_name or info.station_name
        info.status = report.status
        info.sop_name = report.sop_name
        info.current_step_index = report.current_step_index
        info.total_steps = report.total_steps
        info.current_step_name = report.current_step_name
        info.step_status = report.step_status
        info.matched_duration = report.matched_duration
        info.hold_duration_sec = report.hold_duration_sec
        info.alarms = report.alarms
        info.fps = report.fps
        info.is_online = True
        info.last_heartbeat = datetime.now()
        return info

    def get_all_stations(self) -> List[StationInfo]:
        """获取所有工位状态（检查在线状态）"""
        now = datetime.now()
        for sid, info in self._stations.items():
            elapsed = (now - info.last_heartbeat).total_seconds()
            if elapsed > self._heartbeat_timeout and info.is_online:
                info.is_online = False
                info.status = "offline"
                logger.warning("工位 %s 心跳超时(%.1f秒)，标记为离线", sid, elapsed)
        return list(self._stations.values())

    def get_station(self, station_id: str) -> Optional[StationInfo]:
        """获取单个工位状态"""
        return self._stations.get(station_id)

    def get_line_summary(self) -> dict:
        """获取产线整体摘要"""
        stations = self.get_all_stations()
        total = len(stations)
        online = sum(1 for s in stations if s.is_online)
        running = sum(1 for s in stations if s.status == "running")
        error = sum(1 for s in stations if s.status in ("error", "offline"))
        active_alarms = sum(len(s.alarms) for s in stations)
        return {
            "total_stations": total,
            "online_stations": online,
            "running_stations": running,
            "error_stations": error,
            "active_alarms": active_alarms,
            "timestamp": datetime.now().isoformat(),
        }

    def remove_station(self, station_id: str) -> bool:
        """移除工位"""
        if station_id in self._stations:
            del self._stations[station_id]
            logger.info("工位已移除: %s", station_id)
            return True
        return False


# ============ API 路由 ============

router = APIRouter(tags=["line-dashboard"])


@router.post("/station/report")
async def report_station(
    report: StationReport,
    x_station_key: Optional[str] = Header(default=None),
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
):
    """工位上报状态"""
    expected_key = os.getenv("STATION_API_KEY", "")
    if expected_key and x_station_key != expected_key:
        raise HTTPException(status_code=401, detail="工位密钥无效")
    info = aggregation_server.report(report)
    return {"ok": True, "station_id": info.station_id, "is_online": info.is_online}


@router.get("/stations", dependencies=[Depends(require_permission("line:view"))])
async def list_stations(
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
):
    """获取所有工位状态"""
    stations = aggregation_server.get_all_stations()
    return {
        "stations": [s.model_dump() for s in stations],
        "summary": aggregation_server.get_line_summary(),
    }


@router.get(
    "/stations/{station_id}",
    dependencies=[Depends(require_permission("station:view"))],
)
async def get_station(
    station_id: str,
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
):
    """获取单个工位详情"""
    info = aggregation_server.get_station(station_id)
    if not info:
        raise HTTPException(status_code=404, detail="工位不存在")
    return info.model_dump()


@router.get("/line/summary", dependencies=[Depends(require_permission("line:view"))])
async def line_summary(
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
):
    """获取产线整体摘要"""
    return aggregation_server.get_line_summary()


@router.delete(
    "/stations/{station_id}",
    dependencies=[Depends(require_permission("station:manage"))],
)
async def remove_station(
    station_id: str,
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
):
    """移除工位"""
    if not aggregation_server.remove_station(station_id):
        raise HTTPException(status_code=404, detail="工位不存在")
    return {"ok": True}
