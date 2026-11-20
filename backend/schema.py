"""数据库自举与轻量迁移。

阶段 0 引入租户维度后，老库需要一个可重复执行的升级流程：

1. 建立 ``tenants`` 表并确保默认租户存在（id=1）
2. 业务表补 ``tenant_id`` 列并回填默认租户
3. 把 ``users.username`` / ``sop_definitions.name`` 的全局唯一约束
   改为 ``(tenant_id, xxx)`` 复合唯一

SQLite 不支持直接删除列上的 UNIQUE 约束，这里通过重建表实现；
重建前把 ``.db`` 文件备份为 ``.db.bak``。阶段 3 引入 Alembic 后，
本模块只保留迁移基线。
"""

import logging
import shutil
from pathlib import Path
from typing import Optional, Set

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateTable

from database import Base, engine
import db_models  # noqa: F401  确保 ORM 模型注册到 Base.metadata
from db_models import DEFAULT_TENANT_ID, DEFAULT_TENANT_CODE, DEFAULT_TENANT_NAME

logger = logging.getLogger(__name__)

# 需要租户维度的业务表
_TENANT_TABLES = ("users", "sop_definitions", "execution_records")

# 需要从「全局唯一」改为「租户内唯一」的列
_LEGACY_UNIQUE = {"users": "username", "sop_definitions": "name"}


def _columns(bind: Engine, table: str) -> Set[str]:
    return {column["name"] for column in inspect(bind).get_columns(table)}


def _unique_column_sets(bind: Engine, table: str) -> list:
    """读取表上的唯一约束列组合。

    SQLite 的列级 UNIQUE 会生成 ``sqlite_autoindex_*``，SQLAlchemy 的
    inspector 读不到，这里直接查 PRAGMA。
    """
    if bind.dialect.name == "sqlite":
        result = []
        with bind.connect() as conn:
            index_rows = conn.exec_driver_sql(
                "PRAGMA index_list('{}')".format(table)
            ).fetchall()
            for row in index_rows:
                # row: (seq, name, unique, origin, partial)
                name, unique = row[1], row[2]
                if not unique:
                    continue
                column_rows = conn.exec_driver_sql(
                    "PRAGMA index_info('{}')".format(name)
                ).fetchall()
                result.append([column[2] for column in column_rows])
        return result

    inspector = inspect(bind)
    result = []
    for index in inspector.get_indexes(table):
        if index.get("unique"):
            result.append(list(index.get("column_names") or []))
    for constraint in inspector.get_unique_constraints(table):
        result.append(list(constraint.get("column_names") or []))
    return result


def _has_global_unique(bind: Engine, table: str, column: str) -> bool:
    return [column] in _unique_column_sets(bind, table)


def _needs_upgrade(bind: Engine, table: str) -> bool:
    if not inspect(bind).has_table(table):
        return False
    if "tenant_id" not in _columns(bind, table):
        return True
    column = _LEGACY_UNIQUE.get(table)
    return bool(column and _has_global_unique(bind, table, column))


def _backup_sqlite(bind: Engine) -> None:
    url = str(bind.url)
    if not url.startswith("sqlite:///"):
        return
    path = Path(url[len("sqlite:///"):])
    if not path.exists() or path.stat().st_size == 0:
        return
    backup = path.with_name(path.name + ".bak")
    try:
        shutil.copy2(str(path), str(backup))
        logger.info("迁移前已备份数据库: %s", backup)
    except OSError as exc:  # 备份失败不应阻断启动
        logger.warning("数据库备份失败，继续迁移: %s", exc)


def _ensure_default_tenant(bind: Engine) -> None:
    with bind.begin() as conn:
        exists = conn.execute(
            text("SELECT id FROM tenants WHERE code = :code"),
            {"code": DEFAULT_TENANT_CODE},
        ).fetchone()
        if exists:
            return

        id_taken = conn.execute(
            text("SELECT id FROM tenants WHERE id = :id"),
            {"id": DEFAULT_TENANT_ID},
        ).fetchone()
        if id_taken:
            conn.execute(
                text(
                    "INSERT INTO tenants (code, name, status, plan_code, created_at, updated_at) "
                    "VALUES (:code, :name, 'active', 'free', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"code": DEFAULT_TENANT_CODE, "name": DEFAULT_TENANT_NAME},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO tenants (id, code, name, status, plan_code, created_at, updated_at) "
                    "VALUES (:id, :code, :name, 'active', 'free', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": DEFAULT_TENANT_ID, "code": DEFAULT_TENANT_CODE, "name": DEFAULT_TENANT_NAME},
            )
    logger.info("已确保默认租户存在: %s (id=%d)", DEFAULT_TENANT_CODE, DEFAULT_TENANT_ID)


def _add_tenant_column(bind: Engine, table: str) -> None:
    with bind.begin() as conn:
        conn.exec_driver_sql(
            "ALTER TABLE {table} ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT {default}".format(
                table=table, default=DEFAULT_TENANT_ID
            )
        )
        conn.exec_driver_sql(
            "UPDATE {table} SET tenant_id = {default} WHERE tenant_id IS NULL".format(
                table=table, default=DEFAULT_TENANT_ID
            )
        )
    logger.info("表 %s 已补充 tenant_id 并回填默认租户", table)


def _rebuild_table(bind: Engine, table) -> None:
    """重建表，使唯一约束从全局改为租户维度。"""
    name = table.name
    temp = "{}__new".format(name)

    ddl = str(CreateTable(table).compile(bind=bind)).strip()
    temp_ddl = ddl.replace("CREATE TABLE {} ".format(name), "CREATE TABLE {} ".format(temp), 1)
    if temp_ddl == ddl:
        raise RuntimeError("无法为 {0} 生成临时表 DDL: {1}".format(name, ddl.splitlines()[0]))

    old_columns = _columns(bind, name)
    columns = [column.name for column in table.columns if column.name in old_columns]
    column_list = ", ".join(columns)

    with bind.begin() as conn:
        conn.exec_driver_sql(temp_ddl)
        conn.exec_driver_sql(
            "INSERT INTO {temp} ({columns}) SELECT {columns} FROM {source}".format(
                temp=temp, columns=column_list, source=name
            )
        )
        conn.exec_driver_sql("DROP TABLE {}".format(name))
        conn.exec_driver_sql("ALTER TABLE {} RENAME TO {}".format(temp, name))

    for index in table.indexes:
        index.create(bind=bind, checkfirst=True)

    logger.info("表 %s 已重建，唯一约束改为 (tenant_id, %s)", name, _LEGACY_UNIQUE.get(name, "?"))


def _upgrade_sqlite(bind: Engine) -> None:
    for table in _TENANT_TABLES:
        if not inspect(bind).has_table(table):
            continue
        if "tenant_id" not in _columns(bind, table):
            _add_tenant_column(bind, table)

    for table, column in _LEGACY_UNIQUE.items():
        if inspect(bind).has_table(table) and _has_global_unique(bind, table, column):
            _rebuild_table(bind, Base.metadata.tables[table])


def _upgrade_generic(bind: Engine) -> None:
    for table in _TENANT_TABLES:
        if not inspect(bind).has_table(table):
            continue
        if "tenant_id" not in _columns(bind, table):
            _add_tenant_column(bind, table)

    logger.warning(
        "非 SQLite 数据库未自动重建唯一约束；PostgreSQL 部署请在阶段 4 通过 Alembic 迁移"
    )


def _ensure_subscriptions(bind: Engine) -> None:
    """为没有订阅记录的租户补一条默认套餐订阅。"""
    with bind.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO subscriptions "
                "(tenant_id, plan_code, status, started_at, created_at, updated_at) "
                "SELECT t.id, COALESCE(t.plan_code, 'free'), 'active', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "FROM tenants t "
                "WHERE NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.tenant_id = t.id)"
            )
        )


def ensure_schema(bind: Optional[Engine] = None) -> None:
    """建表 + 幂等迁移，可重复调用。"""
    bind = bind or engine

    pending = {table for table in _TENANT_TABLES if _needs_upgrade(bind, table)}
    if pending:
        _backup_sqlite(bind)
        logger.info("检测到需要升级的表: %s", ", ".join(sorted(pending)))

    Base.metadata.create_all(bind=bind)
    _ensure_default_tenant(bind)
    _ensure_subscriptions(bind)

    if bind.dialect.name == "sqlite":
        _upgrade_sqlite(bind)
    else:
        _upgrade_generic(bind)
