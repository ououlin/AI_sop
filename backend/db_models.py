"""
SQLAlchemy ORM 模型
用于数据库持久化（SOP定义、执行记录、步骤记录、用户）
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship

from database import Base


class UserDB(Base):
    """用户表"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="operator")
    display_name = Column(String(100), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)


class SOPDefinitionDB(Base):
    __tablename__ = "sop_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    version = Column(String(20), default="1.0")
    steps_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    records = relationship("ExecutionRecord", back_populates="sop")


class ExecutionRecord(Base):
    __tablename__ = "execution_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sop_id = Column(Integer, ForeignKey("sop_definitions.id"))
    sop_name = Column(String(100))
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String(20))
    total_duration = Column(Float)

    sop = relationship("SOPDefinitionDB", back_populates="records")
    steps = relationship("StepRecord", cascade="all, delete-orphan")


class StepRecord(Base):
    __tablename__ = "step_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(Integer, ForeignKey("execution_records.id"))
    step_name = Column(String(100))
    step_index = Column(Integer)
    status = Column(String(20))
    duration = Column(Float)
    completed_at = Column(DateTime)
