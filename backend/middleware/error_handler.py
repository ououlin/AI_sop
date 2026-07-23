from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)


async def error_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            {"error": exc.detail, "code": exc.status_code},
            status_code=exc.status_code,
        )
    if isinstance(exc, AppException):
        return JSONResponse(
            {"error": exc.message, "code": exc.code},
            status_code=exc.code,
        )
    logger.exception(f"未处理异常: {exc}")
    return JSONResponse(
        {"error": "服务器内部错误", "code": 500},
        status_code=500,
    )