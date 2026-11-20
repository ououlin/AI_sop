"""
物体检测器
基于 YOLOv8 的轻量级物体检测，支持自定义模型
在无 ultralytics 时降级为颜色追踪（color-based tracking），保证系统可用
"""

import logging
import os
from typing import List, Optional, Dict

import cv2
import numpy as np

from models import ObjectDetection, BoundingBox
from config import WORK_ZONES, OBJECT_CLASS_ALIASES

logger = logging.getLogger(__name__)


def _resolve_business_class(raw_class: str) -> str:
    """
    将模型输出的 COCO 类名映射为业务名。
    例如 "remote" -> "circuit_board"（依据 config.OBJECT_CLASS_ALIASES）。
    若无映射则原样返回。
    """
    for business_name, aliases in OBJECT_CLASS_ALIASES.items():
        if raw_class in aliases:
            return business_name
    return raw_class


def _assign_zone(bbox: BoundingBox) -> str:
    """根据物体中心点判断所在工作区域"""
    cx, cy = bbox.center()
    for zone_name, (x1, y1, x2, y2) in list(WORK_ZONES.items()):
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            return zone_name
    return "unknown"


class ObjectDetector:
    """
    物体检测器
    - 优先使用 YOLOv8（ultralytics）进行通用物体检测
    - 当 ultralytics 不可用或未配置模型时，降级为颜色追踪
    - 支持自定义类别映射
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence: float = 0.5,
        enabled: bool = True,
    ):
        self.confidence = confidence
        self.enabled = enabled
        self._model = None
        self._mode = "disabled"  # yolo / color / disabled
        self._custom_classes: Dict[int, str] = {}

        if not enabled:
            logger.info("物体检测已禁用")
            return

        # 尝试加载 YOLO
        if model_path and os.path.exists(model_path):
            try:
                from ultralytics import YOLO
                self._model = YOLO(model_path)
                self._mode = "yolo"
                logger.info("YOLO 物体检测已加载: %s", model_path)
            except ImportError:
                logger.warning("ultralytics 未安装，物体检测降级为颜色追踪模式")
                self._mode = "color"
            except Exception as e:
                logger.error("YOLO 模型加载失败: %s，降级为颜色追踪", e)
                self._mode = "color"
        else:
            # 尝试加载默认 YOLO 模型
            try:
                from ultralytics import YOLO
                default_model = os.getenv(
                    "YOLO_MODEL_PATH", "yolov8n.pt"
                )
                self._model = YOLO(default_model)
                self._mode = "yolo"
                logger.info("YOLO 物体检测已加载默认模型: %s", default_model)
            except ImportError:
                logger.info("ultralytics 未安装，物体检测降级为颜色追踪模式")
                self._mode = "color"
            except Exception as e:
                logger.info("YOLO 默认模型加载失败(%s)，降级为颜色追踪", e)
                self._mode = "color"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_available(self) -> bool:
        return self._mode != "disabled"

    def detect(self, frame: np.ndarray) -> List[ObjectDetection]:
        """检测帧中的物体"""
        if not self.enabled or self._mode == "disabled":
            return []

        if self._mode == "yolo":
            return self._detect_yolo(frame)
        elif self._mode == "color":
            return self._detect_color(frame)
        return []

    def _detect_yolo(self, frame: np.ndarray) -> List[ObjectDetection]:
        """使用 YOLO 检测"""
        detections: List[ObjectDetection] = []
        try:
            h, w = frame.shape[:2]
            results = self._model(frame, conf=self.confidence, verbose=False)
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    raw_name = self._custom_classes.get(
                        cls_id, self._model.names.get(cls_id, f"class_{cls_id}")
                    )
                    # 将 COCO 类名映射为业务名（如 remote -> circuit_board）
                    class_name = _resolve_business_class(raw_name)
                    x1 = float(box.xyxy[0][0]) / w
                    y1 = float(box.xyxy[0][1]) / h
                    x2 = float(box.xyxy[0][2]) / w
                    y2 = float(box.xyxy[0][3]) / h
                    bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
                    det = ObjectDetection(
                        class_name=class_name,
                        confidence=float(box.conf[0]),
                        bbox=bbox,
                        current_zone=_assign_zone(bbox),
                    )
                    detections.append(det)
        except Exception as e:
            logger.exception("YOLO 检测异常: %s", e)
        return detections

    def _detect_color(self, frame: np.ndarray) -> List[ObjectDetection]:
        """
        颜色追踪降级方案：检测画面中的显著颜色块
        识别红色/绿色/蓝色物体，用于无 YOLO 环境下的基本演示
        """
        detections: List[ObjectDetection] = []
        try:
            h, w = frame.shape[:2]
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            color_ranges = {
                "red_object": [
                    ((0, 80, 80), (10, 255, 255)),
                    ((170, 80, 80), (180, 255, 255)),
                ],
                "green_object": [((40, 80, 80), (80, 255, 255))],
                "blue_object": [((100, 80, 80), (130, 255, 255))],
            }

            for name, ranges in color_ranges.items():
                mask = None
                for lower, upper in ranges:
                    m = cv2.inRange(hsv, np.array(lower), np.array(upper))
                    mask = m if mask is None else cv2.bitwise_or(mask, m)

                # 形态学去噪
                kernel = np.ones((5, 5), np.uint8)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

                contours, _ = cv2.findContours(
                    mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                for cnt in contours:
                    area = cv2.contourArea(cnt)
                    if area < 1500:  # 过滤小噪点
                        continue
                    x, y, cw, ch = cv2.boundingRect(cnt)
                    bbox = BoundingBox(
                        x1=x / w, y1=y / h,
                        x2=(x + cw) / w, y2=(y + ch) / h,
                    )
                    confidence = min(area / 10000.0, 1.0)
                    detections.append(ObjectDetection(
                        class_name=name,
                        confidence=confidence,
                        bbox=bbox,
                        current_zone=_assign_zone(bbox),
                    ))
        except Exception as e:
            logger.exception("颜色追踪异常: %s", e)
        return detections

    def draw(self, frame: np.ndarray, detections: List[ObjectDetection]) -> np.ndarray:
        """在画面上绘制物体检测框"""
        h, w = frame.shape[:2]
        colors = {
            "red_object": (0, 0, 255),
            "green_object": (0, 255, 0),
            "blue_object": (255, 0, 0),
        }
        for det in detections:
            color = colors.get(det.class_name, (200, 200, 200))
            x1 = int(det.bbox.x1 * w)
            y1 = int(det.bbox.y1 * h)
            x2 = int(det.bbox.x2 * w)
            y2 = int(det.bbox.y2 * h)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            cv2.putText(frame, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        return frame

    def close(self):
        self._model = None
