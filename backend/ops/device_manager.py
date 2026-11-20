"""设备控制面（持久化）。

设备与命令落在 ``devices`` / ``device_commands`` 两张表：
服务重启后配置、升级指令与回执不丢；在线状态由 ``last_seen`` 与心跳阈值推导，
不再依赖内存中的聚合服务状态。
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from db_models import DeviceCommandDB, DeviceDB

HEARTBEAT_TIMEOUT_SEC = 10.0
PENDING_LIMIT = 5
ACK_STATUSES = ("acked", "failed")


class DeviceManager:
    # ---------- 设备 ----------
    def touch(self, db: Session, tenant_id: int, report) -> DeviceDB:
        """工位心跳时更新设备记录（不存在则创建）。"""
        device = self.get_device(db, tenant_id, report.station_id)
        if device is None:
            device = DeviceDB(tenant_id=tenant_id, device_id=report.station_id)
            db.add(device)

        device.name = report.station_name or device.name or report.station_id
        device.status = report.status or "idle"
        device.app_version = report.app_version or device.app_version
        device.model_version = report.model_version or device.model_version
        device.camera_ok = bool(report.camera_ok)
        device.fps = float(report.fps or 0.0)
        device.latency_ms = float(report.latency_ms or 0.0)
        device.last_seen = datetime.now()

        db.commit()
        db.refresh(device)
        return device

    def get_device(
        self, db: Session, tenant_id: int, device_id: str
    ) -> Optional[DeviceDB]:
        return (
            db.query(DeviceDB)
            .filter(DeviceDB.tenant_id == tenant_id, DeviceDB.device_id == device_id)
            .first()
        )

    def list_devices(self, db: Session, tenant_id: int) -> List[DeviceDB]:
        return (
            db.query(DeviceDB)
            .filter(DeviceDB.tenant_id == tenant_id)
            .order_by(DeviceDB.device_id.asc())
            .all()
        )

    @staticmethod
    def is_online(device: DeviceDB, now: Optional[datetime] = None) -> bool:
        if device.last_seen is None:
            return False
        return (now or datetime.now()) - device.last_seen <= timedelta(
            seconds=HEARTBEAT_TIMEOUT_SEC
        )

    # ---------- 配置下发 / 远程升级 ----------
    def set_config(
        self, db: Session, tenant_id: int, device_id: str, config: dict
    ) -> dict:
        device = self.get_device(db, tenant_id, device_id)
        if device is None:
            raise KeyError(device_id)

        device.config_json = json.dumps(config, ensure_ascii=False)
        device.config_version = (device.config_version or 0) + 1
        db.commit()
        db.refresh(device)

        return self._enqueue(
            db,
            tenant_id,
            device_id,
            "config",
            {"config": config, "version": device.config_version},
        )

    def schedule_upgrade(
        self, db: Session, tenant_id: int, device_id: str, model_id: str, version: str
    ) -> dict:
        return self._enqueue(
            db, tenant_id, device_id, "upgrade", {"model_id": model_id, "version": version}
        )

    def _enqueue(
        self, db: Session, tenant_id: int, device_id: str, command_type: str, payload: dict
    ) -> dict:
        command = DeviceCommandDB(
            tenant_id=tenant_id,
            device_id=device_id,
            command_id=uuid.uuid4().hex[:12],
            type=command_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
            status="pending",
        )
        db.add(command)
        db.commit()
        db.refresh(command)
        return self._command_dict(command)

    # ---------- 命令通道 ----------
    def pending(self, db: Session, device_id: str, limit: int = PENDING_LIMIT) -> List[dict]:
        rows = (
            db.query(DeviceCommandDB)
            .filter(DeviceCommandDB.device_id == device_id, DeviceCommandDB.status == "pending")
            .order_by(DeviceCommandDB.id.asc())
            .limit(limit)
            .all()
        )
        return [self._command_dict(row) for row in rows]

    def ack(
        self,
        db: Session,
        device_id: str,
        command_id: str,
        status: str = "acked",
        message: str = "",
    ) -> bool:
        if status not in ACK_STATUSES:
            raise ValueError("回执状态只能是 acked 或 failed")

        command = (
            db.query(DeviceCommandDB)
            .filter(
                DeviceCommandDB.device_id == device_id,
                DeviceCommandDB.command_id == command_id,
            )
            .first()
        )
        if command is None:
            return False

        command.status = status
        command.message = (message or "")[:200]
        command.acked_at = datetime.now()
        db.commit()
        return True

    def commands_of(self, db: Session, device_id: str) -> List[dict]:
        rows = (
            db.query(DeviceCommandDB)
            .filter(DeviceCommandDB.device_id == device_id)
            .order_by(DeviceCommandDB.id.asc())
            .all()
        )
        return [self._command_dict(row) for row in rows]

    def state_of(self, db: Session, device_id: str) -> dict:
        device = db.query(DeviceDB).filter(DeviceDB.device_id == device_id).first()
        last_ack = (
            db.query(DeviceCommandDB)
            .filter(
                DeviceCommandDB.device_id == device_id,
                DeviceCommandDB.acked_at.isnot(None),
            )
            .order_by(DeviceCommandDB.acked_at.desc())
            .first()
        )
        return {
            "config": json.loads(device.config_json or "{}") if device else {},
            "config_version": device.config_version if device else 0,
            "pending_commands": len(self.pending(db, device_id)),
            "last_ack": self._command_dict(last_ack) if last_ack else None,
        }

    @staticmethod
    def _command_dict(row: DeviceCommandDB) -> dict:
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        return {
            "command_id": row.command_id,
            "device_id": row.device_id,
            "type": row.type,
            "payload": payload,
            "status": row.status,
            "message": row.message or "",
            "acked_at": row.acked_at.isoformat() if row.acked_at else None,
        }
