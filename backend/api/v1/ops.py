"""设备运维 API。

- ``/ops/*``：管理端，需 ``station:view`` / ``station:manage`` 权限
- ``/station/ack``：工位端回执，公开路径，用 ``X-Station-Key`` 校验
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from auth.dependencies import require_permission
from central.aggregation_server import AggregationServer
from dependencies import get_aggregation_server, get_device_manager
from ops import ota_updater
from ops.device_manager import DeviceManager
from ops.health_monitor import evaluate

router = APIRouter(prefix="/ops", tags=["设备运维"])
agent_router = APIRouter(tags=["设备运维"])


class ConfigPushRequest(BaseModel):
    config: dict = Field(default_factory=dict)


class UpgradeRequest(BaseModel):
    model_id: str
    version: str


class AckRequest(BaseModel):
    station_id: str
    command_id: str
    status: str = "acked"
    message: str = ""


def _device_payload(info, manager: DeviceManager) -> dict:
    health, issues = evaluate(info)
    state = manager.state_of(info.station_id)
    return {
        "device_id": info.station_id,
        "name": info.station_name,
        "status": info.status,
        "health": health,
        "issues": issues,
        "app_version": info.app_version,
        "model_version": info.model_version,
        "camera_ok": info.camera_ok,
        "fps": info.fps,
        "latency_ms": info.latency_ms,
        "last_heartbeat": info.last_heartbeat.isoformat(),
        "config_version": state["config_version"],
        "pending_commands": state["pending_commands"],
        "last_ack": state["last_ack"],
    }


@router.get("/devices", dependencies=[Depends(require_permission("station:view"))])
async def list_devices(
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
    manager: DeviceManager = Depends(get_device_manager),
):
    """设备列表与健康摘要"""
    devices = [
        _device_payload(info, manager)
        for info in aggregation_server.get_all_stations()
    ]
    summary = {
        "total": len(devices),
        "healthy": sum(1 for item in devices if item["health"] == "healthy"),
        "warning": sum(1 for item in devices if item["health"] == "warning"),
        "offline": sum(1 for item in devices if item["health"] == "offline"),
    }
    return {"devices": devices, "summary": summary}


@router.get(
    "/devices/{device_id}",
    dependencies=[Depends(require_permission("station:view"))],
)
async def get_device(
    device_id: str,
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
    manager: DeviceManager = Depends(get_device_manager),
):
    """设备详情（含命令记录）"""
    info = aggregation_server.get_station(device_id)
    if not info:
        raise HTTPException(status_code=404, detail="设备不存在")
    payload = _device_payload(info, manager)
    payload["alarms"] = [alarm for alarm in info.alarms]
    payload["commands"] = manager.commands_of(device_id)
    return payload


@router.post(
    "/devices/{device_id}/config",
    dependencies=[Depends(require_permission("station:manage"))],
)
async def push_config(
    device_id: str,
    req: ConfigPushRequest,
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
    manager: DeviceManager = Depends(get_device_manager),
):
    """下发配置：工位下次心跳拿到命令，应用后回执"""
    if not aggregation_server.get_station(device_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    command = manager.set_config(device_id, req.config)
    return {"ok": True, "command": command}


@router.post(
    "/devices/{device_id}/upgrade",
    dependencies=[Depends(require_permission("station:manage"))],
)
async def schedule_upgrade(
    device_id: str,
    req: UpgradeRequest,
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
    manager: DeviceManager = Depends(get_device_manager),
):
    """下发模型升级命令（v1：登记目标版本，重启工位后生效）"""
    if not aggregation_server.get_station(device_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    try:
        ota_updater.resolve(req.model_id, req.version)
    except ota_updater.UpgradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    command = manager.schedule_upgrade(device_id, req.model_id, req.version)
    return {"ok": True, "command": command}


@router.get(
    "/devices/{device_id}/commands",
    dependencies=[Depends(require_permission("station:view"))],
)
async def list_commands(
    device_id: str,
    aggregation_server: AggregationServer = Depends(get_aggregation_server),
    manager: DeviceManager = Depends(get_device_manager),
):
    """设备命令历史"""
    if not aggregation_server.get_station(device_id):
        raise HTTPException(status_code=404, detail="设备不存在")
    return {"commands": manager.commands_of(device_id)}


@router.get(
    "/model-versions",
    dependencies=[Depends(require_permission("station:view"))],
)
async def list_model_versions():
    """可升级的模型版本目录"""
    return ota_updater.list_versions()


@agent_router.post("/station/ack")
async def station_ack(
    req: AckRequest,
    x_station_key: Optional[str] = Header(default=None),
    manager: DeviceManager = Depends(get_device_manager),
):
    """工位回执命令执行结果（公开路径，使用工位密钥）"""
    expected_key = os.getenv("STATION_API_KEY", "")
    if expected_key and x_station_key != expected_key:
        raise HTTPException(status_code=401, detail="工位密钥无效")
    try:
        ok = manager.ack(
            req.station_id, req.command_id, status=req.status, message=req.message
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="命令不存在")
    return {"ok": True}
