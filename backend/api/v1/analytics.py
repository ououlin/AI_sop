"""数据分析 API（BI 指标）。

口径说明见 ``analytics/metrics_calculator.py`` 模块文档：
无标准工时数据时，OEE 采用「覆盖时长 × 相对标杆节拍 × 一次通过率」的近似算法。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from analytics import metrics_calculator, trend_analyzer
from auth.dependencies import require_permission
from database import get_db

router = APIRouter(prefix="/analytics", tags=["数据分析"])


@router.get(
    "/overview",
    dependencies=[Depends(require_permission("record:view:all"))],
)
async def overview(
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """OEE / FPY / CT / DPMO / MTBF 汇总"""
    return metrics_calculator.compute_overview(db, days=days)


@router.get(
    "/trend",
    dependencies=[Depends(require_permission("record:view:all"))],
)
async def trend(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """按自然日的执行量与通过率趋势"""
    return {"days": days, "series": trend_analyzer.daily_series(db, days=days)}


@router.get(
    "/steps",
    dependencies=[Depends(require_permission("record:view:all"))],
)
async def steps(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """瓶颈步骤排行（按平均耗时）"""
    return {"steps": trend_analyzer.step_ranking(db, days=days, limit=limit)}


@router.get(
    "/sops",
    dependencies=[Depends(require_permission("record:view:all"))],
)
async def sops(
    days: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
):
    """SOP 维度对比"""
    return {"sops": trend_analyzer.sop_breakdown(db, days=days)}
