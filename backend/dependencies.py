"""
FastAPI 依赖注入工厂
所有共享服务实例通过 app.state 持有，路由通过 Depends 获取。
消除模块级单例，便于测试与多实例部署。
"""

import os

from fastapi import Request


def get_camera(request: Request):
    """摄像头采集服务"""
    return request.app.state.camera


def get_detector(request: Request):
    """手部检测器"""
    return request.app.state.detector


def get_sop_manager(request: Request):
    """SOP 管理器"""
    return request.app.state.sop_manager


def get_object_detector(request: Request):
    """物体检测器"""
    return request.app.state.object_detector


def get_alarm_manager(request: Request):
    """告警管理器"""
    return request.app.state.alarm_manager


def get_aggregation_server(request: Request):
    """中央聚合服务"""
    return request.app.state.aggregation_server


def get_execution_tracker(request: Request):
    """当前执行记录跟踪器"""
    return request.app.state.execution_tracker


def init_app_state(app) -> None:
    """
    创建所有共享服务实例并挂到 app.state。
    在 lifespan 启动阶段调用（同步创建，异步绑定循环在调用方补充）。
    """
    from camera_service import CameraService
    from hand_detector import HandDetector
    from sop_manager import SOPManager
    from detectors.object_detector import ObjectDetector
    from alarm.alarm_manager import AlarmManager
    from central.aggregation_server import AggregationServer
    from execution_tracker import ExecutionTracker

    app.state.camera = CameraService()
    app.state.detector = HandDetector()

    _object_enabled = os.getenv("OBJECT_DETECTION_ENABLED", "true").lower() == "true"
    _object_confidence = float(os.getenv("OBJECT_DETECTION_CONFIDENCE", "0.5"))
    app.state.object_detector = ObjectDetector(
        model_path=os.getenv("YOLO_MODEL_PATH"),
        confidence=_object_confidence,
        enabled=_object_enabled,
    )

    # 告警管理器：主事件循环在 lifespan 中通过 bind_loop 绑定
    app.state.alarm_manager = AlarmManager()

    app.state.sop_manager = SOPManager()

    app.state.aggregation_server = AggregationServer()
    app.state.execution_tracker = ExecutionTracker()
