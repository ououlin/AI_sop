"""Alembic 运行环境。

连接串复用应用配置（``DATABASE_URL`` 环境变量），模型元数据直接取自
``db_models``，保证迁移与应用模型不会漂移。

PostgreSQL 且设置了 ``TENANT_SCHEMA`` 时，迁移前会创建并进入该 schema。
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database import TENANT_SCHEMA, Base, engine  # noqa: E402
import db_models  # noqa: F401,E402  确保模型注册到 Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection=None):
    kwargs = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
    }
    if connection is not None:
        kwargs["connection"] = connection
    else:
        kwargs["url"] = str(engine.url)
        kwargs["literal_binds"] = True
        kwargs["dialect_opts"] = {"paramstyle": "named"}
    context.configure(**kwargs)


def run_migrations_offline():
    _configure()
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        if TENANT_SCHEMA and connection.dialect.name == "postgresql":
            connection.exec_driver_sql(
                'CREATE SCHEMA IF NOT EXISTS "{}"'.format(TENANT_SCHEMA)
            )
            connection.exec_driver_sql('SET search_path TO "{}"'.format(TENANT_SCHEMA))
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
