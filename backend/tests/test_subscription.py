"""阶段 2：订阅套餐、配额与到期只读测试。"""

import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.subscription import plans_router
from api.v1.subscription import router as subscription_router
from central.aggregation_server import AggregationServer
from central.aggregation_server import router as line_router
from database import Base
from database import get_db as real_get_db
from db_models import SubscriptionDB, TenantDB
from dependencies import get_aggregation_server
from middleware.tenant_middleware import TenantMiddleware
from saas import subscription


class SubscriptionServiceTests(unittest.TestCase):
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

    def test_plan_catalog(self):
        plans = subscription.list_plans()
        self.assertEqual([plan["code"] for plan in plans], ["free", "standard", "pro", "enterprise"])
        self.assertEqual(subscription.get_plan("PRO")["max_stations"], 20)
        self.assertIsNone(subscription.get_plan("enterprise")["max_stations"])
        with self.assertRaises(subscription.SubscriptionError):
            subscription.get_plan("gold")

    def test_default_subscription_is_free(self):
        db = self.Session()
        try:
            limits = subscription.limits_for(db, 1)
            self.assertEqual(limits["plan_code"], "free")
            self.assertEqual(limits["max_stations"], 1)
            self.assertFalse(limits["expired"])
        finally:
            db.close()

    def test_set_plan_syncs_tenant_row(self):
        db = self.Session()
        try:
            subscription.set_plan(db, 1, "standard")
            tenant = db.query(TenantDB).filter(TenantDB.id == 1).one()
            self.assertEqual(tenant.plan_code, "standard")
            self.assertEqual(db.query(SubscriptionDB).count(), 1)
        finally:
            db.close()

    def test_expiry_detection(self):
        db = self.Session()
        try:
            subscription.set_plan(db, 1, "standard", datetime.now() - timedelta(days=1))
            self.assertTrue(subscription.is_tenant_expired(db, 1))
            subscription.set_plan(db, 1, "standard", datetime.now() + timedelta(days=30))
            self.assertFalse(subscription.is_tenant_expired(db, 1))
        finally:
            db.close()


class _BaseApiTest(unittest.TestCase):
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

    def _get_db_override(self):
        factory = self.Session

        def override():
            db = factory()
            try:
                yield db
            finally:
                db.close()

        return override

    def _auth_middleware(self, role="platform_admin"):
        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = {"sub": "root", "role": role, "tid": 1}
                return await call_next(request)

        return FakeAuth


class SubscriptionApiTests(_BaseApiTest):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.state.session_factory = self.Session
        app.dependency_overrides[real_get_db] = self._get_db_override()
        app.add_middleware(TenantMiddleware)
        app.add_middleware(self._auth_middleware())
        app.include_router(subscription_router, prefix="/api/v1")
        app.include_router(plans_router, prefix="/api/v1")
        self.client = TestClient(app)

    def test_list_plans(self):
        response = self.client.get("/api/v1/plans")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 4)

    def test_get_and_update_subscription(self):
        current = self.client.get("/api/v1/tenants/1/subscription")
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()["plan_code"], "free")

        updated = self.client.put("/api/v1/tenants/1/subscription", json={"plan_code": "pro"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["plan_code"], "pro")
        self.assertEqual(updated.json()["max_stations"], 20)

        unknown = self.client.put("/api/v1/tenants/1/subscription", json={"plan_code": "gold"})
        self.assertEqual(unknown.status_code, 400)

        missing = self.client.get("/api/v1/tenants/99/subscription")
        self.assertEqual(missing.status_code, 404)


class ExpiryMiddlewareTests(_BaseApiTest):
    def _build_app(self):
        app = FastAPI()
        app.state.session_factory = self.Session
        app.add_middleware(TenantMiddleware)
        app.add_middleware(self._auth_middleware("admin"))

        @app.get("/api/v1/probe")
        def probe_get():
            return {"ok": True}

        @app.post("/api/v1/probe")
        def probe_post():
            return {"ok": True}

        return app

    def test_expired_tenant_is_read_only(self):
        db = self.Session()
        subscription.set_plan(db, 1, "standard", datetime.now() - timedelta(days=1))
        db.close()

        client = TestClient(self._build_app())
        self.assertEqual(client.get("/api/v1/probe").status_code, 200)
        blocked = client.post("/api/v1/probe")
        self.assertEqual(blocked.status_code, 402)
        self.assertIn("只读", blocked.json()["error"])

    def test_active_tenant_can_write(self):
        client = TestClient(self._build_app())
        self.assertEqual(client.post("/api/v1/probe").status_code, 200)


class StationQuotaTests(_BaseApiTest):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add(TenantDB(id=2, code="acme", name="Acme"))
        db.commit()
        db.close()

        self.aggregation = AggregationServer()
        app = FastAPI()
        app.dependency_overrides[real_get_db] = self._get_db_override()
        app.dependency_overrides[get_aggregation_server] = lambda: self.aggregation
        app.include_router(line_router, prefix="/api/v1")
        self.client = TestClient(app)

    def _report(self, station_id, tenant_code):
        return self.client.post(
            "/api/v1/station/report",
            json={"station_id": station_id, "station_name": station_id, "tenant_code": tenant_code},
        )

    def test_free_plan_allows_single_station(self):
        first = self._report("W-001", "acme")
        self.assertEqual(first.status_code, 200, first.text)

        second = self._report("W-002", "acme")
        self.assertEqual(second.status_code, 409, second.text)
        self.assertIn("套餐上限", second.json()["detail"])

    def test_other_tenant_has_own_quota(self):
        self.assertEqual(self._report("W-001", "acme").status_code, 200)
        self.assertEqual(self._report("W-101", "default").status_code, 200)
        self.assertEqual(self._report("W-102", "default").status_code, 409)

    def test_unknown_tenant_rejected(self):
        response = self._report("W-001", "nope")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
