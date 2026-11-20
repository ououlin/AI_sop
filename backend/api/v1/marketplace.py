"""工序模板市场 API。

- 浏览模板（需 ``sop:view``）
- 一键应用模板（需 ``sop:edit``）：写入数据库 SOP，可选立即激活
- 检测模型目录（需 ``sop:view``）
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from alarm.alarm_manager import AlarmManager
from auth.dependencies import require_permission
from database import get_db
from dependencies import get_alarm_manager, get_execution_tracker, get_sop_manager
from execution_tracker import ExecutionTracker
from marketplace import template_registry
from repositories.sop_repo import SOPRepository
from sop_manager import SOPManager

router = APIRouter(prefix="/marketplace", tags=["工序模板"])


class TemplateInfo(BaseModel):
    template_id: str
    name: str
    industry: str
    difficulty: str
    summary: str
    recommended_objects: List[str]
    step_count: int
    sop_name: str


class TemplateDetail(TemplateInfo):
    steps: List[dict]


class ModelInfo(BaseModel):
    model_id: str
    name: str
    task: str
    source: str
    license: str
    size_mb: float
    bundled: bool
    note: str


class ApplyTemplateRequest(BaseModel):
    activate: bool = True
    name: Optional[str] = Field(default=None, max_length=100)


@router.get(
    "/templates",
    response_model=List[TemplateInfo],
    dependencies=[Depends(require_permission("sop:view"))],
)
async def list_templates(industry: Optional[str] = None):
    """模板列表，可按行业过滤"""
    return template_registry.list_templates(industry)


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetail,
    dependencies=[Depends(require_permission("sop:view"))],
)
async def get_template(template_id: str):
    """模板详情（含完整步骤）"""
    detail = template_registry.describe(template_id)
    if not detail:
        raise HTTPException(status_code=404, detail="模板不存在")
    return detail


@router.post(
    "/templates/{template_id}/apply",
    dependencies=[Depends(require_permission("sop:edit"))],
)
async def apply_template(
    template_id: str,
    req: ApplyTemplateRequest,
    sop_manager: SOPManager = Depends(get_sop_manager),
    execution_tracker: ExecutionTracker = Depends(get_execution_tracker),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
    db: Session = Depends(get_db),
):
    """应用模板：写入本租户的数据库 SOP，可选立即激活"""
    template = template_registry.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    definition = template["definition"]
    if req.name:
        definition = definition.model_copy(update={"sop_name": req.name.strip()})

    steps_json = json.dumps(
        [step.model_dump(mode="json") for step in definition.steps],
        ensure_ascii=False,
    )
    sop = SOPRepository(db).create(definition.sop_name, steps_json, definition.version)
    source = "db:{}".format(sop.id)

    if req.activate:
        execution_tracker.interrupt()
        sop_manager.load_definition(definition, source=source)
        alarm_manager.reset_execution()

    return {
        "template_id": template_id,
        "id": sop.id,
        "name": sop.name,
        "version": sop.version,
        "source": source,
        "activated": req.activate,
    }


@router.get(
    "/models",
    response_model=List[ModelInfo],
    dependencies=[Depends(require_permission("sop:view"))],
)
async def list_models():
    """检测模型目录"""
    return template_registry.list_models()
