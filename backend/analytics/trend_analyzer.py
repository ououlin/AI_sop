"""趋势与结构分析：每日序列、瓶颈步骤、SOP 维度对比。"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from analytics.metrics_calculator import (
    DEFECT_STEP_STATUSES,
    FAILED_RUN_STATUSES,
    load_records,
    load_steps,
)


def daily_series(
    db: Session,
    days: int = 14,
    tenant_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> List[dict]:
    """按自然日聚合：执行数、完成数、失败数、FPY、平均节拍。"""
    now = now or datetime.now()
    since = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    records = load_records(db, since, tenant_id)

    buckets = {}
    for offset in range(days):
        day = (since + timedelta(days=offset)).date().isoformat()
        buckets[day] = {
            "date": day,
            "runs": 0,
            "completed": 0,
            "failed": 0,
            "duration_sum": 0.0,
            "duration_count": 0,
        }

    for record in records:
        start = record.start_time or since
        key = start.date().isoformat()
        bucket = buckets.get(key)
        if bucket is None:
            continue
        bucket["runs"] += 1
        if record.status == "completed":
            bucket["completed"] += 1
            if record.total_duration is not None:
                bucket["duration_sum"] += float(record.total_duration)
                bucket["duration_count"] += 1
        elif record.status in FAILED_RUN_STATUSES:
            bucket["failed"] += 1

    series = []
    for day in sorted(buckets):
        bucket = buckets[day]
        series.append(
            {
                "date": day,
                "runs": bucket["runs"],
                "completed": bucket["completed"],
                "failed": bucket["failed"],
                "fpy": round(bucket["completed"] / bucket["runs"], 4)
                if bucket["runs"]
                else None,
                "avg_duration_sec": round(
                    bucket["duration_sum"] / bucket["duration_count"], 2
                )
                if bucket["duration_count"]
                else None,
            }
        )
    return series


def step_ranking(
    db: Session,
    days: int = 30,
    tenant_id: Optional[int] = None,
    limit: int = 10,
    now: Optional[datetime] = None,
) -> List[dict]:
    """按平均耗时排名的瓶颈步骤。"""
    now = now or datetime.now()
    since = now - timedelta(days=days)
    steps = load_steps(db, since, tenant_id)

    stats = {}
    for step in steps:
        item = stats.setdefault(
            step.step_name or "未命名",
            {
                "step_name": step.step_name or "未命名",
                "count": 0,
                "duration_sum": 0.0,
                "duration_count": 0,
                "max_duration_sec": 0.0,
                "defects": 0,
            },
        )
        item["count"] += 1
        if step.duration is not None:
            item["duration_sum"] += float(step.duration)
            item["duration_count"] += 1
            item["max_duration_sec"] = max(item["max_duration_sec"], float(step.duration))
        if step.status in DEFECT_STEP_STATUSES:
            item["defects"] += 1

    rows = []
    for item in stats.values():
        rows.append(
            {
                "step_name": item["step_name"],
                "count": item["count"],
                "avg_duration_sec": round(item["duration_sum"] / item["duration_count"], 2)
                if item["duration_count"]
                else None,
                "max_duration_sec": round(item["max_duration_sec"], 2),
                "defects": item["defects"],
                "defect_rate": round(item["defects"] / item["count"], 4)
                if item["count"]
                else None,
            }
        )

    rows.sort(key=lambda row: (row["avg_duration_sec"] or 0.0), reverse=True)
    return rows[:limit]


def sop_breakdown(
    db: Session,
    days: int = 30,
    tenant_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> List[dict]:
    """按 SOP 维度对比执行量、通过率与节拍。"""
    now = now or datetime.now()
    since = now - timedelta(days=days)
    records = load_records(db, since, tenant_id)

    stats = {}
    for record in records:
        name = record.sop_name or "未命名"
        item = stats.setdefault(
            name,
            {
                "sop_name": name,
                "runs": 0,
                "completed": 0,
                "duration_sum": 0.0,
                "duration_count": 0,
            },
        )
        item["runs"] += 1
        if record.status == "completed":
            item["completed"] += 1
            if record.total_duration is not None:
                item["duration_sum"] += float(record.total_duration)
                item["duration_count"] += 1

    rows = []
    for item in stats.values():
        rows.append(
            {
                "sop_name": item["sop_name"],
                "runs": item["runs"],
                "completed": item["completed"],
                "fpy": round(item["completed"] / item["runs"], 4) if item["runs"] else None,
                "avg_duration_sec": round(item["duration_sum"] / item["duration_count"], 2)
                if item["duration_count"]
                else None,
            }
        )
    rows.sort(key=lambda row: row["runs"], reverse=True)
    return rows
