from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from repositories.record_repo import RecordRepository

router = APIRouter(prefix="/records", tags=["执行记录"])


@router.get("/")
async def get_records(
    status: Optional[str] = None,
    sop_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    repo = RecordRepository(db)

    start_dt = None
    end_dt = None
    try:
        if start_time:
            start_dt = datetime.fromisoformat(start_time)
        if end_time:
            end_dt = datetime.fromisoformat(end_time)
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式错误，请使用ISO格式")

    records, total = repo.get_all(
        status=status,
        sop_name=sop_name,
        start_time=start_dt,
        end_time=end_dt,
        page=page,
        limit=limit,
    )

    return {
        "records": [
            {
                "id": r.id,
                "sop_name": r.sop_name,
                "start_time": r.start_time.isoformat() if r.start_time else None,
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "status": r.status,
                "total_duration": round(r.total_duration, 2) if r.total_duration else 0,
                "step_count": len(r.steps),
            }
            for r in records
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{record_id}")
async def get_record_detail(record_id: int, db: Session = Depends(get_db)):
    repo = RecordRepository(db)
    record = repo.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    return {
        "id": record.id,
        "sop_name": record.sop_name,
        "start_time": record.start_time.isoformat() if record.start_time else None,
        "end_time": record.end_time.isoformat() if record.end_time else None,
        "status": record.status,
        "total_duration": round(record.total_duration, 2) if record.total_duration else 0,
        "steps": [
            {
                "id": s.id,
                "step_name": s.step_name,
                "step_index": s.step_index,
                "status": s.status,
                "duration": round(s.duration, 2) if s.duration else 0,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in record.steps
        ],
    }