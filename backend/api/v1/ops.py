"""设备运维 API。

设备状态来自数据库（``devices`` / ``device_commands``），
在线状态由最近心跳推导，重启后仍然保留配置与命令记录。
"""

import os
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import require_permission
from database import get_db
from dependencies import get_device_manager
from ops import ota_updater
from ops.device_manager import DeviceManager
from ops.health_monitor import evaluate
from tenancy.context import get_tenant_id

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


def _device_payload(manager: DeviceManager, db: Session, device) -> dict:
    online = manager.is_online(device)
    view = SimpleNamespace(
        is_online=online,
        camera_ok=device.camera_ok,
        fps=device.fps or 0.0,
        latency_ms=device.latency_ms or 0.0,
    )
    health, issues = evaluate(view)
    state = manager.state_of(db, device.device_id)

    return {
        "device_id": device.device_id,
        "name": device.name,
        "status": device.status,
        "health": health,
        "issues": issues,
        "app_version": device.app_version or "",
        "model_version": device.model_version or "",
        "camera_ok": bool(device.camera_ok),
        "fps": device.fps or 0.0,
        "latency_ms": device.latency_ms or 0.0,
        "last_heartbeat": device.last_seen.isoformat() if device.last_seen else "",
        "config_version": state["config_version"],
        "pending_commands": state["pending_commands"],
        "last_ack": state["last_ack"],
    }


@router.get("/devices", dependencies=[Depends(require_permission("station:view"))])
async def list_devices(
    db: Session = Depends(get_db),
    manager: DeviceManager = Depends(get_device_manager),
):
    """设备列表与健康摘要"""
    devices = [
        _device_payload(manager, db, device)
        for device in manager.list_devices(db, get_tenant_id())
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
    db: Session = Depends(get_db),
    manager: DeviceManager = Depends(get_device_manager),
):
    """设备详情（含命令记录）"""
    device = manager.get_device(db, get_tenant_id(), device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    payload = _device_payload(manager, db, device)
    payload["commands"] = manager.commands_of(db, device_id)
    return payload


@router.post(
    "/devices/{device_id}/config",
    dependencies=[Depends(require_permission("station:manage"))],
)
async def push_config(
    device_id: str,
    req: ConfigPushRequest,
    db: Session = Depends(get_db),
    manager: DeviceManager = Depends(get_device_manager),
):
    """下发配置：工位下次心跳拿到命令，应用后回执"""
    try:
        command = manager.set_config(db, get_tenant_id(), device_id, req.config)
    except KeyError:
        raise HTTPException(status_code=404, detail="设备不存在")
    return {"ok": True, "command": command}


@router.post(
    "/devices/{device_id}/upgrade",
    dependencies=[Depends(require_permission("station:manage"))],
)
async def schedule_upgrade(
    device_id: str,
    req: UpgradeRequest,
    db: Session = Depends(get_db),
    manager: DeviceManager = Depends(get_device_manager),
):
    """下发模型升级命令（v1：登记目标版本，重启工位后生效）"""
    if manager.get_device(db, get_tenant_id(), device_id) is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    try:
        ota_updater.resolve(req.model_id, req.version)
    except ota_updater.UpgradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    command = manager.schedule_upgrade(
        db, get_tenant_id(), device_id, req.model_id, req.version
    )
    return {"ok": True, "command": command}


@router.get(
    "/devices/{device_id}/commands",
    dependencies=[Depends(require_permission("station:view"))],
)
async def list_commands(
    device_id: str,
    db: Session = Depends(get_db),
    manager: DeviceManager = Depends(get_device_manager),
):
    """设备命令历史"""
    if manager.get_device(db, get_tenant_id(), device_id) is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    return {"commands": manager.commands_of(db, device_id)}


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
    db: Session = Depends(get_db),
    manager: DeviceManager = Depends(get_device_manager),
):
    """工位回执命令执行结果（公开路径，使用工位密钥）"""
    expected_key = os.getenv("STATION_API_KEY", "")
    if expected_key and x_station_key != expected_key:
        raise HTTPException(status_code=401, detail="工位密钥无效")
    try:
        ok = manager.ack(
            db, req.station_id, req.command_id, status=req.status, message=req.message
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="命令不存在")
    return {"ok": True}
