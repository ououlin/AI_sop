"""
手部检测模块
自动兼容新旧两版 MediaPipe API：
- 旧版 (v0.10.11-, Python 3.8): mp.solutions  API
- 新版 (v0.10.30+, Python 3.9+): mp.tasks.vision API

提供：21关键点骨架检测、4种手势识别、骨架绘制、区域判定
"""

import logging
import time
from pathlib import Path
from typing import List, Tuple, Optional

import cv2
import numpy as np
import mediapipe as mp

from models import HandResult, HandType, GestureType, Landmark
from config import HAND_DETECTOR_CONFIG, WORK_ZONES, ZONE_COLORS

logger = logging.getLogger(__name__)

# ============ API 检测 ============
_HAS_TASKS_API = hasattr(mp, "tasks") and hasattr(mp.tasks, "vision")

if _HAS_TASKS_API:
    logger.info("MediaPipe Tasks API 已检测，使用新版接口")
else:
    logger.info("MediaPipe Solutions API 已检测，使用旧版接口")

# ============ 旧版 API 常量 ============
if not _HAS_TASKS_API:
    mp_hands_module = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles
    HAND_CONNECTIONS = mp_hands_module.HAND_CONNECTIONS


class HandDetector:
    """
    MediaPipe 手部检测封装（自动适配新旧 API）
    """

    def __init__(self, config=HAND_DETECTOR_CONFIG):
        self.config = config
        self._api = "tasks" if _HAS_TASKS_API else "solutions"
        self._landmarker = None
        self._hands = None
        self._ts_start = int(time.time() * 1000)
        self._frame_count = 0

        if _HAS_TASKS_API:
            self._init_tasks_api()
        else:
            self._init_solutions_api()

    def _init_tasks_api(self):
        """初始化新版 Tasks API"""
        _MODEL_PATH = Path(__file__).resolve().parent / "hand_landmarker.task"
        if not _MODEL_PATH.exists():
            raise FileNotFoundError(
                f"模型文件未找到: {_MODEL_PATH}\n"
                "下载命令: Invoke-WebRequest -Uri "
                "'https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                "hand_landmarker/float16/latest/hand_landmarker.task' "
                f"-OutFile '{_MODEL_PATH}'"
            )
        base_options = mp.tasks.BaseOptions(model_asset_path=str(_MODEL_PATH))
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=self.config.max_num_hands,
            min_hand_detection_confidence=self.config.min_detection_confidence,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=self.config.min_tracking_confidence,
        )
        self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        logger.info("HandDetector: Tasks API 初始化完成")

    def _init_solutions_api(self):
        """初始化旧版 Solutions API"""
        self._hands = mp_hands_module.Hands(
            static_image_mode=self.config.static_image_mode,
            max_num_hands=self.config.max_num_hands,
            min_detection_confidence=self.config.min_detection_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
        )
        logger.info("HandDetector: Solutions API 初始化完成")

    def close(self):
        if _HAS_TASKS_API and self._landmarker:
            self._landmarker.close()
            self._landmarker = None
        elif not _HAS_TASKS_API and self._hands:
            self._hands.close()
            self._hands = None

    # ========== 统一检测接口 ==========
    def detect(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, List[HandResult]]:
        """检测手部并返回 (标注图像, 结果列表)"""
        if _HAS_TASKS_API:
            return self._detect_tasks(frame_bgr)
        else:
            return self._detect_solutions(frame_bgr)

    _HAND_CONNECTIONS = [
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (5, 9), (9, 10), (10, 11), (11, 12),
        (9, 13), (13, 14), (14, 15), (15, 16),
        (13, 17), (17, 18), (18, 19), (19, 20),
        (0, 17),
    ]

    def _draw_hand_landmarks(self, frame: np.ndarray, landmarks, frame_shape):
        h, w = frame_shape[:2]
        points = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
        for i, (x, y) in enumerate(points):
            cv2.circle(frame, (x, y), 4, (0, 255, 0), -1)
            cv2.circle(frame, (x, y), 6, (0, 200, 0), 1)
        for start, end in self._HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], (0, 200, 0), 2)

    # ========== 新版 Tasks API 检测 ==========
    def _detect_tasks(self, frame_bgr: np.ndarray):
        self._frame_count += 1
        timestamp_ms = int(time.time() * 1000) - self._ts_start + self._frame_count

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        annotated = frame_bgr.copy()
        hand_results: List[HandResult] = []

        if result.hand_landmarks and result.handedness:
            for hand_lms, handed_info in zip(result.hand_landmarks, result.handedness):
                self._draw_hand_landmarks(annotated, hand_lms, frame_bgr.shape)
                hr = self._parse_hand(hand_lms, handed_info[0].category_name, frame_bgr.shape)
                hand_results.append(hr)

        return annotated, hand_results

    # ========== 旧版 Solutions API 检测 ==========
    def _detect_solutions(self, frame_bgr: np.ndarray):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_rgb.flags.writeable = False
        results = self._hands.process(frame_rgb)
        frame_rgb.flags.writeable = True

        annotated = frame_bgr.copy()
        hand_results: List[HandResult] = []

        if results.multi_hand_landmarks and results.multi_handedness:
            for hand_lms, handed_info in zip(
                results.multi_hand_landmarks, results.multi_handedness
            ):
                # 绘制骨架
                mp_draw.draw_landmarks(
                    annotated, hand_lms, HAND_CONNECTIONS,
                    mp_styles.get_default_hand_landmarks_style(),
                    mp_styles.get_default_hand_connections_style(),
                )
                # 旧版 label: "Left"/"Right" → 提取后直接传
                label = handed_info.classification[0].label
                hr = self._parse_hand(
                    hand_lms.landmark, label, frame_bgr.shape
                )
                hand_results.append(hr)

        return annotated, hand_results

    # ========== 结果解析 ==========
    def _parse_hand(self, landmarks_iterable, hand_label: str, frame_shape) -> HandResult:
        """
        统一解析手部关键点 → HandResult
        landmarks_iterable: 可迭代的 landmark 对象（新旧 API 统一通过 .x/.y/.z 访问）
        hand_label: "Left" / "Right" 字符串
        """
        h, w = frame_shape[:2]
        landmarks: List[Landmark] = []

        for lm in landmarks_iterable:
            landmarks.append(Landmark(x=lm.x, y=lm.y, z=lm.z))

        handedness = HandType(hand_label) if hand_label in ("Left", "Right") else HandType.RIGHT

        cx_norm = (landmarks[0].x + landmarks[9].x) / 2
        cy_norm = (landmarks[0].y + landmarks[9].y) / 2

        gesture = self._recognize_gesture(landmarks)
        zone = self._locate_zone(cx_norm, cy_norm)

        return HandResult(
            handedness=handedness,
            gesture=gesture,
            landmarks=landmarks,
            center_x=cx_norm,
            center_y=cy_norm,
            current_zone=zone,
        )

    # ========== 手势识别 ==========
    def _recognize_gesture(self, lms: List[Landmark]) -> GestureType:
        """
        21关键点几何关系识别4种手势
        索引: 拇指1-4, 食指5-8, 中指9-12, 无名指13-16, 小指17-20, 手腕0
        """
        def finger_extended(tip_idx: int, pip_idx: int) -> bool:
            return lms[tip_idx].y < lms[pip_idx].y

        def thumb_extended() -> bool:
            def dist(a, b):
                return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
            return dist(lms[4], lms[0]) > dist(lms[2], lms[0]) * 1.2

        def pinch_detected() -> bool:
            d = ((lms[4].x - lms[8].x) ** 2 + (lms[4].y - lms[8].y) ** 2) ** 0.5
            palm = ((lms[0].x - lms[9].x) ** 2 + (lms[0].y - lms[9].y) ** 2) ** 0.5
            if palm < 1e-3:
                return False
            return (d / palm) < 0.4

        # 优先捏合
        if pinch_detected():
            if not finger_extended(12, 10) and not finger_extended(16, 14):
                return GestureType.PINCH

        index_ext = finger_extended(8, 6)
        middle_ext = finger_extended(12, 10)
        ring_ext = finger_extended(16, 14)
        pinky_ext = finger_extended(20, 18)
        thumb_ext = thumb_extended()
        ext_count = sum([index_ext, middle_ext, ring_ext, pinky_ext])

        if ext_count == 0 and not thumb_ext:
            return GestureType.FIST
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            return GestureType.POINT
        if ext_count >= 4:
            return GestureType.OPEN

        return GestureType.UNKNOWN

    # ========== 区域判定 ==========
    def _locate_zone(self, x: float, y: float) -> str:
        for zone_name, (x1, y1, x2, y2) in list(WORK_ZONES.items()):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return zone_name
        return "unknown"

    # ========== 可视化 ==========
    _zone_cache: Optional[np.ndarray] = None
    _zone_cache_shape: Tuple[int, int] = (0, 0)

    @staticmethod
    def draw_zones(frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        if HandDetector._zone_cache is None or HandDetector._zone_cache_shape != (h, w):
            overlay = np.zeros((h, w, 3), dtype=np.uint8)
            for zone_name, (x1, y1, x2, y2) in list(WORK_ZONES.items()):
                pt1 = (int(x1 * w), int(y1 * h))
                pt2 = (int(x2 * w), int(y2 * h))
                color = ZONE_COLORS.get(zone_name, (200, 200, 200))
                cv2.rectangle(overlay, pt1, pt2, color, -1)
            HandDetector._zone_cache = overlay
            HandDetector._zone_cache_shape = (h, w)
        cv2.addWeighted(HandDetector._zone_cache, 0.15, frame, 0.85, 0, frame)
        for zone_name, (x1, y1, x2, y2) in list(WORK_ZONES.items()):
            pt1 = (int(x1 * w), int(y1 * h))
            cv2.putText(frame, zone_name, (pt1[0] + 8, pt1[1] + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame
