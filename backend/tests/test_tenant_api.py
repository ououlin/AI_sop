"""阶段 1：租户管理与平台管理员权限测试。"""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.tenant import router as tenant_router
from database import Base
from database import get_db as real_get_db
from db_models import TenantDB, UserDB
from middleware.tenant_middleware import TenantMiddleware
from saas import tenant_manager


class TenantManagerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        db.add(TenantDB(id=1, code="default", name="默认租户"))
        db.commit()
        db.close()

    def test_create_tenant_creates_admin_user(self):
        db = self.Session()
        try:
            tenant = tenant_manager.create_tenant(db, "ACME-1", "Acme 制造", "boss", "secret123")
            self.assertEqual(tenant.code, "acme-1")
            self.assertEqual(tenant.status, "active")
            admin = db.query(UserDB).filter(UserDB.tenant_id == tenant.id).one()
            self.assertEqual(admin.username, "boss")
            self.assertEqual(admin.role, "admin")
        finally:
            db.close()

    def test_duplicate_code_conflicts(self):
        db = self.Session()
        try:
            tenant_manager.create_tenant(db, "acme", "Acme", "boss", "secret123")
            with self.assertRaises(tenant_manager.TenantConflict):
                tenant_manager.create_tenant(db, "acme", "Acme 2", "boss2", "secret123")
        finally:
            db.close()

    def test_invalid_inputs_rejected(self):
        db = self.Session()
        try:
            for bad_code in ("1acme", "ac me", "a", "x" * 40):
                with self.assertRaises(tenant_manager.TenantError):
                    tenant_manager.create_tenant(db, bad_code, "bad", "boss", "secret123")
            with self.assertRaises(tenant_manager.TenantError):
                tenant_manager.create_tenant(db, "okcode", "ok", "boss", "123")
        finally:
            db.close()

    def test_default_tenant_cannot_be_suspended(self):
        db = self.Session()
        try:
            with self.assertRaises(tenant_manager.TenantError):
                tenant_manager.update_tenant(db, 1, status="suspended")
            with self.assertRaises(tenant_manager.TenantError):
                tenant_manager.update_tenant(db, 1, status="deleted")
        finally:
            db.close()


class TenantApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        db.add(TenantDB(id=1, code="default", name="默认租户"))
        db.commit()
        db.close()

        self.client = TestClient(self._build_app("platform_admin"))

    def _build_app(self, role):
        app = FastAPI()
        app.state.session_factory = self.Session
        session_factory = self.Session

        def override_get_db():
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[real_get_db] = override_get_db

        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = {"sub": "root", "role": role, "tid": 1}
                return await call_next(request)

        app.add_middleware(TenantMiddleware)
        app.add_middleware(FakeAuth)
        app.include_router(tenant_router, prefix="/api/v1")
        return app

    def _payload(self, code="acme"):
        return {
            "code": code,
            "name": "Acme 制造",
            "admin_username": "boss",
            "admin_password": "secret123",
        }

    def test_platform_admin_creates_lists_and_patches(self):
        created = self.client.post("/api/v1/tenants", json=self._payload())
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertEqual(body["code"], "acme")
        self.assertEqual(body["user_count"], 1)
        tenant_id = body["id"]

        listed = self.client.get("/api/v1/tenants")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([tenant["code"] for tenant in listed.json()], ["default", "acme"])

        detail = self.client.get("/api/v1/tenants/{}".format(tenant_id))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["name"], "Acme 制造")

        patched = self.client.patch(
            "/api/v1/tenants/{}".format(tenant_id), json={"status": "suspended", "plan_code": "standard"}
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["status"], "suspended")
        self.assertEqual(patched.json()["plan_code"], "standard")

    def test_duplicate_code_returns_409(self):
        self.assertEqual(self.client.post("/api/v1/tenants", json=self._payload()).status_code, 200)
        again = self.client.post("/api/v1/tenants", json=self._payload())
        self.assertEqual(again.status_code, 409, again.text)

    def test_tenant_admin_is_forbidden(self):
        client = TestClient(self._build_app("admin"))
        self.assertEqual(client.get("/api/v1/tenants").status_code, 403)
        self.assertEqual(client.post("/api/v1/tenants", json=self._payload()).status_code, 403)

    def test_unknown_tenant_returns_404(self):
        self.assertEqual(self.client.get("/api/v1/tenants/999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
