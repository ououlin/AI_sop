"""
后台处理循环：摄像头采集 -> 手部/物体检测 -> 步骤识别 -> 视频/状态推送
从 main.py 拆分，所有服务实例从 app.state 获取。

架构优化：
- 检测线程：后台独立线程持续运行检测，结果缓存
- 视频循环：异步循环独立推送视频帧，使用缓存的检测结果
- 这样视频推送不会被检测阻塞，保证流畅度
"""

import asyncio
import logging
import threading
import time
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np

from config import SERVER_CONFIG
from hand_detector import HandDetector
from models import HandResult, WSStatusMessage, StepStatus, ObjectDetection
from detectors.object_detector import _assign_zone

logger = logging.getLogger("ai_sop.pipeline")


class ProcessingPipeline:
    """
    主处理循环封装（解耦架构）
    - 检测线程：后台独立运行手部/物体检测
    - 视频循环：独立推送视频帧，使用缓存结果
    - 步骤识别与告警检查
    """

    def __init__(self, app):
        self.app = app
        self._video_task: Optional[asyncio.Task] = None
        self._detection_thread: Optional[threading.Thread] = None
        self._detection_running = False
        self._last_status_push = 0.0
        self._restart_count = 0
        self._max_restarts = 10
        self._cached_hands: List = []
        self._cached_objects: List = []
        self._detection_lock = threading.Lock()
        self._detection_interval = 3
        self._detection_counter = 0

    async def start(self) -> None:
        self._detection_running = True
        self._detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._detection_thread.start()
        self._video_task = asyncio.create_task(self._video_run())
        logger.info("处理循环已启动（检测线程+视频循环）")

    async def stop(self) -> None:
        self._detection_running = False
        if self._video_task:
            self._video_task.cancel()
            try:
                await self._video_task
            except asyncio.CancelledError:
                pass
        if self._detection_thread and self._detection_thread.is_alive():
            self._detection_thread.join(timeout=2.0)
        logger.info("处理循环已停止")

    def _detection_loop(self):
        """后台检测线程：持续运行手部和物体检测"""
        camera = self.app.state.camera
        detector = self.app.state.detector
        object_detector = self.app.state.object_detector
        sop_manager = self.app.state.sop_manager
        alarm_manager = self.app.state.alarm_manager
        execution_tracker = self.app.state.execution_tracker

        logger.info("检测线程已启动")
        while self._detection_running:
            try:
                frame = camera.get_frame()
                if frame is None:
                    time.sleep(0.02)
                    continue

                self._detection_counter += 1
                if self._detection_counter % self._detection_interval != 0:
                    time.sleep(0.01)
                    continue

                t0 = time.perf_counter()

                # 降采样检测输入
                orig_h, orig_w = frame.shape[:2]
                detect_w = 640
                if orig_w > detect_w:
                    scale = detect_w / orig_w
                    detect_h = int(orig_h * scale)
                    detect_frame = cv2.resize(frame, (detect_w, detect_h), interpolation=cv2.INTER_AREA)
                else:
                    detect_frame = frame
                    scale = 1.0

                # 并行检测
                hands_result = detector.detect(detect_frame)
                objects_result = object_detector.detect(detect_frame) if object_detector.is_available else []

                _, hands = hands_result
                objects = objects_result

                # 缩放坐标回原始分辨率
                if scale != 1.0:
                    for h in hands:
                        h.center_x /= scale
                        h.center_y /= scale
                        for lm in h.landmarks:
                            lm.x /= scale
                            lm.y /= scale
                    for o in objects:
                        o.bbox.x1 /= scale
                        o.bbox.y1 /= scale
                        o.bbox.x2 /= scale
                        o.bbox.y2 /= scale
                        o.current_zone = _assign_zone(o.bbox)

                # 更新缓存（线程安全）
                with self._detection_lock:
                    self._cached_hands = hands
                    self._cached_objects = objects

                # 步骤识别与告警
                if sop_manager.is_loaded() and not sop_manager.paused:
                    rec = sop_manager.recognizer
                    current_before_update = rec.current_step()
                    future_match = rec.find_out_of_sequence_match(hands, objects)
                    alarm_manager.check_sequence(current_before_update, future_match)
                    rec.update(hands, objects)
                    alarm_manager.check_timeout(rec.states, rec.current_index)
                    current_step = rec.current_step()
                    if current_step:
                        alarm_manager.check_object_missing(current_step, objects)
                    execution_tracker.sync(rec)

                t1 = time.perf_counter()
                logger.debug("检测耗时: %.1fms, hands=%d, objects=%d",
                           (t1 - t0) * 1000, len(hands), len(objects))

            except Exception as e:
                logger.exception("检测线程异常: %s", e)
                time.sleep(0.1)

        logger.info("检测线程已结束")

    async def _video_run(self) -> None:
        """视频推送循环：独立于检测，保证流畅"""
        logger.info("视频推送循环已开始")
        while True:
            try:
                await self._video_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("视频推送异常: %s", e)
                await asyncio.sleep(0.1)
        logger.info("视频推送循环已结束")

    async def _video_tick(self) -> None:
        """单次视频推送：获取最新帧，绘制缓存的检测结果，推送"""
        camera = self.app.state.camera
        object_detector = self.app.state.object_detector
        sop_manager = self.app.state.sop_manager
        alarm_manager = self.app.state.alarm_manager

        t_start = time.perf_counter()

        frame = camera.get_frame()
        if frame is None:
            with self._detection_lock:
                hands = list(self._cached_hands)
                objects = list(self._cached_objects)
            await self._maybe_push_status(
                hands, objects, False, sop_manager, alarm_manager, camera
            )
            await asyncio.sleep(0.03)
            return

        # 获取缓存的检测结果（线程安全）
        with self._detection_lock:
            hands = list(self._cached_hands)
            objects = list(self._cached_objects)

        orig_h, orig_w = frame.shape[:2]

        # 绘制工作区域和检测结果
        annotated = frame.copy()
        HandDetector.draw_zones(annotated)

        if object_detector.is_available and objects:
            object_detector.draw(annotated, objects)

        self._draw_step_overlay(annotated, hands, objects, sop_manager, alarm_manager, camera)

        # 推送视频帧（降采样到 960x540）
        push_frame = annotated
        push_w, push_h = 960, 540
        if orig_w > push_w:
            push_frame = cv2.resize(annotated, (push_w, push_h), interpolation=cv2.INTER_AREA)

        t_encode = time.perf_counter()
        await self._broadcast_video(push_frame)

        # 推送状态（节流）
        state_changed = False
        await self._maybe_push_status(
            hands, objects, state_changed, sop_manager, alarm_manager, camera
        )

        t_end = time.perf_counter()
        elapsed = (t_end - t_start) * 1000
        logger.debug("视频帧耗时: 总%.1fms (绘制%.1fms, 编码推送%.1fms)",
                     elapsed, (t_encode - t_start) * 1000, (t_end - t_encode) * 1000)

    # ============ 画面叠加 ============
    def _draw_step_overlay(self, frame: np.ndarray, hands, objects,
                           sop_manager, alarm_manager, camera) -> None:
        h, w = frame.shape[:2]

        if not sop_manager.is_loaded():
            cv2.putText(frame, "No SOP Loaded", (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            return

        rec = sop_manager.recognizer
        step = rec.current_step()

        if sop_manager.paused:
            cv2.putText(frame, "[PAUSED]", (w - 180, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

        if rec.all_done:
            cv2.putText(frame, "ALL STEPS COMPLETED!", (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            return

        if step:
            idx = rec.current_index + 1
            total = len(sop_manager.definition.steps)
            state = rec.states[rec.current_index]

            status_colors = {
                StepStatus.PENDING: (200, 200, 200),
                StepStatus.IN_PROGRESS: (50, 200, 50),
                StepStatus.TIMEOUT: (0, 0, 255),
                StepStatus.ERROR: (0, 0, 255),
                StepStatus.UNAUTHORIZED_SKIP: (0, 0, 255),
            }
            text_color = status_colors.get(state.status, (50, 200, 50))
            text = f"Step {idx}/{total}: {step.name}"
            cv2.putText(frame, text, (10, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)

            if state.status in (StepStatus.TIMEOUT, StepStatus.ERROR, StepStatus.UNAUTHORIZED_SKIP):
                cv2.putText(frame, f"[{state.status.value.upper()}]", (w - 280, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            progress = min(state.matched_duration / step.hold_duration_sec, 1.0)
            bar_x, bar_y, bar_w, bar_h = 10, 50, 300, 12
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                          (80, 80, 80), -1)
            cv2.rectangle(frame, (bar_x, bar_y),
                          (bar_x + int(bar_w * progress), bar_y + bar_h),
                          (0, 255, 0), -1)

        # 手势与区域信息
        y_off = 90
        for i, hand in enumerate(hands):
            info = f"Hand{i}: {hand.handedness.value} | {hand.gesture.value} | {hand.current_zone}"
            cv2.putText(frame, info, (10, y_off + i * 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)

        # 物体检测信息
        if objects:
            obj_y = y_off + len(hands) * 25 + 10
            for i, obj in enumerate(objects[:3]):
                info = f"Obj: {obj.class_name} ({obj.confidence:.2f}) @ {obj.current_zone}"
                cv2.putText(frame, info, (10, obj_y + i * 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 200), 1)

        # 活跃告警显示
        active = alarm_manager.active_alarms
        if active:
            alarm_y = h - 60
            for i, a in enumerate(active[-3:]):
                color = (0, 0, 255) if a.level.value == "critical" else (0, 165, 255)
                cv2.putText(frame, f"[{a.level.value.upper()}] {a.message[:50]}",
                            (10, alarm_y - i * 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        cv2.putText(frame, f"FPS: {camera.get_fps():.1f}", (w - 130, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

    # ============ WebSocket 推送 ============
    async def _broadcast_video(self, frame: np.ndarray) -> None:
        registry = self.app.state.ws_registry
        video_clients = registry.video_clients
        if not video_clients:
            return
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), SERVER_CONFIG.jpeg_quality],
        )
        if not ok:
            return
        data = buf.tobytes()

        dead = []
        for ws in video_clients:
            try:
                await ws.send_bytes(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            video_clients.discard(ws)

    async def _maybe_push_status(self, hands, objects, force: bool,
                                 sop_manager, alarm_manager, camera) -> None:
        now = time.time()
        if not force and (now - self._last_status_push) < SERVER_CONFIG.status_interval:
            return
        self._last_status_push = now

        registry = self.app.state.ws_registry
        status_clients = registry.status_clients
        if not status_clients:
            return

        if not sop_manager.is_loaded():
            return

        rec = sop_manager.recognizer
        msg = WSStatusMessage(
            sop_name=sop_manager.definition.sop_name,
            source=sop_manager.source,
            paused=sop_manager.paused,
            all_done=rec.all_done,
            current_step_index=rec.current_index,
            steps=[s.model_dump() for s in rec.states],
            hands=[h.model_dump() for h in hands],
            objects=[o.model_dump() for o in objects],
            alarms=[a.model_dump() for a in alarm_manager.active_alarms],
            fps=camera.get_fps(),
            timestamp=datetime.now().isoformat(),
        )
        payload = msg.model_dump_json()
        dead = []
        for ws in status_clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            status_clients.discard(ws)
