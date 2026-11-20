"""Persist one execution record for each SOP run."""

import json
import logging
import threading
from datetime import datetime
from typing import List, Optional

from database import SessionLocal
from tenancy.context import DEFAULT_TENANT_ID, get_tenant_id
from models import StepStatus
from repositories.record_repo import RecordRepository
from repositories.sop_repo import SOPRepository

logger = logging.getLogger(__name__)


class ExecutionTracker:
    def __init__(self):
        self._lock = threading.RLock()
        self._tenant_id: int = DEFAULT_TENANT_ID
        self._record_id: Optional[int] = None
        self._started_at: Optional[datetime] = None
        self._step_record_ids: List[int] = []
        self._last_statuses: List[str] = []

    @property
    def active_record_id(self) -> Optional[int]:
        with self._lock:
            return self._record_id

    def start(self, sop_manager) -> Optional[int]:
        if not sop_manager.is_loaded():
            return None
        with self._lock:
            if self._record_id is not None:
                return self._record_id

            definition = sop_manager.definition
            self._tenant_id = get_tenant_id()
            db = SessionLocal()
            try:
                sop_repo = SOPRepository(db, self._tenant_id)
                source = sop_manager.source or ""
                sop = None
                if source.startswith("db:"):
                    try:
                        sop = sop_repo.get_by_id(int(source.split(":", 1)[1]))
                    except ValueError:
                        sop = None
                sop = sop or sop_repo.get_by_name(definition.sop_name)
                if sop is None:
                    sop = sop_repo.create(
                        definition.sop_name,
                        json.dumps(
                            [step.model_dump(mode="json") for step in definition.steps],
                            ensure_ascii=False,
                        ),
                        definition.version,
                    )
                record_repo = RecordRepository(db, self._tenant_id)
                record = record_repo.create(sop.id, definition.sop_name)
                step_ids = []
                statuses = []
                for index, state in enumerate(sop_manager.recognizer.states):
                    step_record = record_repo.add_step(
                        record.id,
                        state.name,
                        index,
                        state.status.value,
                    )
                    step_ids.append(step_record.id)
                    statuses.append(state.status.value)
                self._record_id = record.id
                self._started_at = record.start_time
                self._step_record_ids = step_ids
                self._last_statuses = statuses
                logger.info("执行记录已开始: record_id=%d", record.id)
                return record.id
            finally:
                db.close()

    def sync(self, recognizer) -> None:
        with self._lock:
            if self._record_id is None:
                return

            db = SessionLocal()
            try:
                repo = RecordRepository(db, self._tenant_id)
                for index, state in enumerate(recognizer.states):
                    status_value = state.status.value
                    if index >= len(self._last_statuses) or status_value == self._last_statuses[index]:
                        continue
                    repo.update_step(
                        self._step_record_ids[index],
                        status_value,
                        duration=state.matched_duration,
                        completed_at=state.completed_at,
                    )
                    self._last_statuses[index] = status_value

                if recognizer.all_done:
                    self._finalize_locked(repo, "completed")
                    return

                current_index = recognizer.current_index
                if current_index < len(recognizer.states):
                    current_status = recognizer.states[current_index].status
                    if current_status in {
                        StepStatus.TIMEOUT,
                        StepStatus.ERROR,
                        StepStatus.UNAUTHORIZED_SKIP,
                    }:
                        self._finalize_locked(repo, "error")
            finally:
                db.close()

    def interrupt(self) -> None:
        with self._lock:
            if self._record_id is None:
                return
            db = SessionLocal()
            try:
                self._finalize_locked(RecordRepository(db, self._tenant_id), "interrupted")
            finally:
                db.close()

    def _finalize_locked(self, repo: RecordRepository, status: str) -> None:
        if self._record_id is None:
            return
        ended_at = datetime.now()
        duration = (
            (ended_at - self._started_at).total_seconds()
            if self._started_at is not None
            else 0.0
        )
        record_id = self._record_id
        repo.update_status(record_id, status, ended_at, duration)
        self._record_id = None
        self._started_at = None
        self._step_record_ids = []
        self._last_statuses = []
        logger.info("执行记录已结束: record_id=%d, status=%s", record_id, status)
