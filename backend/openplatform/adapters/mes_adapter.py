"""执行记录 → MES 友好的数据结构。

真实 MES 对接（SAP / 用友 / 金蝶）需要各自适配，这里给出通用报文骨架，
后续在 ``adapters/`` 下按厂商扩展字段映射。
"""

from typing import List, Optional


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def execution_to_mes(record, steps: List) -> dict:
    return {
        "source": "ai_sop",
        "schema_version": "1.0",
        "execution": {
            "id": record.id,
            "sop_name": record.sop_name,
            "status": record.status,
            "start_time": _iso(record.start_time),
            "end_time": _iso(record.end_time),
            "cycle_time_sec": record.total_duration,
        },
        "steps": [
            {
                "index": step.step_index,
                "name": step.step_name,
                "status": step.status,
                "duration_sec": step.duration,
                "completed_at": _iso(step.completed_at),
            }
            for step in sorted(steps, key=lambda item: item.step_index or 0)
        ],
        "quality": {
            "defect_steps": sum(
                1 for step in steps if step.status in ("timeout", "error", "unauthorized_skip")
            ),
            "passed": record.status == "completed",
        },
    }
