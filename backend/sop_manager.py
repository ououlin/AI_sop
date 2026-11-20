"""
SOP 管理器
- 从 JSON 文件加载工序定义
- 管理当前执行的 StepRecognizer 实例
- 提供 SOP 切换、重置等接口
"""

import json
import logging
import time
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
        self._source: Optional[str] = None
        self._paused = True
        self._paused_at: Optional[float] = None

    # ---------- 加载 ----------
    def read_file(self, filename: str) -> Optional[SOPDefinition]:
        """Read and validate a definition without changing runtime state."""
        if Path(filename).name != filename or not filename.lower().endswith(".json"):
            return None
        path = SOPS_DIR / filename
        if not path.is_file():
            return None
        try:
            return SOPDefinition(**json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.error("读取 SOP 失败: %s -> %s", path, exc)
            return None

    def load(self, filename: str = DEFAULT_SOP_FILE) -> bool:
        """从 sops/ 目录加载 SOP JSON 文件"""
        definition = self.read_file(filename)
        if definition is not None:
            self.load_definition(definition, source=f"file:{filename}")
            self._current_file = filename
            logger.info(
                "已加载 SOP: %s (共 %d 步)",
                self._definition.sop_name, len(self._definition.steps),
            )
            return True
        return False

    def load_definition(self, definition: SOPDefinition, source: str = "database") -> None:
        """Load an already validated definition into the runtime engine."""
        self._definition = definition
        self._recognizer = StepRecognizer(definition.steps)
        self._current_file = None
        self._source = source
        self._paused = True
        self._paused_at = None

    # ---------- 控制接口 ----------
    def reset(self):
        if self._recognizer:
            self._recognizer.reset()
            self._paused = True
            self._paused_at = None
            logger.info("SOP 已重置")

    def skip_current(self, authorized: bool = True):
        if self._recognizer and not self._paused:
            self._recognizer.skip_current(authorized=authorized)

    def pause(self):
        if self._paused:
            return
        self._paused = True
        self._paused_at = time.monotonic()
        if self._recognizer:
            self._recognizer.suspend_timing()
        logger.info("SOP 已暂停")

    def resume(self):
        if not self._paused:
            return
        if self._paused_at is not None and self._recognizer:
            self._recognizer.resume_timing(time.monotonic() - self._paused_at)
        self._paused = False
        self._paused_at = None
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

    @property
    def source(self) -> Optional[str]:
        return self._source

    def list_available_sops(self) -> List[str]:
        """列出 sops/ 目录下所有可用 SOP 文件"""
        if not SOPS_DIR.exists():
            return []
        return [p.name for p in SOPS_DIR.glob("*.json")]

    def is_loaded(self) -> bool:
        return self._definition is not None and self._recognizer is not None
