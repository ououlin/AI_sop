"""
工序步骤识别引擎
基于 状态机 + 区域匹配 + 手势匹配 + 物体检测 + 时序确认 的识别逻辑

识别流程：
1. 获取当前待完成步骤的目标区域、所需手势和所需物体
2. 检查是否有手部落在目标区域
3. 检查手势是否符合要求（UNKNOWN表示不限手势）
4. 检查物体检测是否符合要求（无 required_objects 则跳过）
5. 条件满足时累计持续时间，达到阈值则标记完成并推进
"""

import time
import logging
from typing import List, Optional
from datetime import datetime

from models import (
    HandResult, SOPStep, StepRuntimeState, StepStatus, GestureType,
    ObjectDetection, RequiredObject,
)
from config import OBJECT_CLASS_ALIASES

logger = logging.getLogger(__name__)


def _class_matches(detected: str, required: str) -> bool:
    """
    判断检测到的类名是否满足步骤要求的类名。
    支持业务别名映射：required 为业务名（如 circuit_board），
    detected 可为业务名或 COCO 原始类名（如 remote）。
    """
    if detected == required:
        return True
    aliases = OBJECT_CLASS_ALIASES.get(required, [])
    return detected in aliases


class StepRecognizer:
    """
    步骤识别引擎
    - 接收手部检测和物体检测结果，驱动步骤状态机
    - 线程安全由调用方保证（在主处理循环中单线程调用）
    """

    def __init__(self, steps: List[SOPStep]):
        self._steps = steps
        self._current_index = 0
        # 当前步骤条件累计开始时间
        self._match_start_time: Optional[float] = None
        # 步骤首次进入时间（用于超时计算）
        self._step_enter_time: Optional[float] = None
        # 初始化运行时状态
        self._states: List[StepRuntimeState] = [
            StepRuntimeState(
                step_id=s.step_id,
                name=s.name,
                status=StepStatus.PENDING,
                hold_duration_sec=s.hold_duration_sec,
                timeout_sec=s.timeout_sec,
                description=s.description,
            )
            for s in steps
        ]
        self._all_done = False

    # ---------- 状态访问 ----------
    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def all_done(self) -> bool:
        return self._all_done

    @property
    def states(self) -> List[StepRuntimeState]:
        return self._states

    def current_step(self) -> Optional[SOPStep]:
        if self._current_index < len(self._steps):
            return self._steps[self._current_index]
        return None

    @property
    def step_enter_time(self) -> Optional[float]:
        return self._step_enter_time

    # ---------- 重置 / 跳过 ----------
    def reset(self):
        self._current_index = 0
        self._match_start_time = None
        self._step_enter_time = None
        self._all_done = False
        now = datetime.now()
        for st in self._states:
            st.status = StepStatus.PENDING
            st.matched_duration = 0.0
            st.completed_at = None
            st.started_at = None
        # 第一个步骤设置开始时间
        if self._states:
            self._states[0].started_at = now
            self._step_enter_time = time.time()

    def skip_current(self, authorized: bool = True):
        """跳过当前步骤
        :param authorized: True=授权跳过(SKIPPED), False=未授权跳过(UNAUTHORIZED_SKIP)
        """
        if self._current_index < len(self._steps):
            if authorized:
                self._states[self._current_index].status = StepStatus.SKIPPED
            else:
                self._states[self._current_index].status = StepStatus.UNAUTHORIZED_SKIP
            self._advance_to_next()

    def _advance_to_next(self):
        """推进到下一个步骤"""
        self._current_index += 1
        self._match_start_time = None
        self._step_enter_time = time.time()
        # 设置下一步开始时间
        if self._current_index < len(self._states):
            self._states[self._current_index].started_at = datetime.now()
        self._check_completion()

    # ---------- 核心：更新 ----------
    def update(
        self,
        hands: List[HandResult],
        objects: Optional[List[ObjectDetection]] = None,
    ) -> bool:
        """
        根据手部检测和物体检测结果更新步骤状态
        :return: 是否有步骤状态发生变化（用于触发推送）
        """
        if self._all_done:
            return False

        step = self.current_step()
        if step is None:
            return False

        # 首次进入当前步骤时记录开始时间
        if self._step_enter_time is None:
            self._step_enter_time = time.time()
            self._states[self._current_index].started_at = datetime.now()

        state = self._states[self._current_index]
        prev_status = state.status

        # 已是终态（TIMEOUT/ERROR/UNAUTHORIZED_SKIP）则不更新
        if state.status in (StepStatus.TIMEOUT, StepStatus.ERROR, StepStatus.UNAUTHORIZED_SKIP):
            return False

        # 判断条件是否满足
        matched = self._check_conditions(step, hands, objects or [])

        if matched:
            if self._match_start_time is None:
                self._match_start_time = time.time()
            elapsed = time.time() - self._match_start_time
            state.matched_duration = elapsed
            state.status = StepStatus.IN_PROGRESS

            # 达到持续时间阈值 -> 完成
            if elapsed >= step.hold_duration_sec:
                state.status = StepStatus.COMPLETED
                state.completed_at = datetime.now()
                state.matched_duration = step.hold_duration_sec
                logger.info("步骤完成: [%d] %s", step.step_id, step.name)
                self._advance_to_next()
                return True
        else:
            # 条件不满足，重置累计
            if self._match_start_time is not None:
                self._match_start_time = None
                state.matched_duration = 0.0
            # 如果之前是 IN_PROGRESS，回退到 PENDING
            if state.status == StepStatus.IN_PROGRESS:
                state.status = StepStatus.PENDING

        return state.status != prev_status

    # ---------- 条件判定 ----------
    def _check_conditions(
        self,
        step: SOPStep,
        hands: List[HandResult],
        objects: List[ObjectDetection],
    ) -> bool:
        """
        判断当前检测结果是否满足步骤条件
        条件：手部（区域+手势）AND 物体（如果配置了 required_objects）
        """
        # 1. 手部条件检查
        hand_ok = self._check_hand_condition(step, hands)
        if not hand_ok:
            return False

        # 2. 物体条件检查（如果步骤配置了 required_objects）
        if step.required_objects:
            object_ok = self._check_object_condition(step, objects)
            if not object_ok:
                return False

        return True

    def _check_hand_condition(self, step: SOPStep, hands: List[HandResult]) -> bool:
        """检查手部条件：至少一只手满足 区域 + 手势"""
        if not hands:
            return False
        for hand in hands:
            # 区域匹配
            zone_ok = (hand.current_zone == step.target_zone)
            if not zone_ok:
                continue
            # 手势匹配（UNKNOWN 表示不限手势，仅区域匹配即可）
            if step.required_gesture == GestureType.UNKNOWN:
                return True
            if hand.gesture == step.required_gesture:
                return True
        return False

    def _check_object_condition(
        self,
        step: SOPStep,
        objects: List[ObjectDetection],
    ) -> bool:
        """检查物体条件：所有 required_objects 都满足"""
        for req in step.required_objects:
            matched = [o for o in objects if _class_matches(o.class_name, req.class_name)]
            if req.target_zone:
                matched = [o for o in matched if o.current_zone == req.target_zone]
            if len(matched) < req.min_count:
                return False
        return True

    # ---------- 完成检查 ----------
    def _check_completion(self):
        if self._current_index >= len(self._steps):
            self._all_done = True
            logger.info("所有工序步骤已完成")

    # ---------- 状态摘要 ----------
    def get_summary(self) -> dict:
        """获取步骤执行摘要（用于报告）"""
        completed = sum(1 for s in self._states if s.status == StepStatus.COMPLETED)
        skipped = sum(1 for s in self._states if s.status in (StepStatus.SKIPPED, StepStatus.UNAUTHORIZED_SKIP))
        errored = sum(1 for s in self._states if s.status in (StepStatus.TIMEOUT, StepStatus.ERROR))
        total = len(self._states)
        return {
            "total": total,
            "completed": completed,
            "skipped": skipped,
            "errored": errored,
            "pass_rate": (completed / total * 100) if total > 0 else 0,
        }
