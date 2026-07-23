"""
PDF 质检报告渲染器
使用 reportlab 生成结构化 PDF 报告（含中文 CID 字体支持）
在 reportlab 不可用时抛出友好错误，由路由层捕获返回 503
"""

import logging

logger = logging.getLogger(__name__)


def render_pdf_report(data: dict) -> bytes:
    """
    将报告数据结构渲染为 PDF 二进制内容
    :param data: generate_report_data 产出的 dict
    :return: PDF 文件字节
    :raises ImportError: reportlab 未安装
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
    except ImportError as e:
        raise ImportError(
            "reportlab 未安装，无法生成 PDF 报告。请在 backend/ 目录执行 "
            "`pip install reportlab` 或 `pip install -r requirements.txt`。"
        ) from e

    # 注册中文 CID 字体（reportlab 内置，跨平台无需系统字体文件）
    _zh_font = "Helvetica"
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase import pdfmetrics
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _zh_font = "STSong-Light"
    except Exception as e:
        logger.warning("中文字体注册失败，回退 Helvetica: %s", e)

    from io import BytesIO
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ZhTitle", parent=styles["Title"],
        fontName=_zh_font, fontSize=18, spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "ZhH2", parent=styles["Heading2"],
        fontName=_zh_font, fontSize=13, spaceBefore=8, spaceAfter=4,
    )
    normal_style = ParagraphStyle(
        "ZhNormal", parent=styles["Normal"],
        fontName=_zh_font, fontSize=9.5, leading=14,
    )

    story = []
    story.append(Paragraph(f"质检报告  {data['report_id']}", title_style))
    story.append(Spacer(1, 4 * mm))

    meta = [
        ["生成时间", data["generated_at"]],
        ["SOP 名称", data["sop_name"]],
        ["订单号", data.get("order_no", "-") or "-"],
        ["产品型号", data.get("product_model", "-") or "-"],
        ["操作员", data.get("operator", "-") or "-"],
    ]
    meta_tbl = Table(meta, colWidths=[30 * mm, 120 * mm])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _zh_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666666")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 4 * mm))

    # 汇总
    s = data["summary"]
    conclusion_color = (
        colors.green if s["conclusion"] == "合格"
        else colors.orange if s["conclusion"] == "需关注"
        else colors.red
    )
    summary = [
        ["总步骤", "合格", "跳过", "异常", "合格率", "结论"],
        [
            str(s["total"]), str(s["completed"]), str(s["skipped"]),
            str(s["errored"]), f"{s['pass_rate']}%", s["conclusion"],
        ],
    ]
    summary_tbl = Table(summary, colWidths=[25 * mm] * 5 + [25 * mm])
    summary_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _zh_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TEXTCOLOR", (5, 1), (5, 1), conclusion_color),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 4 * mm))

    # 步骤明细
    story.append(Paragraph("工序执行记录", h2_style))
    step_header = ["步骤", "名称", "开始", "结束", "用时", "结果"]
    step_rows = [step_header]
    for st in data["steps"]:
        step_rows.append([
            str(st["step_id"]), st["name"], st["started_at"],
            st["completed_at"], st["duration"], st["status"],
        ])
    step_tbl = Table(step_rows, colWidths=[12 * mm, 30 * mm, 32 * mm, 32 * mm, 18 * mm, 26 * mm])
    step_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _zh_font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(step_tbl)

    # 异常记录
    if data["alarms"]:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("异常记录", h2_style))
        alarm_rows = [["级别", "时间", "类型", "描述"]]
        for a in data["alarms"]:
            alarm_rows.append([
                a["level"], a["timestamp"], a["type"], a["message"],
            ])
        alarm_tbl = Table(
            alarm_rows,
            colWidths=[18 * mm, 32 * mm, 25 * mm, 75 * mm],
        )
        alarm_tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), _zh_font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ffe8e8")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(alarm_tbl)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        f"本报告由 AI SOP 系统于 {data['generated_at']} 自动生成",
        ParagraphStyle("Footer", parent=normal_style, fontSize=8,
                       textColor=colors.grey, alignment=2),
    ))

    doc.build(story)
    return buf.getvalue()
