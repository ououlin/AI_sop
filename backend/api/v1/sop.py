import json
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import (
    DEFAULT_SOP_FILE, WORK_ZONES, ZONE_COLORS, ZONES_FILE, DATA_DIR,
    update_work_zones,
)
from dependencies import get_alarm_manager, get_execution_tracker, get_sop_manager
from database import get_db
from repositories.sop_repo import SOPRepository
from models import SOPDefinition, SOPStep
from sop_manager import SOPManager
from alarm.alarm_manager import AlarmManager
from execution_tracker import ExecutionTracker
from auth.dependencies import require_permission

router = APIRouter(prefix="/sop", tags=["SOP"])


# ============ 区域标定（产线工程师自助配置）============

class ZoneConfig(BaseModel):
    """单个工作区域定义（归一化坐标 0~1）"""
    name: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class ZonesUpdate(BaseModel):
    """区域批量更新请求体"""
    zones: List[ZoneConfig]


class SopSaveRequest(BaseModel):
    name: str
    version: str = "1.0"
    standard_cycle_sec: float = 0.0
    steps: List[SOPStep]
    activate: bool = True


def _load_zones() -> dict:
    """从持久化文件加载区域，回退到 config 默认值"""
    if ZONES_FILE.exists():
        try:
            with open(ZONES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {k: list(v) for k, v in WORK_ZONES.items()}


def _save_zones(zones: dict) -> None:
    """持久化区域定义到 data/zones.json"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(zones, f, ensure_ascii=False, indent=2)


@router.get("/zones", dependencies=[Depends(require_permission("sop:view"))])
async def get_zones():
    """获取当前工作区域定义（归一化坐标）"""
    zones = _load_zones()
    colors = {k: list(v) for k, v in ZONE_COLORS.items()}
    return {"zones": zones, "colors": colors}


@router.post("/zones", dependencies=[Depends(require_permission("camera:manage"))])
async def update_zones(req: ZonesUpdate):
    """更新工作区域定义（管理员操作，持久化到 data/zones.json）"""
    if not req.zones:
        raise HTTPException(status_code=400, detail="至少需要一个区域")
    zones = {}
    for z in req.zones:
        values = (z.x_min, z.y_min, z.x_max, z.y_max)
        if not all(0 <= value <= 1 for value in values):
            raise HTTPException(status_code=400, detail=f"区域 {z.name} 坐标须在0到1之间")
        if z.x_min >= z.x_max or z.y_min >= z.y_max:
            raise HTTPException(
                status_code=400,
                detail=f"区域 {z.name} 坐标非法：x_min/y_min 须小于 x_max/y_max",
            )
        zones[z.name] = [z.x_min, z.y_min, z.x_max, z.y_max]
    _save_zones(zones)
    update_work_zones(zones)
    return {"ok": True, "zones": zones}


@router.get("/list", dependencies=[Depends(require_permission("sop:view"))])
async def list_sops(
    sop_manager: SOPManager = Depends(get_sop_manager),
    db: Session = Depends(get_db),
):
    entries = [
        {"key": f"file:{name}", "name": name, "source": "file"}
        for name in sop_manager.list_available_sops()
    ]
    entries.extend(
        {"key": f"db:{sop.id}", "name": sop.name, "source": "database", "version": sop.version}
        for sop in SOPRepository(db).get_all()
    )
    return {
        "sops": [entry["key"] for entry in entries],
        "entries": entries,
        "current_source": sop_manager.source,
    }


@router.get("/file/{filename}", dependencies=[Depends(require_permission("sop:view"))])
async def get_sop_file(
    filename: str,
    sop_manager: SOPManager = Depends(get_sop_manager),
):
    definition = sop_manager.read_file(filename)
    if definition is None:
        raise HTTPException(status_code=404, detail="SOP文件不存在或格式错误")
    return definition.model_dump(mode="json")


@router.post("/load", dependencies=[Depends(require_permission("sop:execute"))])
async def load_sop(
    source: str = f"file:{DEFAULT_SOP_FILE}",
    sop_manager: SOPManager = Depends(get_sop_manager),
    execution_tracker: ExecutionTracker = Depends(get_execution_tracker),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
    db: Session = Depends(get_db),
):
    source = source if ":" in source else f"file:{source}"
    if source.startswith("db:"):
        try:
            sop_id = int(source.split(":", 1)[1])
        except ValueError:
            raise HTTPException(status_code=400, detail="数据库SOP标识无效")
        sop = SOPRepository(db).get_by_id(sop_id)
        if not sop:
            raise HTTPException(status_code=404, detail="SOP不存在")
        definition = SOPDefinition(
            sop_name=sop.name,
            version=sop.version,
            steps=json.loads(sop.steps_json),
        )
        execution_tracker.interrupt()
        sop_manager.load_definition(definition, source=source)
    elif source.startswith("file:"):
        filename = source.split(":", 1)[1]
        definition = sop_manager.read_file(filename)
        if definition is None:
            raise HTTPException(status_code=404, detail=f"SOP文件不存在或格式错误: {filename}")
        execution_tracker.interrupt()
        sop_manager.load(filename)
    else:
        raise HTTPException(status_code=400, detail="不支持的SOP来源")
    alarm_manager.reset_execution()
    return {
        "status": "loaded",
        "sop_name": sop_manager.definition.sop_name,
        "source": sop_manager.source,
    }


@router.post("/start", dependencies=[Depends(require_permission("sop:execute"))])
async def start_sop(
    sop_manager: SOPManager = Depends(get_sop_manager),
    execution_tracker: ExecutionTracker = Depends(get_execution_tracker),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    if not sop_manager.is_loaded():
        raise HTTPException(status_code=400, detail="未加载SOP")
    if sop_manager.recognizer.all_done:
        raise HTTPException(status_code=409, detail="SOP已完成，请先重置")
    current_step = sop_manager.recognizer.current_index
    states = sop_manager.recognizer.states
    if current_step < len(states) and states[current_step].status.value in {
        "timeout", "error", "unauthorized_skip",
    }:
        raise HTTPException(status_code=409, detail="当前执行已异常结束，请先重置")
    if execution_tracker.active_record_id is None:
        alarm_manager.reset_execution()
        execution_tracker.start(sop_manager)
    sop_manager.resume()
    return {"status": "running", "record_id": execution_tracker.active_record_id}


@router.post("/pause", dependencies=[Depends(require_permission("sop:execute"))])
async def pause_sop(
    sop_manager: SOPManager = Depends(get_sop_manager),
    execution_tracker: ExecutionTracker = Depends(get_execution_tracker),
):
    if not sop_manager.is_loaded():
        raise HTTPException(status_code=400, detail="未加载SOP")
    sop_manager.pause()
    execution_tracker.sync(sop_manager.recognizer)
    return {"status": "paused"}


@router.post("/reset", dependencies=[Depends(require_permission("sop:execute"))])
async def reset_sop(
    sop_manager: SOPManager = Depends(get_sop_manager),
    execution_tracker: ExecutionTracker = Depends(get_execution_tracker),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
):
    execution_tracker.interrupt()
    sop_manager.reset()
    alarm_manager.reset_execution()
    return {"status": "reset"}


@router.post("/skip", dependencies=[Depends(require_permission("sop:skip"))])
async def skip_step(
    sop_manager: SOPManager = Depends(get_sop_manager),
    execution_tracker: ExecutionTracker = Depends(get_execution_tracker),
):
    if not sop_manager.is_loaded() or sop_manager.paused:
        raise HTTPException(status_code=409, detail="SOP未运行，不能跳过步骤")
    sop_manager.skip_current()
    if sop_manager.recognizer:
        execution_tracker.sync(sop_manager.recognizer)
    return {"status": "skipped"}


@router.get("/status", dependencies=[Depends(require_permission("sop:view"))])
async def get_status(sop_manager: SOPManager = Depends(get_sop_manager)):
    if not sop_manager.is_loaded():
        return {"loaded": False}
    rec = sop_manager.recognizer
    return {
        "loaded": True,
        "sop_name": sop_manager.definition.sop_name,
        "source": sop_manager.source,
        "paused": sop_manager.paused,
        "current_step_index": rec.current_index,
        "all_done": rec.all_done,
        "steps": [s.model_dump() for s in rec.states],
    }


@router.get("/db/list", dependencies=[Depends(require_permission("sop:view"))])
async def list_sops_db(db: Session = Depends(get_db)):
    repo = SOPRepository(db)
    sops = repo.get_all()
    return {
        "sops": [
            {
                "id": s.id,
                "name": s.name,
                "version": s.version,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sops
        ]
    }


@router.get("/db/{sop_id}", dependencies=[Depends(require_permission("sop:view"))])
async def get_sop_db(sop_id: int, db: Session = Depends(get_db)):
    repo = SOPRepository(db)
    sop = repo.get_by_id(sop_id)
    if not sop:
        raise HTTPException(status_code=404, detail="SOP不存在")
    return {
        "id": sop.id,
        "name": sop.name,
        "version": sop.version,
        "steps": json.loads(sop.steps_json),
        "created_at": sop.created_at.isoformat(),
        "updated_at": sop.updated_at.isoformat(),
    }


@router.post("/db/save", dependencies=[Depends(require_permission("sop:edit"))])
async def save_sop_db(
    req: SopSaveRequest,
    sop_manager: SOPManager = Depends(get_sop_manager),
    execution_tracker: ExecutionTracker = Depends(get_execution_tracker),
    alarm_manager: AlarmManager = Depends(get_alarm_manager),
    db: Session = Depends(get_db),
):
    definition = SOPDefinition(
        sop_name=req.name,
        version=req.version,
        standard_cycle_sec=req.standard_cycle_sec,
        steps=req.steps,
    )
    repo = SOPRepository(db)
    steps_json = json.dumps(
        [step.model_dump(mode="json") for step in definition.steps],
        ensure_ascii=False,
    )
    sop = repo.create(
        req.name,
        steps_json,
        req.version,
        standard_cycle_sec=req.standard_cycle_sec or None,
    )
    source = f"db:{sop.id}"
    if req.activate:
        execution_tracker.interrupt()
        sop_manager.load_definition(definition, source=source)
        alarm_manager.reset_execution()
    return {"id": sop.id, "name": sop.name, "version": sop.version, "source": source}


@router.delete("/db/{sop_id}", dependencies=[Depends(require_permission("sop:delete"))])
async def delete_sop_db(
    sop_id: int,
    sop_manager: SOPManager = Depends(get_sop_manager),
    db: Session = Depends(get_db),
):
    if sop_manager.source == f"db:{sop_id}":
        raise HTTPException(status_code=409, detail="不能删除当前已加载的SOP")
    repo = SOPRepository(db)
    if not repo.delete(sop_id):
        raise HTTPException(status_code=404, detail="SOP不存在")
    return {"status": "deleted"}
