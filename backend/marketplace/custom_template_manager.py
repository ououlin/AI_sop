"""租户自定义工序模板。

内置模板是只读 JSON；自定义模板落库（``custom_templates``），
按租户隔离，可创建、查看、删除，并能像内置模板一样一键应用。
"""

import json
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from db_models import CustomTemplateDB
from models import SOPDefinition


class TemplateValidationError(ValueError):
    """模板内容非法。"""


class TemplateConflict(ValueError):
    """模板标识冲突。"""


def list_custom(db: Session, tenant_id: int) -> List[CustomTemplateDB]:
    return (
        db.query(CustomTemplateDB)
        .filter(CustomTemplateDB.tenant_id == tenant_id)
        .order_by(CustomTemplateDB.id.desc())
        .all()
    )


def get_custom(
    db: Session, tenant_id: int, template_id: str
) -> Optional[CustomTemplateDB]:
    return (
        db.query(CustomTemplateDB)
        .filter(
            CustomTemplateDB.tenant_id == tenant_id,
            CustomTemplateDB.template_id == template_id,
        )
        .first()
    )


def describe(row: CustomTemplateDB) -> dict:
    definition = SOPDefinition(**json.loads(row.sop_json))
    return {
        "template_id": row.template_id,
        "name": row.name,
        "industry": row.industry,
        "difficulty": row.difficulty,
        "summary": row.summary,
        "recommended_objects": [],
        "step_count": len(definition.steps),
        "sop_name": definition.sop_name,
        "source": "custom",
        "steps": [step.model_dump(mode="json") for step in definition.steps],
    }


def summaries(db: Session, tenant_id: int, industry: Optional[str] = None) -> List[dict]:
    rows = list_custom(db, tenant_id)
    result = []
    for row in rows:
        if industry and row.industry != industry:
            continue
        detail = describe(row)
        detail.pop("steps", None)
        result.append(detail)
    return result


def create_custom(db: Session, tenant_id: int, payload: dict) -> CustomTemplateDB:
    name = (payload.get("name") or "").strip()
    if not name:
        raise TemplateValidationError("模板名称不能为空")

    sop_raw = payload.get("sop") or {}
    try:
        definition = SOPDefinition(**sop_raw)
    except Exception as exc:  # pydantic 校验失败
        raise TemplateValidationError("SOP 定义非法: {}".format(exc))
    if not definition.steps:
        raise TemplateValidationError("模板至少需要一个步骤")

    template_id = (payload.get("template_id") or "").strip()
    if template_id:
        if len(template_id) > 50:
            raise TemplateValidationError("模板标识过长（≤50）")
        if get_custom(db, tenant_id, template_id) is not None:
            raise TemplateConflict("模板标识已存在: {}".format(template_id))
    else:
        template_id = "custom-" + uuid.uuid4().hex[:8]

    row = CustomTemplateDB(
        tenant_id=tenant_id,
        template_id=template_id,
        name=name,
        industry=(payload.get("industry") or "自定义").strip(),
        difficulty=(payload.get("difficulty") or "基础").strip(),
        summary=(payload.get("summary") or "").strip()[:200],
        sop_json=json.dumps(sop_raw, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_custom(db: Session, tenant_id: int, template_id: str) -> bool:
    row = get_custom(db, tenant_id, template_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
