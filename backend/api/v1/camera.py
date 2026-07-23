from fastapi import APIRouter, HTTPException, Depends
import cv2

from dependencies import get_camera
from camera_service import CameraService

router = APIRouter(prefix="/camera", tags=["摄像头"])


@router.get("/list")
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


@router.post("/switch")
async def switch_camera(index: int, camera: CameraService = Depends(get_camera)):
    camera.stop()
    camera.config.index = index
    success = camera.start()
    if success:
        return {"status": "success", "index": index}
    raise HTTPException(status_code=400, detail=f"无法打开摄像头 {index}")
