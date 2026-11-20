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
from marketplace import custom_template_manager, template_registry, zone_presets
from models import SOPDefinition
from tenancy.context import get_tenant_id
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
    # 应用模板时同时铺开推荐区域划分，免去首次标定
    apply_zones: bool = False
    zone_preset: str = "standard"


class CustomTemplateRequest(BaseModel):
    template_id: Optional[str] = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    industry: str = "自定义"
    difficulty: str = "基础"
    summary: str = ""
    sop: dict


@router.get(
    "/templates",
    response_model=List[TemplateInfo],
    dependencies=[Depends(require_permission("sop:view"))],
)
async def list_templates(
    industry: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """模板列表：内置模板 + 本租户自定义模板"""
    items = template_registry.list_templates(industry)
    items.extend(custom_template_manager.summaries(db, get_tenant_id(), industry))
    return items


@router.post(
    "/templates",
    dependencies=[Depends(require_permission("sop:edit"))],
)
async def create_custom_template(
    req: CustomTemplateRequest,
    db: Session = Depends(get_db),
):
    """保存自定义模板（可视化编辑器的提交入口）"""
    try:
        row = custom_template_manager.create_custom(
            db, get_tenant_id(), req.model_dump()
        )
    except custom_template_manager.TemplateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except custom_template_manager.TemplateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return custom_template_manager.describe(row)


@router.delete(
    "/templates/{template_id}",
    dependencies=[Depends(require_permission("sop:edit"))],
)
async def delete_custom_template(
    template_id: str,
    db: Session = Depends(get_db),
):
    """删除自定义模板（内置模板不可删除）"""
    if template_registry.get_template(template_id) is not None:
        raise HTTPException(status_code=400, detail="内置模板不能删除")
    if not custom_template_manager.delete_custom(
        db, get_tenant_id(), template_id
    ):
        raise HTTPException(status_code=404, detail="模板不存在")
    return {"ok": True}


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetail,
    dependencies=[Depends(require_permission("sop:view"))],
)
async def get_template(template_id: str, db: Session = Depends(get_db)):
    """模板详情（含完整步骤）"""
    custom = custom_template_manager.get_custom(db, get_tenant_id(), template_id)
    if custom is not None:
        return custom_template_manager.describe(custom)
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
    custom = custom_template_manager.get_custom(db, get_tenant_id(), template_id)
    if custom is not None:
        definition = SOPDefinition(**json.loads(custom.sop_json))
    else:
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
    zones_applied = False
    if req.apply_zones:
        try:
            zone_presets.apply_preset(req.zone_preset)
            zones_applied = True
        except zone_presets.ZonePresetError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    sop = SOPRepository(db).create(
        definition.sop_name,
        steps_json,
        definition.version,
        standard_cycle_sec=definition.standard_cycle_sec or None,
    )
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
        "zones_applied": zones_applied,
    }


@router.get(
    "/zone-presets",
    dependencies=[Depends(require_permission("sop:view"))],
)
async def list_zone_presets():
    """可一键铺开的区域预设"""
    return {
        "presets": zone_presets.list_presets(),
        "current": zone_presets.current_zones(),
    }


@router.get(
    "/models",
    response_model=List[ModelInfo],
    dependencies=[Depends(require_permission("sop:view"))],
)
async def list_models():
    """检测模型目录"""
    return template_registry.list_models()
