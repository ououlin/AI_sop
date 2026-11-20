"""数据库连接与会话管理。

默认使用 backend/data/ai_sop.db（SQLite）；
通过 ``DATABASE_URL`` 可切换到 PostgreSQL 等其它数据库（阶段 4）。
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DB_DIR = Path(__file__).resolve().parent / "data"
DB_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///{}".format(DB_DIR / "ai_sop.db")

_engine_kwargs = {"echo": False}
if DATABASE_URL.startswith("sqlite"):
    # SQLite 在多线程（识别流水线）下复用连接需要关闭同线程校验
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_pre_ping"] = True

engine = create_engine(DATABASE_URL, **_engine_kwargs)

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
