import asyncio
import cv2

from fastapi import APIRouter, Response, Depends
from fastapi.responses import StreamingResponse

from dependencies import get_camera
from camera_service import CameraService
from hand_detector import HandDetector
from config import SERVER_CONFIG
from auth.dependencies import require_permission

router = APIRouter(prefix="/video", tags=["视频流"])


@router.get("/mjpeg", dependencies=[Depends(require_permission("video:view"))])
async def mjpeg_video(camera: CameraService = Depends(get_camera)):
    async def generate():
        while True:
            frame = camera.get_frame()
            if frame is None:
                await asyncio.sleep(0.03)
                continue

            HandDetector.draw_zones(frame)
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n"
                   + cv2.imencode(".jpg", frame,
                                   [int(cv2.IMWRITE_JPEG_QUALITY), SERVER_CONFIG.jpeg_quality])[1].tobytes()
                   + b"\r\n")
            await asyncio.sleep(1/30)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/snapshot", dependencies=[Depends(require_permission("video:view"))])
async def snapshot(camera: CameraService = Depends(get_camera)):
    frame = camera.get_frame()
    if frame is None:
        return Response(status_code=503)

    HandDetector.draw_zones(frame)
    ok, buf = cv2.imencode(".jpg", frame,
                            [int(cv2.IMWRITE_JPEG_QUALITY), SERVER_CONFIG.jpeg_quality])
    if not ok:
        return Response(status_code=500)

    return Response(content=buf.tobytes(), media_type="image/jpeg")
