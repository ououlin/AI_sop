"""运行指标计算。

v1 口径（在缺少标准工时数据时的近似定义，报表页与文档同步说明）：

- **FPY** 一次通过率 = 状态 ``completed`` 的执行数 / 总执行数
- **CT** 节拍 = 已完成执行的平均总时长（秒）
- **OEE** = 可用率 × 表现指数 × 质量指数
  - 可用率 = 窗口内被执行覆盖的时长 / 窗口时长（区间并集，上限 1）
  - 表现指数 = 窗口内最快单次节拍 / 平均节拍（相对标杆，上限 1）
  - 质量指数 = FPY
- **DPMO** = 异常步骤数 × 1e6 / (步骤机会数 × 执行次数)
- **MTBF** = 覆盖时长 / 失败执行次数（无失败时为 null）
"""

import logging
from datetime import datetime, timedelta
from statistics import mean
from typing import List, Optional

from sqlalchemy.orm import Session

from db_models import ExecutionRecord, StepRecord
from tenancy.context import get_tenant_id

logger = logging.getLogger(__name__)

DEFECT_STEP_STATUSES = ("timeout", "error", "unauthorized_skip")
FAILED_RUN_STATUSES = ("error", "interrupted")


def _tenant(tenant_id: Optional[int]) -> int:
    return get_tenant_id() if tenant_id is None else int(tenant_id)


def load_records(
    db: Session, since: datetime, tenant_id: Optional[int] = None
) -> List[ExecutionRecord]:
    return (
        db.query(ExecutionRecord)
        .filter(
            ExecutionRecord.tenant_id == _tenant(tenant_id),
            ExecutionRecord.start_time >= since,
        )
        .order_by(ExecutionRecord.start_time.asc())
        .all()
    )


def load_steps(
    db: Session, since: datetime, tenant_id: Optional[int] = None
) -> List[StepRecord]:
    return (
        db.query(StepRecord)
        .join(ExecutionRecord, StepRecord.record_id == ExecutionRecord.id)
        .filter(
            ExecutionRecord.tenant_id == _tenant(tenant_id),
            ExecutionRecord.start_time >= since,
        )
        .all()
    )


def _merge_intervals(records: List[ExecutionRecord], since: datetime, now: datetime) -> float:
    """执行区间并集时长（秒），用于可用率。"""
    intervals = []
    for record in records:
        start = record.start_time or since
        end = record.end_time or now
        if end < since or start > now:
            continue
        intervals.append((max(start, since), min(end, now)))
    if not intervals:
        return 0.0

    intervals.sort()
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum((end - start).total_seconds() for start, end in merged)


def compute_overview(
    db: Session,
    days: int = 7,
    tenant_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict:
    now = now or datetime.now()
    since = now - timedelta(days=days)

    records = load_records(db, since, tenant_id)
    steps = load_steps(db, since, tenant_id)

    total = len(records)
    completed = [record for record in records if record.status == "completed"]
    failed = [record for record in records if record.status in FAILED_RUN_STATUSES]
    durations = [
        float(record.total_duration)
        for record in completed
        if record.total_duration is not None
    ]
    defect_steps = [step for step in steps if step.status in DEFECT_STEP_STATUSES]

    fpy = round(len(completed) / total, 4) if total else None
    cycle_time = round(mean(durations), 2) if durations else None

    window_seconds = max((now - since).total_seconds(), 1.0)
    covered = _merge_intervals(records, since, now)
    availability = min(1.0, covered / window_seconds)

    average_duration = mean(durations) if durations else 0.0
    performance = min(1.0, min(durations) / average_duration) if average_duration else 0.0

    quality = fpy if fpy is not None else 0.0
    oee = round(availability * performance * quality, 4) if total else None

    opportunities = len(steps)
    dpmo = (
        round(len(defect_steps) * 1_000_000 / (opportunities * total), 1)
        if total and opportunities
        else None
    )

    mtbf = round(covered / len(failed), 1) if failed else None

    return {
        "window_days": days,
        "total_runs": total,
        "completed_runs": len(completed),
        "failed_runs": len(failed),
        "fpy": fpy,
        "cycle_time_sec": cycle_time,
        "oee": oee,
        "oee_detail": {
            "availability": round(availability, 4),
            "performance": round(performance, 4),
            "quality": round(quality, 4),
        },
        "dpmo": dpmo,
        "mtbf_sec": mtbf,
        "defect_steps": len(defect_steps),
        "step_opportunities": opportunities,
        "coverage_sec": round(covered, 1),
    }
