"""模板区域预设：把模板里的区域语义映射到实际画面。

模板按 ``left_area / center_area / right_area / top_area`` 定义步骤，
但现场摄像头视角各不相同。这里提供可一键铺开的区域预设，
避免新装部署必须先手工标定才能用模板。

复杂布局（料架偏左、成品区在上方等）仍需用区域标定工具微调。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from config import WORK_ZONES, update_work_zones

PRESETS: Dict[str, Dict[str, List[float]]] = {
    # 标准三段式：左料 / 中台 / 右成品，上方留空
    "standard": {
        "left_area": [0.00, 0.20, 0.35, 1.00],
        "center_area": [0.30, 0.20, 0.70, 1.00],
        "right_area": [0.65, 0.20, 1.00, 1.00],
        "top_area": [0.00, 0.00, 1.00, 0.25],
    },
    # 左右两段式：适合只有取料/放料两个动作的简单工位
    "two_zone": {
        "left_area": [0.00, 0.15, 0.45, 1.00],
        "right_area": [0.45, 0.15, 1.00, 1.00],
        "center_area": [0.35, 0.20, 0.65, 0.90],
        "top_area": [0.00, 0.00, 1.00, 0.20],
    },
}


class ZonePresetError(ValueError):
    """区域预设非法。"""


def list_presets() -> List[dict]:
    return [
        {"name": name, "zones": {key: list(value) for key, value in zones.items()}}
        for name, zones in PRESETS.items()
    ]


def get_preset(name: str = "standard") -> Dict[str, List[float]]:
    preset = PRESETS.get((name or "standard").strip())
    if preset is None:
        raise ZonePresetError("未知区域预设: {}".format(name))
    return {key: list(value) for key, value in preset.items()}


def apply_preset(name: str = "standard", zones_file: Optional[Path] = None) -> Dict[str, List[float]]:
    """应用预设：更新内存区域并落盘（默认写入 config.ZONES_FILE）。"""
    zones = get_preset(name)
    update_work_zones(zones)

    target = zones_file if zones_file is not None else Path(__file__).resolve().parent.parent / "data" / "zones.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(zones, ensure_ascii=False, indent=2), encoding="utf-8")
    return zones


def current_zones() -> Dict[str, List[float]]:
    return {name: list(coords) for name, coords in WORK_ZONES.items()}
