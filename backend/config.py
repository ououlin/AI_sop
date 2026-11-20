"""
AI SOP 系统全局配置
包含摄像头参数、区域定义、MediaPipe参数、服务端口等
优先从环境变量读取，支持 .env 文件
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()


# ============ 路径配置 ============
BASE_DIR = Path(__file__).resolve().parent.parent          # g:\ai_sop
BACKEND_DIR = BASE_DIR / "backend"
SOPS_DIR = BASE_DIR / "sops"


# ============ 摄像头配置 ============
@dataclass
class CameraConfig:
    """摄像头采集参数"""
    index: int = int(os.getenv("CAMERA_INDEX", 0))
    backend: str = os.getenv("CAMERA_BACKEND", "MSMF")
    width: int = int(os.getenv("CAMERA_WIDTH", 640))
    height: int = int(os.getenv("CAMERA_HEIGHT", 480))
    fps: int = int(os.getenv("CAMERA_FPS", 30))
    buffer_size: int = 1


# ============ MediaPipe 手部检测配置 ============
@dataclass
class HandDetectorConfig:
    """MediaPipe Hands 参数"""
    static_image_mode: bool = False       # 视频流模式，启用跟踪降低计算量
    max_num_hands: int = 2                # 最多检测双手
    min_detection_confidence: float = 0.6 # 检测置信度阈值
    min_tracking_confidence: float = 0.5  # 跟踪置信度阈值


# ============ 工作区域定义 ============
# 使用归一化坐标 [x_min, y_min, x_max, y_max] (0~1)
# 这样无论摄像头分辨率如何变化，区域定义都保持一致
WORK_ZONES: Dict[str, Tuple[float, float, float, float]] = {
    "left_area":   (0.00, 0.20, 0.35, 1.00),   # 左侧物料区
    "center_area": (0.30, 0.20, 0.70, 1.00),   # 中央工作台
    "right_area":  (0.65, 0.20, 1.00, 1.00),   # 右侧成品区
    "top_area":    (0.00, 0.00, 1.00, 0.25),   # 上方区域（预留）
}

# 区域显示颜色 (BGR)
ZONE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "left_area":   (255, 200, 100),   # 橙黄
    "center_area": (100, 255, 100),   # 绿色
    "right_area":  (100, 200, 255),   # 蓝
    "top_area":    (200, 200, 200),   # 灰
}


# ============ WebSocket / 服务配置 ============
@dataclass
class ServerConfig:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", 8000))
    jpeg_quality: int = int(os.getenv("JPEG_QUALITY", 60))
    status_interval: float = float(os.getenv("STATUS_INTERVAL", 0.2))
    frontend_dist: str = str(BASE_DIR / "frontend" / "dist")


# ============ 默认SOP文件 ============
DEFAULT_SOP_FILE: str = "assembly_demo.json"


# ============ 物体检测自定义类别别名映射 ============
# 业务名 -> COCO/模型输出类名列表
# 用户在 SOP 中写业务名（如 circuit_board），检测器输出 COCO 类名后，
# step_recognizer 通过此映射判定 required_objects 是否满足。
# 这样无需训练自定义模型即可让"自定义类别"语义成立。
# 可通过环境变量 OBJECT_CLASS_ALIASES_JSON 覆盖（JSON 字符串）。
OBJECT_CLASS_ALIASES: Dict[str, List[str]] = {
    "circuit_board": ["remote", "cell phone", "keyboard", "laptop"],
    "component": ["remote", "cell phone"],
    "tool": ["scissors", "knife"],
    "product": ["bottle", "cup", "book"],
}


# ============ 区域标定数据持久化 ============
# 产线工程师通过前端 ZoneCalibrator 标定的区域写入此文件（归一化坐标）。
# 启动时若存在则覆盖上方 WORK_ZONES 默认值。
DATA_DIR = BASE_DIR / "data"
ZONES_FILE = DATA_DIR / "zones.json"


def update_work_zones(zones: Dict[str, List[float]]) -> None:
    """Validate and replace the live zone map used by all detectors."""
    normalized: Dict[str, Tuple[float, float, float, float]] = {}
    for name, coords in zones.items():
        if len(coords) != 4:
            raise ValueError(f"区域 {name} 必须包含4个坐标")
        x_min, y_min, x_max, y_max = (float(value) for value in coords)
        if not all(0.0 <= value <= 1.0 for value in (x_min, y_min, x_max, y_max)):
            raise ValueError(f"区域 {name} 坐标必须在0到1之间")
        if x_min >= x_max or y_min >= y_max:
            raise ValueError(f"区域 {name} 坐标范围无效")
        normalized[name] = (x_min, y_min, x_max, y_max)
    if not normalized:
        raise ValueError("至少需要一个区域")
    WORK_ZONES.clear()
    WORK_ZONES.update(normalized)


def load_work_zones() -> None:
    """Load persisted calibration at startup, keeping defaults on failure."""
    if not ZONES_FILE.exists():
        return
    try:
        raw = json.loads(ZONES_FILE.read_text(encoding="utf-8"))
        update_work_zones(raw)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Invalid calibration must not prevent the service from starting.
        return


load_work_zones()


# ============ 全局实例 ============
CAMERA_CONFIG = CameraConfig()
HAND_DETECTOR_CONFIG = HandDetectorConfig()
SERVER_CONFIG = ServerConfig()


# ============ 部署形态开关 ============
# ENABLE_LOCAL_AGGREGATION: 是否在本进程挂载中央聚合路由（产线看板）。
#   true(默认)：进程内聚合，单机部署；false：工位须上报到远程 CENTRAL_SERVER_URL。
ENABLE_LOCAL_AGGREGATION: bool = os.getenv("ENABLE_LOCAL_AGGREGATION", "true").lower() == "true"

# STATION_REPORT_TO_SELF: 当 CENTRAL_SERVER_URL 指向本机端口时，是否仍启动工位上报。
#   false(默认)：检测到自调用即跳过，避免 httpx 回环；true：强制上报（自测用）。
STATION_REPORT_TO_SELF: bool = os.getenv("STATION_REPORT_TO_SELF", "false").lower() == "true"
