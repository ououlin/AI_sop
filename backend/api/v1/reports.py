"""
报告导出 API
- 生成并导出质检报告（JSON / 文本）
- 支持从当前执行状态或历史记录生成
"""

import csv
import io
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from dependencies import get_sop_manager, get_alarm_manager
from reports.report_generator import generate_report_data, render_text_report
from reports.pdf_renderer import render_pdf_report
from reports.excel_renderer import render_excel_report
from sop_manager import SOPManager
from alarm.alarm_manager import AlarmManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    operator: str = ""
    order_no: str = ""
    product_model: str = ""


def _get_report_data(
    req: GenerateReportRequest,
    sop_manager: SOPManager,
    alarm_manager: AlarmManager,
) -> dict:
    """从当前执行状态构建报告数据（三个端点共用）"""
    if not sop_manager.is_loaded():
        raise HTTPException(status_code=400, detail="未加载SOP")

    rec = sop_manager.recognizer
    steps_state = [s.model_dump() for s in rec.states]
    alarms = [a.model_dump() for a in alarm_manager.history]

    return generate_report_data(
        sop_name=sop_manager.definition.sop_name,
        steps_state=steps_state,
        alarms=alarms,
        operator=req.operator,
        order_no=req.order_no,
        product_model=req.product_model,
    )


@router.post("/generate")
async def generate_report(
    req: GenerateReportRequest,
    sop_manager: SOPManager = Depends(get_sop_manager),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    """从当前执行状态生成报告（JSON格式）"""
    return _get_report_data(req, sop_manager, alarm_manager)


@router.post("/export/text", response_class=PlainTextResponse)
async def export_text_report(
    req: GenerateReportRequest,
    sop_manager: SOPManager = Depends(get_sop_manager),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    """导出文本格式报告"""
    data = _get_report_data(req, sop_manager, alarm_manager)
    text = render_text_report(data)
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return PlainTextResponse(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/export/csv")
async def export_csv_report(
    req: GenerateReportRequest,
    sop_manager: SOPManager = Depends(get_sop_manager),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    """导出CSV格式报告"""
    data = _get_report_data(req, sop_manager, alarm_manager)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["步骤ID", "步骤名称", "开始时间", "结束时间", "用时", "结果"])
    for s in data["steps"]:
        writer.writerow([
            s["step_id"], s["name"], s["started_at"],
            s["completed_at"], s["duration"], s["status"],
        ])
    writer.writerow([])
    writer.writerow(["合格率", f"{data['summary']['pass_rate']}%"])
    writer.writerow(["结论", data["summary"]["conclusion"]])

    csv_content = output.getvalue()
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=f"\ufeff{csv_content}",  # BOM for Excel UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/export/pdf")
async def export_pdf_report(
    req: GenerateReportRequest,
    sop_manager: SOPManager = Depends(get_sop_manager),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    """导出 PDF 格式质检报告（需安装 reportlab）"""
    data = _get_report_data(req, sop_manager, alarm_manager)
    try:
        pdf_bytes = render_pdf_report(data)
    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/export/excel")
async def export_excel_report(
    req: GenerateReportRequest,
    sop_manager: SOPManager = Depends(get_sop_manager),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    """导出 Excel 格式质检报告（需安装 openpyxl）"""
    data = _get_report_data(req, sop_manager, alarm_manager)
    try:
        excel_bytes = render_excel_report(data)
    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/alarms")
async def get_alarms(alarm_manager: AlarmManager = Depends(get_alarm_manager)):
    """获取告警历史"""
    return {
        "active": [a.model_dump() for a in alarm_manager.active_alarms],
        "history": [a.model_dump() for a in alarm_manager.history],
    }


@router.post("/alarms/{alarm_id}/acknowledge")
async def acknowledge_alarm(
    alarm_id: str,
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    """确认告警"""
    if alarm_manager.acknowledge(alarm_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="告警不存在或已确认")


@router.delete("/alarms")
async def clear_alarms(alarm_manager: AlarmManager = Depends(get_alarm_manager)):
    """清除所有活跃告警"""
    alarm_manager.clear_active()
    return {"ok": True}
