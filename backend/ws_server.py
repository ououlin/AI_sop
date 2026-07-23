"""
WebSocket 端点与客户端注册表
从 main.py 拆分，负责 /ws/video 与 /ws/status 端点及客户端集合管理。
"""

import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("ai_sop.ws")


class ClientRegistry:
    """WebSocket 客户端集合（视频/状态各一组）"""

    def __init__(self):
        self.video_clients: Set[WebSocket] = set()
        self.status_clients: Set[WebSocket] = set()


def create_ws_router(registry: ClientRegistry) -> APIRouter:
    """创建 WebSocket 路由，绑定到给定客户端注册表"""
    router = APIRouter()

    @router.websocket("/ws/video")
    async def ws_video(ws: WebSocket):
        await ws.accept()
        registry.video_clients.add(ws)
        logger.info("视频客户端已连接，当前: %d", len(registry.video_clients))
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            registry.video_clients.discard(ws)
            logger.info("视频客户端断开，剩余: %d", len(registry.video_clients))

    @router.websocket("/ws/status")
    async def ws_status(ws: WebSocket):
        await ws.accept()
        registry.status_clients.add(ws)
        logger.info("状态客户端已连接，当前: %d", len(registry.status_clients))
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            registry.status_clients.discard(ws)
            logger.info("状态客户端断开，剩余: %d", len(registry.status_clients))

    return router
