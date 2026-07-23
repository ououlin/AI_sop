from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from db_models import ExecutionRecord, StepRecord


class RecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, status: Optional[str] = None, sop_name: Optional[str] = None,
                start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
                page: int = 1, limit: int = 20) -> Tuple[List[ExecutionRecord], int]:
        query = self.db.query(ExecutionRecord)

        if status:
            query = query.filter(ExecutionRecord.status == status)
        if sop_name:
            query = query.filter(ExecutionRecord.sop_name.like(f"%{sop_name}%"))
        if start_time:
            query = query.filter(ExecutionRecord.start_time >= start_time)
        if end_time:
            query = query.filter(ExecutionRecord.start_time <= end_time)

        total = query.count()
        records = query.order_by(ExecutionRecord.start_time.desc()) \
            .offset((page - 1) * limit) \
            .limit(limit) \
            .all()

        return records, total

    def get_by_id(self, record_id: int) -> Optional[ExecutionRecord]:
        return self.db.query(ExecutionRecord).filter(ExecutionRecord.id == record_id).first()

    def create(self, sop_id: int, sop_name: str) -> ExecutionRecord:
        record = ExecutionRecord(
            sop_id=sop_id,
            sop_name=sop_name,
            start_time=datetime.now(),
            status="in_progress",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_status(self, record_id: int, status: str, end_time: Optional[datetime] = None,
                      total_duration: Optional[float] = None) -> bool:
        record = self.get_by_id(record_id)
        if record:
            record.status = status
            if end_time:
                record.end_time = end_time
            if total_duration:
                record.total_duration = total_duration
            self.db.commit()
            self.db.refresh(record)
            return True
        return False

    def add_step(self, record_id: int, step_name: str, step_index: int,
                 status: str, duration: float = 0, completed_at: Optional[datetime] = None) -> StepRecord:
        step = StepRecord(
            record_id=record_id,
            step_name=step_name,
            step_index=step_index,
            status=status,
            duration=duration,
            completed_at=completed_at,
        )
        self.db.add(step)
        self.db.commit()
        self.db.refresh(step)
        return step

    def update_step(self, step_id: int, status: str, duration: Optional[float] = None,
                    completed_at: Optional[datetime] = None) -> bool:
        step = self.db.query(StepRecord).filter(StepRecord.id == step_id).first()
        if step:
            step.status = status
            if duration:
                step.duration = duration
            if completed_at:
                step.completed_at = completed_at
            self.db.commit()
            self.db.refresh(step)
            return True
        return False