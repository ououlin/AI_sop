"""多租户基础能力测试：上下文、数据隔离、老库迁移、中间件。"""

import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware

from database import Base
from db_models import SOPDefinitionDB, TenantDB, UserDB
from middleware.tenant_middleware import TenantMiddleware
from repositories.sop_repo import SOPRepository
from tenancy.context import get_tenant_id, tenant_context

LEGACY_DDL = (
    """
    CREATE TABLE users (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(50) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(20) NOT NULL,
        display_name VARCHAR(100),
        is_active BOOLEAN,
        created_at DATETIME,
        last_login DATETIME
    )
    """,
    """
    CREATE TABLE sop_definitions (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(100) NOT NULL UNIQUE,
        version VARCHAR(20),
        steps_json TEXT NOT NULL,
        created_at DATETIME,
        updated_at DATETIME
    )
    """,
    """
    CREATE TABLE execution_records (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        sop_id INTEGER REFERENCES sop_definitions(id),
        sop_name VARCHAR(100),
        start_time DATETIME,
        end_time DATETIME,
        status VARCHAR(20),
        total_duration FLOAT
    )
    """,
    """
    CREATE TABLE step_records (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER REFERENCES execution_records(id),
        step_name VARCHAR(100),
        step_index INTEGER,
        status VARCHAR(20),
        duration FLOAT,
        completed_at DATETIME
    )
    """,
)


class TenantContextTests(unittest.TestCase):
    def test_default_and_restore(self):
        self.assertEqual(get_tenant_id(), 1)
        with tenant_context(7, "acme"):
            self.assertEqual(get_tenant_id(), 7)
        self.assertEqual(get_tenant_id(), 1)


class RepositoryIsolationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        db = self.session_factory()
        db.add_all([
            TenantDB(id=1, code="default", name="默认租户"),
            TenantDB(id=2, code="acme", name="Acme 制造"),
        ])
        db.commit()
        db.close()

    def test_same_username_allowed_per_tenant(self):
        db = self.session_factory()
        try:
            db.add(UserDB(tenant_id=1, username="admin", password_hash="h", role="admin"))
            db.add(UserDB(tenant_id=2, username="admin", password_hash="h", role="admin"))
            db.commit()
            self.assertEqual(db.query(UserDB).count(), 2)
        finally:
            db.close()

    def test_sop_names_are_isolated_per_tenant(self):
        db = self.session_factory()
        try:
            with tenant_context(1, "default"):
                SOPRepository(db).create("装配工序", "[]")
            with tenant_context(2, "acme"):
                SOPRepository(db).create("装配工序", "[]")
                self.assertEqual([s.tenant_id for s in SOPRepository(db).get_all()], [2])
                self.assertEqual(SOPRepository(db).get_by_name("装配工序").tenant_id, 2)
            with tenant_context(1, "default"):
                self.assertEqual([s.tenant_id for s in SOPRepository(db).get_all()], [1])
            self.assertEqual(db.query(SOPDefinitionDB).count(), 2)
        finally:
            db.close()


class SchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.tmpdir), True)
        self.db_path = self.tmpdir / "legacy.db"
        self.engine = create_engine("sqlite:///{}".format(self.db_path))

    def _create_legacy_database(self):
        with self.engine.begin() as conn:
            for statement in LEGACY_DDL:
                conn.exec_driver_sql(statement)
            conn.exec_driver_sql(
                "INSERT INTO users (id, username, password_hash, role, is_active) "
                "VALUES (1, 'admin', 'h', 'admin', 1)"
            )
            conn.exec_driver_sql(
                "INSERT INTO sop_definitions (id, name, version, steps_json) "
                "VALUES (1, '装配工序', '1.0', '[]')"
            )
            conn.exec_driver_sql(
                "INSERT INTO execution_records (id, sop_id, sop_name, status) "
                "VALUES (1, 1, '装配工序', 'completed')"
            )

    def test_legacy_database_is_upgraded_and_idempotent(self):
        from schema import ensure_schema

        self._create_legacy_database()
        ensure_schema(self.engine)

        with self.engine.begin() as conn:
            self.assertEqual(
                conn.execute(text("SELECT id, code FROM tenants")).fetchall(),
                [(1, "default")],
            )
            for table in ("users", "sop_definitions", "execution_records"):
                self.assertEqual(
                    conn.execute(text("SELECT tenant_id FROM {}".format(table))).scalar(),
                    1,
                    table,
                )

            # 复合唯一生效：另一个租户可以复用同名账号与同名 SOP
            conn.exec_driver_sql(
                "INSERT INTO tenants (id, code, name, status, plan_code) "
                "VALUES (2, 'acme', 'Acme', 'active', 'free')"
            )
            conn.exec_driver_sql(
                "INSERT INTO users (tenant_id, username, password_hash, role, is_active) "
                "VALUES (2, 'admin', 'h', 'admin', 1)"
            )
            conn.exec_driver_sql(
                "INSERT INTO sop_definitions (tenant_id, name, version, steps_json) "
                "VALUES (2, '装配工序', '1.0', '[]')"
            )

        # 幂等：再跑一次不应报错或改动数据
        ensure_schema(self.engine)
        with self.engine.begin() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM users")).scalar(), 2)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM tenants")).scalar(), 2)

    def test_backup_created_for_sqlite(self):
        from schema import ensure_schema

        self._create_legacy_database()
        ensure_schema(self.engine)
        self.assertTrue(Path(str(self.db_path) + ".bak").exists())


class TenantMiddlewareTests(unittest.TestCase):
    def _build_app(self, payload):
        app = FastAPI()

        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = payload
                return await call_next(request)

        app.add_middleware(TenantMiddleware)
        app.add_middleware(FakeAuth)

        @app.get("/probe")
        def probe(request: Request):
            return {"ctx": get_tenant_id(), "state": request.state.tenant_id}

        return app

    def test_context_follows_jwt_payload(self):
        payload = {"sub": "u", "role": "admin", "tid": 3, "tenant": "acme"}
        response = TestClient(self._build_app(payload)).get("/probe")
        self.assertEqual(response.json(), {"ctx": 3, "state": 3})
        self.assertEqual(get_tenant_id(), 1)

    def test_platform_admin_can_override_tenant(self):
        payload = {"sub": "root", "role": "platform_admin", "tid": 1, "tenant": "default"}
        response = TestClient(self._build_app(payload)).get("/probe", headers={"X-Tenant-Id": "5"})
        self.assertEqual(response.json(), {"ctx": 5, "state": 5})

    def test_regular_user_cannot_override_tenant(self):
        payload = {"sub": "u", "role": "admin", "tid": 2, "tenant": "acme"}
        response = TestClient(self._build_app(payload)).get("/probe", headers={"X-Tenant-Id": "5"})
        self.assertEqual(response.json(), {"ctx": 2, "state": 2})


if __name__ == "__main__":
    unittest.main()
