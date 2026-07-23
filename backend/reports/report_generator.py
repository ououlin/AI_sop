"""
质检报告生成器
- 从执行记录生成结构化报告数据
- 支持 PDF / Excel 导出
"""

import logging
from typing import List, Optional, Dict
from datetime import datetime

from models import StepStatus

logger = logging.getLogger(__name__)


def generate_report_data(
    sop_name: str,
    steps_state: List[dict],
    alarms: List[dict],
    operator: str = "",
    order_no: str = "",
    product_model: str = "",
) -> dict:
    """
    生成报告数据结构
    :param steps_state: 步骤运行时状态列表（dict格式）
    :param alarms: 告警历史列表
    """
    total = len(steps_state)
    completed = sum(1 for s in steps_state if s.get("status") == StepStatus.COMPLETED.value)
    skipped = sum(1 for s in steps_state if s.get("status") in (
        StepStatus.SKIPPED.value, StepStatus.UNAUTHORIZED_SKIP.value
    ))
    errored = sum(1 for s in steps_state if s.get("status") in (
        StepStatus.TIMEOUT.value, StepStatus.ERROR.value
    ))

    pass_rate = (completed / total * 100) if total > 0 else 0
    conclusion = "合格" if pass_rate == 100 else ("需关注" if pass_rate >= 75 else "不合格")

    # 计算每步用时
    step_records = []
    for s in steps_state:
        started = s.get("started_at")
        completed_at = s.get("completed_at")
        duration = ""
        if started and completed_at:
            try:
                t1 = datetime.fromisoformat(started) if isinstance(started, str) else started
                t2 = datetime.fromisoformat(completed_at) if isinstance(completed_at, str) else completed_at
                delta = (t2 - t1).total_seconds()
                duration = f"{delta:.1f}s"
            except Exception:
                duration = "-"

        status_label = {
            StepStatus.COMPLETED.value: "合格",
            StepStatus.SKIPPED.value: "已跳过",
            StepStatus.UNAUTHORIZED_SKIP.value: "未授权跳过",
            StepStatus.TIMEOUT.value: "超时",
            StepStatus.ERROR.value: "错误",
            StepStatus.PENDING.value: "未执行",
            StepStatus.IN_PROGRESS.value: "进行中",
        }.get(s.get("status", ""), "未知")

        def _fmt_dt(v):
            if not v:
                return ""
            if isinstance(v, str):
                return v[:19]
            if isinstance(v, datetime):
                return v.strftime("%Y-%m-%d %H:%M:%S")
            return str(v)

        step_records.append({
            "step_id": s.get("step_id", ""),
            "name": s.get("name", ""),
            "started_at": _fmt_dt(started),
            "completed_at": _fmt_dt(completed_at),
            "duration": duration,
            "status": status_label,
        })

    def _fmt_alarm_dt(v):
        if not v:
            return ""
        if isinstance(v, str):
            return v[:19]
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M:%S")
        return str(v)

    return {
        "report_id": f"RPT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sop_name": sop_name,
        "order_no": order_no,
        "product_model": product_model,
        "operator": operator,
        "summary": {
            "total": total,
            "completed": completed,
            "skipped": skipped,
            "errored": errored,
            "pass_rate": round(pass_rate, 1),
            "conclusion": conclusion,
        },
        "steps": step_records,
        "alarms": [
            {
                "level": a.get("level", ""),
                "type": a.get("type", ""),
                "message": a.get("message", ""),
                "timestamp": _fmt_alarm_dt(a.get("timestamp")),
            }
            for a in alarms
        ],
    }


def render_text_report(data: dict) -> str:
    """渲染为纯文本报告（用于调试和简单导出）"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"质检报告  {data['report_id']}")
    lines.append("=" * 60)
    lines.append(f"生成时间: {data['generated_at']}")
    lines.append(f"SOP名称:  {data['sop_name']}")
    lines.append(f"订单号:   {data.get('order_no', '-')}")
    lines.append(f"产品型号: {data.get('product_model', '-')}")
    lines.append(f"操作员:   {data.get('operator', '-')}")
    lines.append("")

    lines.append("工序执行记录:")
    lines.append(f"{'步骤':<6}{'名称':<16}{'开始':<22}{'结束':<22}{'用时':<10}{'结果':<10}")
    lines.append("-" * 86)
    for s in data["steps"]:
        lines.append(
            f"{s['step_id']:<6}{s['name']:<16}{s['started_at']:<22}{s['completed_at']:<22}"
            f"{s['duration']:<10}{s['status']:<10}"
        )
    lines.append("")

    if data["alarms"]:
        lines.append("异常记录:")
        for a in data["alarms"]:
            lines.append(f"  [{a['level']}] {a['timestamp']} {a['message']}")
        lines.append("")

    s = data["summary"]
    lines.append(f"合格率: {s['pass_rate']}% ({s['completed']}/{s['total']})")
    lines.append(f"结论:   {s['conclusion']}")

    return "\n".join(lines)
