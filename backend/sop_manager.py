"""
SOP 管理器
- 从 JSON 文件加载工序定义
- 管理当前执行的 StepRecognizer 实例
- 提供 SOP 切换、重置等接口
"""

import json
import logging
from pathlib import Path
from typing import Optional, List

from models import SOPDefinition, SOPStep
from step_recognizer import StepRecognizer
from config import SOPS_DIR, DEFAULT_SOP_FILE

logger = logging.getLogger(__name__)


class SOPManager:
    """SOP 工序定义加载与运行时管理"""

    def __init__(self):
        self._definition: Optional[SOPDefinition] = None
        self._recognizer: Optional[StepRecognizer] = None
        self._current_file: Optional[str] = None
        self._paused = False

    # ---------- 加载 ----------
    def load(self, filename: str = DEFAULT_SOP_FILE) -> bool:
        """从 sops/ 目录加载 SOP JSON 文件"""
        path = SOPS_DIR / filename
        if not path.exists():
            logger.error("SOP 文件不存在: %s", path)
            return False

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            self._definition = SOPDefinition(**raw)
            self._current_file = filename
            self._recognizer = StepRecognizer(self._definition.steps)
            self._paused = False
            logger.info(
                "已加载 SOP: %s (共 %d 步)",
                self._definition.sop_name, len(self._definition.steps),
            )
            return True
        except Exception as e:
            logger.error("加载 SOP 失败: %s -> %s", path, e)
            return False

    # ---------- 控制接口 ----------
    def reset(self):
        if self._recognizer:
            self._recognizer.reset()
            self._paused = False
            logger.info("SOP 已重置")

    def skip_current(self):
        if self._recognizer and not self._paused:
            self._recognizer.skip_current()

    def pause(self):
        self._paused = True
        logger.info("SOP 已暂停")

    def resume(self):
        self._paused = False
        logger.info("SOP 已恢复")

    @property
    def paused(self) -> bool:
        return self._paused

    # ---------- 查询 ----------
    @property
    def definition(self) -> Optional[SOPDefinition]:
        return self._definition

    @property
    def recognizer(self) -> Optional[StepRecognizer]:
        return self._recognizer

    @property
    def current_file(self) -> Optional[str]:
        return self._current_file

    def list_available_sops(self) -> List[str]:
        """列出 sops/ 目录下所有可用 SOP 文件"""
        if not SOPS_DIR.exists():
            return []
        return [p.name for p in SOPS_DIR.glob("*.json")]

    def is_loaded(self) -> bool:
        return self._definition is not None and self._recognizer is not None
