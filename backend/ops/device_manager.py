"""设备管理与远程运维。

v1 说明：设备在线状态来自 ``AggregationServer``（内存），控制面（配置、命令）
同样保存在进程内存中，服务重启后清空。持久化留到后续与工位注册表一起做。
"""

import logging
import uuid
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 单次心跳最多下发的命令数，避免响应体过大
PENDING_LIMIT = 5


class DeviceManager:
    """设备控制面：配置下发与远程升级命令队列。"""

    def __init__(self):
        self._state: Dict[str, dict] = {}

    def _device(self, device_id: str) -> dict:
        return self._state.setdefault(
            device_id,
            {
                "config": {},
                "config_version": 0,
                "commands": [],
                "last_ack": None,
            },
        )

    # ---------- 配置下发 ----------
    def set_config(self, device_id: str, config: dict) -> dict:
        state = self._device(device_id)
        state["config"] = dict(config)
        state["config_version"] += 1
        return self._enqueue(
            device_id,
            "config",
            {"config": state["config"], "version": state["config_version"]},
        )

    # ---------- 远程升级 ----------
    def schedule_upgrade(self, device_id: str, model_id: str, version: str) -> dict:
        return self._enqueue(
            device_id,
            "upgrade",
            {"model_id": model_id, "version": version},
        )

    # ---------- 命令通道 ----------
    def _enqueue(self, device_id: str, command_type: str, payload: dict) -> dict:
        command = {
            "command_id": uuid.uuid4().hex[:12],
            "device_id": device_id,
            "type": command_type,
            "payload": payload,
            "status": "pending",
        }
        self._device(device_id)["commands"].append(command)
        logger.info(
            "设备命令已入队: device=%s type=%s id=%s",
            device_id, command_type, command["command_id"],
        )
        return dict(command)

    def pending(self, device_id: str) -> List[dict]:
        commands = [
            dict(command)
            for command in self._device(device_id)["commands"]
            if command["status"] == "pending"
        ]
        return commands[:PENDING_LIMIT]

    def ack(
        self,
        device_id: str,
        command_id: str,
        status: str = "acked",
        message: str = "",
    ) -> bool:
        if status not in ("acked", "failed"):
            raise ValueError("回执状态只能是 acked 或 failed")
        state = self._device(device_id)
        for command in state["commands"]:
            if command["command_id"] == command_id:
                command["status"] = status
                state["last_ack"] = {
                    "command_id": command_id,
                    "status": status,
                    "message": message,
                    "type": command["type"],
                }
                logger.info(
                    "设备命令回执: device=%s id=%s status=%s",
                    device_id, command_id, status,
                )
                return True
        return False

    # ---------- 查询 ----------
    def state_of(self, device_id: str) -> dict:
        state = self._device(device_id)
        return {
            "config": dict(state["config"]),
            "config_version": state["config_version"],
            "pending_commands": len(self.pending(device_id)),
            "last_ack": state["last_ack"],
        }

    def commands_of(self, device_id: str) -> List[dict]:
        return [dict(command) for command in self._device(device_id)["commands"]]

    def reset(self) -> None:
        """清空控制面（测试与运维复位用）。"""
        self._state.clear()


def get_default_manager() -> DeviceManager:
    return DeviceManager()
