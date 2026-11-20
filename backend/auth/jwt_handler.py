"""
JWT 认证处理
- 生成和验证 JWT Token
- 密码哈希与验证
"""

import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import bcrypt

logger = logging.getLogger(__name__)

# JWT 配置
_user_secret = os.getenv("JWT_SECRET", "")
if not _user_secret:
    _user_secret = secrets.token_urlsafe(32)
    logger.warning("JWT_SECRET 未设置，已生成随机密钥。生产环境请通过环境变量显式配置！")
JWT_SECRET = _user_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
ACCESS_TOKEN_COOKIE = "ai_sop_access_token"


def hash_password(password: str) -> str:
    """哈希密码（bcrypt）"""
    pw_bytes = password.encode("utf-8")
    # bcrypt 限制72字节，截断处理
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    pw_bytes = plain.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    hashed_bytes = hashed.encode("utf-8")
    return bcrypt.checkpw(pw_bytes, hashed_bytes)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT Token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=JWT_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT Token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token 已过期")
        return None
    except jwt.PyJWTError as e:
        logger.warning("Token 解码失败: %s", e)
        return None
