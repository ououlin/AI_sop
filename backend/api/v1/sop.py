import json
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import DEFAULT_SOP_FILE, WORK_ZONES, ZONE_COLORS, ZONES_FILE, DATA_DIR
from dependencies import get_sop_manager
from database import get_db
from repositories.sop_repo import SOPRepository
from models import SOPDefinition, SOPStep, GestureType
from sop_manager import SOPManager

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


@router.get("/zones")
async def get_zones():
    """获取当前工作区域定义（归一化坐标）"""
    zones = _load_zones()
    colors = {k: list(v) for k, v in ZONE_COLORS.items()}
    return {"zones": zones, "colors": colors}


@router.post("/zones")
async def update_zones(req: ZonesUpdate):
    """更新工作区域定义（管理员操作，持久化到 data/zones.json）"""
    if not req.zones:
        raise HTTPException(status_code=400, detail="至少需要一个区域")
    zones = {}
    for z in req.zones:
        if z.x_min >= z.x_max or z.y_min >= z.y_max:
            raise HTTPException(
                status_code=400,
                detail=f"区域 {z.name} 坐标非法：x_min/y_min 须小于 x_max/y_max",
            )
        zones[z.name] = [z.x_min, z.y_min, z.x_max, z.y_max]
    _save_zones(zones)
    return {"ok": True, "zones": zones}


@router.get("/list")
async def list_sops(sop_manager: SOPManager = Depends(get_sop_manager)):
    return {"sops": sop_manager.list_available_sops()}


@router.post("/load")
async def load_sop(
    filename: str = DEFAULT_SOP_FILE,
    sop_manager: SOPManager = Depends(get_sop_manager),
):
    if not sop_manager.load(filename):
        raise HTTPException(status_code=404, detail=f"SOP文件不存在: {filename}")
    return {"status": "loaded", "sop_name": sop_manager.definition.sop_name}


@router.post("/start")
async def start_sop(sop_manager: SOPManager = Depends(get_sop_manager)):
    sop_manager.resume()
    return {"status": "running"}


@router.post("/pause")
async def pause_sop(sop_manager: SOPManager = Depends(get_sop_manager)):
    sop_manager.pause()
    return {"status": "paused"}


@router.post("/reset")
async def reset_sop(sop_manager: SOPManager = Depends(get_sop_manager)):
    sop_manager.reset()
    return {"status": "reset"}


@router.post("/skip")
async def skip_step(sop_manager: SOPManager = Depends(get_sop_manager)):
    sop_manager.skip_current()
    return {"status": "skipped"}


@router.get("/status")
async def get_status(sop_manager: SOPManager = Depends(get_sop_manager)):
    if not sop_manager.is_loaded():
        return {"loaded": False}
    rec = sop_manager.recognizer
    return {
        "loaded": True,
        "sop_name": sop_manager.definition.sop_name,
        "paused": sop_manager.paused,
        "current_step_index": rec.current_index,
        "all_done": rec.all_done,
        "steps": [s.model_dump() for s in rec.states],
    }


@router.get("/db/list")
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


@router.get("/db/{sop_id}")
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


@router.post("/db/save")
async def save_sop_db(
    name: str,
    steps_json: str,
    version: str = "1.0",
    db: Session = Depends(get_db),
):
    repo = SOPRepository(db)
    try:
        json.loads(steps_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="steps_json 格式错误")
    sop = repo.create(name, steps_json, version)
    return {"id": sop.id, "name": sop.name, "version": sop.version}


@router.delete("/db/{sop_id}")
async def delete_sop_db(sop_id: int, db: Session = Depends(get_db)):
    repo = SOPRepository(db)
    if not repo.delete(sop_id):
        raise HTTPException(status_code=404, detail="SOP不存在")
    return {"status": "deleted"}
