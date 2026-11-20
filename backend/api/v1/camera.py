from fastapi import APIRouter, HTTPException, Depends
import cv2
from pydantic import BaseModel, Field

from dependencies import get_camera
from camera_service import CameraService
from auth.dependencies import require_permission

router = APIRouter(prefix="/camera", tags=["摄像头"])


class CameraSwitchRequest(BaseModel):
    index: int = Field(ge=0, le=20)


@router.get("/list", dependencies=[Depends(require_permission("camera:view"))])
async def list_cameras():
    cameras = []
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cameras.append({"index": i, "resolution": f"{w}x{h}"})
            cap.release()
    return {"cameras": cameras}


@router.post("/switch", dependencies=[Depends(require_permission("camera:manage"))])
async def switch_camera(req: CameraSwitchRequest, camera: CameraService = Depends(get_camera)):
    camera.stop()
    camera.config.index = req.index
    success = camera.start()
    if success:
        return {"status": "success", "index": req.index}
    raise HTTPException(status_code=400, detail=f"无法打开摄像头 {req.index}")
