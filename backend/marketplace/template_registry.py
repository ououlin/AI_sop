"""工序模板与检测模型目录。

模板是只读 JSON 数据，启动时加载并用 ``SOPDefinition`` 校验，
保证「一键应用」不会产生非法 SOP。
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from models import SOPDefinition

DATA_DIR = Path(__file__).resolve().parent
TEMPLATES_FILE = DATA_DIR / "templates.json"
MODELS_FILE = DATA_DIR / "models.json"


class TemplateError(ValueError):
    """模板数据非法。"""


def _read_json(path: Path):
    if not path.is_file():
        raise TemplateError("目录文件不存在: {}".format(path))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TemplateError("目录文件格式错误: {} ({})".format(path.name, exc))


@lru_cache(maxsize=1)
def _load_templates() -> dict:
    items = _read_json(TEMPLATES_FILE)
    if not isinstance(items, list):
        raise TemplateError("templates.json 顶层必须是数组")

    templates = {}
    for item in items:
        template_id = (item.get("template_id") or "").strip()
        if not template_id:
            raise TemplateError("模板缺少 template_id")
        if template_id in templates:
            raise TemplateError("模板 ID 重复: {}".format(template_id))

        sop_raw = item.get("sop") or {}
        try:
            definition = SOPDefinition(**sop_raw)
        except Exception as exc:  # pydantic 校验失败
            raise TemplateError("模板 {} 的 SOP 非法: {}".format(template_id, exc))
        if not definition.steps:
            raise TemplateError("模板 {} 没有任何步骤".format(template_id))

        templates[template_id] = {
            "template_id": template_id,
            "name": item.get("name") or definition.sop_name,
            "industry": item.get("industry") or "通用",
            "difficulty": item.get("difficulty") or "基础",
            "summary": item.get("summary") or "",
            "recommended_objects": list(item.get("recommended_objects") or []),
            "definition": definition,
        }
    return templates


@lru_cache(maxsize=1)
def _load_models() -> tuple:
    items = _read_json(MODELS_FILE)
    if not isinstance(items, list):
        raise TemplateError("models.json 顶层必须是数组")
    return tuple(items)


def _summary(template: dict) -> dict:
    definition = template["definition"]
    return {
        "template_id": template["template_id"],
        "name": template["name"],
        "industry": template["industry"],
        "difficulty": template["difficulty"],
        "summary": template["summary"],
        "recommended_objects": template["recommended_objects"],
        "step_count": len(definition.steps),
        "sop_name": definition.sop_name,
    }


def list_templates(industry: Optional[str] = None) -> List[dict]:
    templates = _load_templates().values()
    if industry:
        templates = [item for item in templates if item["industry"] == industry]
    return [_summary(item) for item in sorted(templates, key=lambda t: (t["industry"], t["template_id"]))]


def list_industries() -> List[str]:
    return sorted({item["industry"] for item in _load_templates().values()})


def get_template(template_id: str) -> Optional[dict]:
    return _load_templates().get(template_id)


def get_definition(template_id: str) -> Optional[SOPDefinition]:
    template = get_template(template_id)
    return template["definition"] if template else None


def describe(template_id: str) -> Optional[dict]:
    """模板详情：摘要 + 完整步骤。"""
    template = get_template(template_id)
    if not template:
        return None
    detail = _summary(template)
    detail["steps"] = [
        step.model_dump(mode="json") for step in template["definition"].steps
    ]
    return detail


def list_models() -> List[dict]:
    return [dict(item) for item in _load_models()]
