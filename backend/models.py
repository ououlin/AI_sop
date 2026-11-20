"""
数据模型定义 (Pydantic)
用于API响应、WebSocket消息、SOP结构等的统一数据格式
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


# ============ 手部检测相关 ============

class GestureType(str, Enum):
    """基础手势类型"""
    OPEN = "open"            # 五指张开
    FIST = "fist"            # 握拳
    PINCH = "pinch"          # 捏合（拇指+食指）
    POINT = "point"          # 指向（食指伸出）
    UNKNOWN = "unknown"      # 未识别


class HandType(str, Enum):
    """左右手"""
    LEFT = "Left"
    RIGHT = "Right"


class Landmark(BaseModel):
    """单个关键点（归一化坐标）"""
    x: float
    y: float
    z: float = 0.0


class HandResult(BaseModel):
    """单只手的检测结果"""
    handedness: HandType
    gesture: GestureType = GestureType.UNKNOWN
    # 21个关键点（归一化坐标 0~1）
    landmarks: List[Landmark] = Field(default_factory=list)
    # 手掌中心点（归一化坐标），用于区域判定
    center_x: float = 0.5
    center_y: float = 0.5
    # 当前所在的工作区域
    current_zone: str = "unknown"


# ============ 物体检测相关 ============

class BoundingBox(BaseModel):
    """边界框（归一化坐标 0~1）"""
    x1: float
    y1: float
    x2: float
    y2: float

    def center(self) -> tuple:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def in_zone(self, zone_bbox) -> bool:
        """判断物体中心点是否落在指定区域内"""
        cx, cy = self.center()
        return zone_bbox[0] <= cx <= zone_bbox[2] and zone_bbox[1] <= cy <= zone_bbox[3]


class ObjectDetection(BaseModel):
    """单个物体检测结果"""
    class_name: str
    confidence: float
    bbox: BoundingBox
    # 物体当前所在的工作区域（由检测器填充）
    current_zone: str = "unknown"


class RequiredObject(BaseModel):
    """步骤要求的物体条件"""
    class_name: str                    # 物体类别名
    min_count: int = 1                 # 最少数量
    target_zone: Optional[str] = None  # 目标区域，None表示不限区域


# ============ 步骤识别相关 ============

class StepStatus(str, Enum):
    """步骤状态机"""
    PENDING = "pending"                      # 未开始
    IN_PROGRESS = "in_progress"              # 进行中（条件满足中）
    COMPLETED = "completed"                  # 已完成
    SKIPPED = "skipped"                      # 已跳过（授权）
    ERROR = "error"                          # 操作错误
    TIMEOUT = "timeout"                      # 超时未完成
    UNAUTHORIZED_SKIP = "unauthorized_skip"  # 未授权跳过


class SOPStep(BaseModel):
    """单个SOP步骤定义"""
    step_id: int
    name: str
    target_zone: str                              # 目标工作区域
    required_gesture: GestureType = GestureType.UNKNOWN  # 需要的手势，UNKNOWN表示不限
    required_objects: List[RequiredObject] = Field(default_factory=list)  # 要求的物体
    hold_duration_sec: float = 1.0                # 条件持续时长（秒）
    timeout_sec: float = 300.0                    # 步骤超时时间（秒），默认5分钟
    description: str = ""


class SOPDefinition(BaseModel):
    """完整SOP定义"""
    sop_name: str
    version: str = "1.0"
    # 标准节拍（秒）；0 表示未配置，报表会按步骤配置派生
    standard_cycle_sec: float = 0.0
    steps: List[SOPStep] = Field(default_factory=list)


class StepRuntimeState(BaseModel):
    """步骤运行时状态"""
    step_id: int
    name: str
    status: StepStatus = StepStatus.PENDING
    # 当前条件已满足的累计时间（秒）
    matched_duration: float = 0.0
    # 步骤要求的持续时长（秒），用于前端计算真实进度
    hold_duration_sec: float = 1.0
    # 步骤超时时间（秒）
    timeout_sec: float = 300.0
    # 完成时间戳
    completed_at: Optional[datetime] = None
    # 步骤开始时间戳
    started_at: Optional[datetime] = None
    description: str = ""


# ============ 告警相关 ============

class AlarmLevel(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlarmType(str, Enum):
    """告警类型"""
    TIMEOUT = "timeout"
    SEQUENCE_ERROR = "sequence_error"
    UNAUTHORIZED_SKIP = "unauthorized_skip"
    OBJECT_MISSING = "object_missing"
    ZONE_VIOLATION = "zone_violation"


class Alarm(BaseModel):
    """告警事件"""
    id: str
    level: AlarmLevel = AlarmLevel.WARNING
    type: AlarmType
    step_id: Optional[int] = None
    step_name: Optional[str] = None
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    acknowledged: bool = False


# ============ WebSocket 消息 ============

class WSStatusMessage(BaseModel):
    """状态推送消息"""
    type: str = "status"
    sop_name: str
    source: Optional[str] = None
    paused: bool = False
    all_done: bool = False
    current_step_index: int                       # 当前进行步骤的索引
    steps: List[StepRuntimeState] = Field(default_factory=list)
    # 最近检测到的手部信息摘要
    hands: List[HandResult] = Field(default_factory=list)
    # 最近检测到的物体
    objects: List[ObjectDetection] = Field(default_factory=list)
    # 当前活跃告警
    alarms: List[Alarm] = Field(default_factory=list)
    fps: float = 0.0
    timestamp: str = ""


class WSControlMessage(BaseModel):
    """前端控制消息"""
    action: str = "start"     # start / pause / reset / skip / load_sop
    sop_file: Optional[str] = None
