from fastapi import APIRouter, Depends

from dependencies import get_camera, get_sop_manager
from camera_service import CameraService
from sop_manager import SOPManager

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health(
    camera: CameraService = Depends(get_camera),
    sop_manager: SOPManager = Depends(get_sop_manager),
):
    return {
        "status": "ok",
        "camera_running": camera.is_running(),
        "camera_index": camera.config.index,
        "camera_fps": round(camera.get_fps(), 1),
        "sop_loaded": sop_manager.is_loaded(),
        "sop_name": sop_manager.definition.sop_name if sop_manager.is_loaded() else None,
        "available_sops": sop_manager.list_available_sops(),
    }
