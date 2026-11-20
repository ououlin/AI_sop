"""数据库连接与会话管理。

- 默认使用 backend/data/ai_sop.db（SQLite）
- 通过 ``DATABASE_URL`` 切换 PostgreSQL 等数据库
- PostgreSQL 下可通过 ``TENANT_SCHEMA`` 指定租户 schema，
  连接时设置 ``search_path``，实现「一个部署 = 一个租户」的 schema 级隔离
"""

import os
import re
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DB_DIR = Path(__file__).resolve().parent / "data"
DB_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///{}".format(DB_DIR / "ai_sop.db")

# 租户 schema（仅 PostgreSQL 生效）；留空表示使用数据库默认 schema
TENANT_SCHEMA = os.getenv("TENANT_SCHEMA", "").strip().lower()
_TENANT_SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

_engine_kwargs = {"echo": False}
if DATABASE_URL.startswith("sqlite"):
    # SQLite 在多线程（识别流水线）下复用连接需要关闭同线程校验
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **_engine_kwargs)

if TENANT_SCHEMA and not DATABASE_URL.startswith("sqlite"):
    if not _TENANT_SCHEMA_PATTERN.match(TENANT_SCHEMA):
        raise RuntimeError("TENANT_SCHEMA 非法: {!r}".format(TENANT_SCHEMA))

    @event.listens_for(engine, "connect")
    def _set_tenant_search_path(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute('SET search_path TO "{}"'.format(TENANT_SCHEMA))
        finally:
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """建表并执行幂等迁移（委托 schema 模块，避免循环导入）。"""
    from schema import ensure_schema

    ensure_schema(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
