"""
摄像头采集服务
- 独立线程持续读取帧，避免阻塞主循环
- 线程安全地提供最新帧
- 使用 MSMF 后端（Windows Media Foundation），稳定且延迟低
"""

import threading
import time
import logging
from typing import Optional, Tuple

import cv2

from config import CAMERA_CONFIG

logger = logging.getLogger(__name__)


class CameraService:
    """
    线程化摄像头采集服务
    - 在后台线程中持续 grab()，保证读到的是最新帧而非缓冲帧
    - 提供 get_frame() 供消费者按需取帧
    """

    def __init__(self, config: Optional["CameraConfig"] = None):
        from config import CameraConfig  # 延迟导入，Python 3.8 类型注解在类定义时求值
        self.config = config or CAMERA_CONFIG
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[cv2.Mat] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # FPS 统计
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._fps_start: float = time.time()

    # ---------- 后端选择 ----------
    def _resolve_backend(self) -> int:
        """将配置中的后端名称解析为 cv2 常量"""
        mapping = {
            "MSMF": cv2.CAP_MSMF,
            "DSHOW": cv2.CAP_DSHOW,
            "AUTO": cv2.CAP_ANY,
        }
        return mapping.get(self.config.backend.upper(), cv2.CAP_MSMF)

    # ---------- 生命周期 ----------
    def start(self) -> bool:
        """打开摄像头并启动采集线程"""
        backend = self._resolve_backend()
        logger.info(
            "打开摄像头: index=%d backend=%s target=%dx%d@%dfps",
            self.config.index, self.config.backend,
            self.config.width, self.config.height, self.config.fps,
        )
        self._cap = cv2.VideoCapture(self.config.index, backend)
        if not self._cap.isOpened():
            logger.error("摄像头 %d 打开失败", self.config.index)
            return False

        # 设置采集参数（MSMF会协商到最接近的值）
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        # 缓冲区设为1，减少延迟（拿到最新帧）
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("摄像头已就绪，实际分辨率: %dx%d", actual_w, actual_h)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """停止采集并释放资源"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info("摄像头服务已停止")

    # ---------- 采集循环 ----------
    def _capture_loop(self):
        """后台采集线程：持续读取最新帧"""
        while self._running:
            if not self._cap or not self._cap.isOpened():
                time.sleep(0.1)
                continue

            ret, frame = self._cap.read()
            if not ret:
                logger.warning("读取帧失败，0.1s后重试")
                time.sleep(0.1)
                continue

            with self._lock:
                self._frame = frame

            # FPS 统计（每秒更新一次）
            self._frame_count += 1
            elapsed = time.time() - self._fps_start
            if elapsed >= 1.0:
                self._fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_start = time.time()

    # ---------- 消费接口 ----------
    def get_frame(self) -> Optional[cv2.Mat]:
        """获取最新一帧（BGR），无帧时返回 None"""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def get_fps(self) -> float:
        """获取当前采集FPS"""
        return self._fps

    def is_running(self) -> bool:
        return self._running
