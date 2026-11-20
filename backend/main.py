"""
AI SOP 装配线工序识别系统 - 主服务
FastAPI + WebSocket

管线：摄像头采集帧 -> MediaPipe手部检测 -> 步骤识别引擎 -> 编码推送

本模块仅负责应用装配与生命周期：
- 共享服务实例由 dependencies.init_app_state 创建并挂到 app.state
- 处理循环见 pipeline.ProcessingPipeline
- WebSocket 端点见 ws_server.create_ws_router
- 各 API 路由通过 Depends 获取服务实例

接口：
  REST:
    GET  /api/health              健康检查
    GET  /api/sop/list            列出可用SOP
    POST /api/sop/load            加载指定SOP
    POST /api/sop/start           开始/恢复
    POST /api/sop/pause           暂停
    POST /api/sop/reset           重置
    POST /api/sop/skip            跳过当前步骤
    GET  /api/sop/status          获取当前状态
  WebSocket:
    /ws/video                     推送带骨架标注的视频帧(JPEG)
    /ws/status                    推送步骤状态更新(JSON)
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import (
    SERVER_CONFIG, DEFAULT_SOP_FILE,
    ENABLE_LOCAL_AGGREGATION, STATION_REPORT_TO_SELF,
)
from dependencies import init_app_state
from pipeline import ProcessingPipeline
from ws_server import ClientRegistry, create_ws_router
from logging_config import setup_logging
from middleware.error_handler import error_handler
from middleware.auth_middleware import AuthMiddleware
from middleware.tenant_middleware import TenantMiddleware
from database import init_db
import db_models  # noqa: F401 确保ORM模型在init_db前注册到Base.metadata
from api.v1.health import router as health_router
from api.v1.sop import router as sop_router
from api.v1.camera import router as camera_router
from api.v1.video import router as video_router
from api.v1.records import router as records_router
from api.v1.auth import router as auth_router, init_default_users
from db_models import UserDB  # noqa: F401 确保ORM模型在init_db前注册到Base.metadata
from api.v1.reports import router as reports_router
from central.aggregation_server import router as line_router
from agent.station_reporter import StationReporter

setup_logging()
logger = logging.getLogger("ai_sop.main")


# ============ 工位自调用检测 ============
def _is_self_report(central_url: str) -> bool:
    """判断 CENTRAL_SERVER_URL 是否指向本服务（避免 httpx 回环自调用）"""
    parsed = urlparse(central_url)
    central_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if central_port != SERVER_CONFIG.port:
        return False
    host = (parsed.hostname or "").lower()
    self_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    return host in self_hosts or host == SERVER_CONFIG.host.lower()


# ============ 生命周期 ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    logger.info("=" * 60)
    logger.info("AI SOP 系统启动中...")
    logger.info("=" * 60)

    # 1. 创建共享服务实例并挂到 app.state
    init_app_state(app)
    camera = app.state.camera
    detector = app.state.detector
    sop_manager = app.state.sop_manager
    object_detector = app.state.object_detector
    alarm_manager = app.state.alarm_manager

    # 2. 绑定主事件循环到告警管理器（跨线程安全派发通知）
    alarm_manager.bind_loop(asyncio.get_running_loop())

    # 3. 数据库与用户初始化
    init_db()
    logger.info("数据库初始化完成")

    init_default_users()
    logger.info("用户系统初始化完成")

    # 4. 摄像头启动
    if not camera.start():
        logger.error("摄像头启动失败！系统仍将运行，但无视频流。")

    # 5. 加载默认SOP
    if not sop_manager.load(DEFAULT_SOP_FILE):
        logger.warning("默认SOP加载失败，请通过API加载。")

    logger.info("物体检测模式: %s", object_detector.mode)

    # 6. 工位上报（检测自调用，避免 httpx 回环）
    station_reporter: Optional[StationReporter] = None
    central_url = os.getenv("CENTRAL_SERVER_URL", "")
    station_id = os.getenv("STATION_ID", "W-001")
    station_name = os.getenv("STATION_NAME", "工位1")
    if central_url:
        if _is_self_report(central_url) and not STATION_REPORT_TO_SELF:
            logger.info(
                "CENTRAL_SERVER_URL(%s) 指向本机端口 %d，跳过工位上报以避免自调用"
                "（如需强制上报，设置 STATION_REPORT_TO_SELF=true）",
                central_url, SERVER_CONFIG.port,
            )
        else:
            station_reporter = StationReporter(
                station_id=station_id,
                central_url=central_url,
                station_name=station_name,
            )
            await station_reporter.start(sop_manager, alarm_manager, camera)
            logger.info("工位上报已启用，station_id=%s", station_id)
    else:
        logger.info("未配置 CENTRAL_SERVER_URL，跳过工位上报")

    # 7. WebSocket 客户端注册表（已在模块级创建并挂到 app.state，此处仅校验）
    if not hasattr(app.state, "ws_registry") or app.state.ws_registry is None:
        app.state.ws_registry = ClientRegistry()

    # 8. 启动后台处理循环
    pipeline = ProcessingPipeline(app)
    app.state.pipeline = pipeline
    await pipeline.start()
    logger.info("系统就绪，处理循环已启动")

    yield  # --- 运行中 ---

    # --- shutdown ---
    logger.info("系统关闭中...")
    await pipeline.stop()
    app.state.execution_tracker.interrupt()
    if station_reporter:
        await station_reporter.stop()
    detector.close()
    camera.stop()
    logger.info("系统已关闭")


# ============ FastAPI 应用 ============
app = FastAPI(title="AI SOP 装配线工序识别系统", version="1.0.0", lifespan=lifespan)

# CORS（显式允许前端dev server跨域）
_cors_env = os.getenv("CORS_ORIGINS", "")
if _cors_env:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    _cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
app.exception_handler(Exception)(error_handler)

# 租户中间件（内层：读取认证中间件注入的用户，解析请求租户）
app.add_middleware(TenantMiddleware)

# 认证中间件（外层：拦截 /api/v1/ 请求，校验JWT）
app.add_middleware(AuthMiddleware)

# API 版本化路由
app.include_router(health_router, prefix="/api/v1")
app.include_router(sop_router, prefix="/api/v1")
app.include_router(camera_router, prefix="/api/v1")
app.include_router(video_router, prefix="/api/v1")
app.include_router(records_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
# 中央聚合路由（产线看板）：受 ENABLE_LOCAL_AGGREGATION 控制
if ENABLE_LOCAL_AGGREGATION:
    app.include_router(line_router, prefix="/api/v1")
    logger.info("本地聚合路由已启用（产线看板）")
else:
    logger.info("本地聚合路由已禁用，工位须上报到远程 CENTRAL_SERVER_URL")

# WebSocket 路由（客户端集合在 lifespan 中初始化到 app.state.ws_registry）
_ws_registry = ClientRegistry()
app.state.ws_registry = _ws_registry  # lifespan 会再次赋值，此处保证路由注册时可用
app.include_router(create_ws_router(_ws_registry))


# ============ 前端静态文件 ============
_frontend_dist = Path(SERVER_CONFIG.frontend_dist)
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # SPA 回退到 index.html
        index = _frontend_dist / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(status_code=404, detail="前端未构建")
else:
    @app.get("/")
    async def root():
        return HTMLResponse(
            "<h2>AI SOP 后端已运行</h2>"
            "<p>前端尚未构建。请进入 frontend/ 执行 <code>npm run build</code>，"
            "或使用 <code>npm run dev</code> 启动开发服务器后访问其地址。</p>"
            "<p>API文档: <a href='/docs'>/docs</a></p>"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=SERVER_CONFIG.host,
        port=SERVER_CONFIG.port,
        reload=False,
    )
