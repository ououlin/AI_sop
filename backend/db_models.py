"""
SQLAlchemy ORM 模型
用于数据库持久化（租户、SOP定义、执行记录、步骤记录、用户）

多租户约定：
- 所有业务表通过 ``tenant_id`` 关联 ``tenants`` 表
- 唯一约束按租户维度：(tenant_id, username) / (tenant_id, name)
- 迁移逻辑见 ``schema.py``
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base
from tenancy.context import DEFAULT_TENANT_CODE, DEFAULT_TENANT_ID

DEFAULT_TENANT_NAME = "默认租户"


class TenantDB(Base):
    """租户表（SaaS 隔离单元）"""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False, default="")
    status = Column(String(20), nullable=False, default="active")
    plan_code = Column(String(20), nullable=False, default="free")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UserDB(Base):
    """用户表（用户名在租户内唯一）"""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        default=DEFAULT_TENANT_ID,
        server_default=str(DEFAULT_TENANT_ID),
        index=True,
    )
    username = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="operator")
    display_name = Column(String(100), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)


class SubscriptionDB(Base):
    """租户订阅（一个租户一条有效订阅）"""

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id"), nullable=False, unique=True, index=True
    )
    plan_code = Column(String(20), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="active")
    started_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ApiKeyDB(Base):
    """开放平台 API Key（只存摘要）"""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(16), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True)
    scopes = Column(Text, nullable=False, default="[]")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.now)
    last_used_at = Column(DateTime, nullable=True)


class WebhookDB(Base):
    """Webhook 订阅"""

    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    events = Column(Text, nullable=False, default="[]")
    secret = Column(String(100), nullable=False, default="")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.now)


class DeviceDB(Base):
    """设备档案（心跳时更新，持久化）"""

    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "device_id", name="uq_devices_tenant_device"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    device_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False, default="")
    status = Column(String(20), nullable=False, default="idle")
    app_version = Column(String(20), nullable=False, default="")
    model_version = Column(String(50), nullable=False, default="")
    camera_ok = Column(Boolean, nullable=False, default=True)
    fps = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    last_seen = Column(DateTime, nullable=True)
    config_json = Column(Text, nullable=False, default="{}")
    config_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DeviceCommandDB(Base):
    """设备命令（配置下发 / 远程升级）"""

    __tablename__ = "device_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    device_id = Column(String(50), nullable=False, index=True)
    command_id = Column(String(32), nullable=False, unique=True, index=True)
    type = Column(String(20), nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(String(20), nullable=False, default="pending")
    message = Column(String(200), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.now)
    acked_at = Column(DateTime, nullable=True)


class SOPDefinitionDB(Base):
    """SOP 定义表（名称在租户内唯一）"""

    __tablename__ = "sop_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_sop_tenant_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        default=DEFAULT_TENANT_ID,
        server_default=str(DEFAULT_TENANT_ID),
        index=True,
    )
    name = Column(String(100), nullable=False)
    version = Column(String(20), default="1.0")
    steps_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    records = relationship("ExecutionRecord", back_populates="sop")


class ExecutionRecord(Base):
    """执行记录表（按租户隔离）"""

    __tablename__ = "execution_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id"),
        nullable=False,
        default=DEFAULT_TENANT_ID,
        server_default=str(DEFAULT_TENANT_ID),
        index=True,
    )
    sop_id = Column(Integer, ForeignKey("sop_definitions.id"))
    sop_name = Column(String(100))
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String(20))
    total_duration = Column(Float)

    sop = relationship("SOPDefinitionDB", back_populates="records")
    steps = relationship("StepRecord", cascade="all, delete-orphan")


class StepRecord(Base):
    """步骤记录表（随执行记录级联归属租户）"""

    __tablename__ = "step_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(Integer, ForeignKey("execution_records.id"))
    step_name = Column(String(100))
    step_index = Column(Integer)
    status = Column(String(20))
    duration = Column(Float)
    completed_at = Column(DateTime)


__all__ = [
    "DEFAULT_TENANT_CODE",
    "DEFAULT_TENANT_ID",
    "DEFAULT_TENANT_NAME",
    "ApiKeyDB",
    "DeviceCommandDB",
    "DeviceDB",
    "ExecutionRecord",
    "WebhookDB",
    "SOPDefinitionDB",
    "StepRecord",
    "SubscriptionDB",
    "TenantDB",
    "UserDB",
]
