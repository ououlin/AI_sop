"""
Excel 质检报告渲染器
使用 openpyxl 生成 .xlsx 报告
在 openpyxl 不可用时抛出友好错误，由路由层捕获返回 503
"""

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def render_excel_report(data: dict) -> bytes:
    """
    将报告数据结构渲染为 Excel 二进制内容
    :param data: generate_report_data 产出的 dict
    :return: .xlsx 文件字节
    :raises ImportError: openpyxl 未安装
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError as e:
        raise ImportError(
            "openpyxl 未安装，无法生成 Excel 报告。请在 backend/ 目录执行 "
            "`pip install openpyxl` 或 `pip install -r requirements.txt`。"
        ) from e

    wb = Workbook()

    # ---- 工作表1：概览 ----
    ws = wb.active
    ws.title = "质检报告"

    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="4472C4")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    title_font = Font(bold=True, size=14)
    center = Alignment(horizontal="center", vertical="center")

    ws["A1"] = f"质检报告  {data['report_id']}"
    ws["A1"].font = title_font
    ws.merge_cells("A1:F1")

    meta_rows = [
        ("生成时间", data["generated_at"]),
        ("SOP 名称", data["sop_name"]),
        ("订单号", data.get("order_no", "-") or "-"),
        ("产品型号", data.get("product_model", "-") or "-"),
        ("操作员", data.get("operator", "-") or "-"),
    ]
    for i, (k, v) in enumerate(meta_rows, start=3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, size=10)
        ws.cell(row=i, column=2, value=v)

    # 汇总表
    summary_start = 9
    ws.cell(row=summary_start, column=1, value="质检汇总").font = title_font
    s = data["summary"]
    summary_header = ["总步骤", "合格", "跳过", "异常", "合格率", "结论"]
    for col, h in enumerate(summary_header, start=1):
        c = ws.cell(row=summary_start + 1, column=col, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = center
        c.border = border
    summary_values = [
        s["total"], s["completed"], s["skipped"],
        s["errored"], f"{s['pass_rate']}%", s["conclusion"],
    ]
    for col, v in enumerate(summary_values, start=1):
        c = ws.cell(row=summary_start + 2, column=col, value=v)
        c.alignment = center
        c.border = border
    conclusion_cell = ws.cell(row=summary_start + 2, column=6)
    fill_color = (
        "C6EFCE" if s["conclusion"] == "合格"
        else "FFEB9C" if s["conclusion"] == "需关注"
        else "FFC7CE"
    )
    conclusion_cell.fill = PatternFill("solid", fgColor=fill_color)

    # 步骤明细
    step_start = summary_start + 4
    ws.cell(row=step_start, column=1, value="工序执行记录").font = title_font
    step_header = ["步骤ID", "步骤名称", "开始时间", "结束时间", "用时", "结果"]
    for col, h in enumerate(step_header, start=1):
        c = ws.cell(row=step_start + 1, column=col, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = center
        c.border = border
    for ridx, st in enumerate(data["steps"], start=step_start + 2):
        for col, key in enumerate(
            ["step_id", "name", "started_at", "completed_at", "duration", "status"],
            start=1,
        ):
            c = ws.cell(row=ridx, column=col, value=st[key])
            c.border = border
            c.alignment = center if col != 2 else Alignment(vertical="center")

    # 列宽
    widths = [10, 24, 22, 22, 12, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ---- 工作表2：异常记录 ----
    if data["alarms"]:
        ws2 = wb.create_sheet("异常记录")
        alarm_header = ["级别", "时间", "类型", "描述"]
        for col, h in enumerate(alarm_header, start=1):
            c = ws2.cell(row=1, column=col, value=h)
            c.fill = header_fill
            c.font = header_font
            c.alignment = center
            c.border = border
        for ridx, a in enumerate(data["alarms"], start=2):
            for col, key in enumerate(
                ["level", "timestamp", "type", "message"], start=1,
            ):
                c = ws2.cell(row=ridx, column=col, value=a[key])
                c.border = border
                c.alignment = Alignment(vertical="center", wrap_text=True)
        for i, w in enumerate([10, 22, 18, 60], start=1):
            ws2.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
