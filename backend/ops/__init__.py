"""设备运维：健康监控、配置下发与远程升级。"""

from ops.device_manager import DeviceManager
from ops.health_monitor import evaluate
from ops.ota_updater import UpgradeError, list_versions, resolve

__all__ = [
    "DeviceManager",
    "UpgradeError",
    "evaluate",
    "list_versions",
    "resolve",
]
