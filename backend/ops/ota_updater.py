"""模型版本目录与远程升级。

v1 只做「版本登记 + 命令下发 + 回执」，工位进程收到升级命令后
记录目标版本并回执；真正替换权重文件需要重启工位服务（后续接 OTA 下载器）。
"""

from typing import List

MODEL_VERSIONS = [
    {
        "model_id": "yolov8n",
        "version": "8.2.0",
        "channel": "stable",
        "notes": "默认稳定版，误检率与速度平衡",
    },
    {
        "model_id": "yolov8n",
        "version": "8.3.0",
        "channel": "candidate",
        "notes": "候选版本，建议先灰度一台工位",
    },
    {
        "model_id": "color-tracker",
        "version": "builtin",
        "channel": "fallback",
        "notes": "内置颜色追踪，无模型权重依赖",
    },
]


class UpgradeError(ValueError):
    """升级参数非法。"""


def list_versions() -> List[dict]:
    return [dict(item) for item in MODEL_VERSIONS]


def resolve(model_id: str, version: str) -> dict:
    for item in MODEL_VERSIONS:
        if item["model_id"] == model_id and item["version"] == version:
            return dict(item)
    raise UpgradeError("未知模型版本: {}@{}".format(model_id, version))
