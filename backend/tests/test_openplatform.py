"""阶段 M5：开放平台测试（API Key、Webhook、MES 适配、开放接口）。"""

import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.v1.openplatform import open_router
from database import Base
from database import get_db as real_get_db
from db_models import ExecutionRecord, SOPDefinitionDB, StepRecord, TenantDB, WebhookDB
from openplatform import api_gateway
from openplatform.adapters.mes_adapter import execution_to_mes
from openplatform.webhook_manager import WebhookError, WebhookManager


class OpenPlatformBase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        db.add_all([
            TenantDB(id=1, code="default", name="默认租户"),
            TenantDB(id=2, code="acme", name="Acme"),
        ])
        db.commit()
        db.close()

    def _make_record(self, tenant_id=1, status="completed"):
        db = self.Session()
        record = ExecutionRecord(
            tenant_id=tenant_id,
            sop_name="装配工序",
            start_time=datetime(2026, 11, 20, 10, 0, 0),
            end_time=datetime(2026, 11, 20, 10, 1, 0),
            status=status,
            total_duration=60.0,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        db.add(StepRecord(record_id=record.id, step_name="取料", step_index=0,
                          status="completed", duration=12.0))
        db.add(StepRecord(record_id=record.id, step_name="放置", step_index=1,
                          status="timeout", duration=30.0))
        db.commit()
        record_id = record.id
        db.close()
        return record_id


class ApiKeyTests(OpenPlatformBase):
    def test_create_and_authenticate(self):
        db = self.Session()
        try:
            record, raw = api_gateway.create_key(db, 1, "MES 对接", ["read"])
            self.assertTrue(raw.startswith("sk_"))
            self.assertEqual(record.key_prefix, raw[:8])
            self.assertNotEqual(record.key_hash, raw)

            found = api_gateway.authenticate(db, raw)
            self.assertIsNotNone(found)
            self.assertEqual(found.id, record.id)
            self.assertIsNotNone(found.last_used_at)

            self.assertIsNone(api_gateway.authenticate(db, "sk_invalid"))
            self.assertIsNone(api_gateway.authenticate(db, raw[:-1] + "x"))
        finally:
            db.close()

    def test_revoke(self):
        db = self.Session()
        try:
            record, raw = api_gateway.create_key(db, 1, "临时", ["read"])
            self.assertTrue(api_gateway.revoke_key(db, 1, record.id))
            self.assertIsNone(api_gateway.authenticate(db, raw))
            self.assertFalse(api_gateway.revoke_key(db, 1, 9999))
        finally:
            db.close()

    def test_cross_tenant_cannot_revoke(self):
        db = self.Session()
        try:
            record, _ = api_gateway.create_key(db, 1, "A", ["read"])
            self.assertFalse(api_gateway.revoke_key(db, 2, record.id))
        finally:
            db.close()

    def test_invalid_scope(self):
        db = self.Session()
        try:
            with self.assertRaises(api_gateway.ApiKeyError):
                api_gateway.create_key(db, 1, "bad", ["admin"])
        finally:
            db.close()


class WebhookTests(OpenPlatformBase):
    def setUp(self):
        super().setUp()
        self.manager = WebhookManager()

    def test_create_and_list(self):
        db = self.Session()
        try:
            record = self.manager.create_subscription(
                db, 1, "https://example.com/hook", ["execution.completed"], secret="s3cret"
            )
            self.assertTrue(record.active)
            self.assertEqual(len(self.manager.list_subscriptions(db, 1)), 1)
            self.assertEqual(len(self.manager.list_subscriptions(db, 2)), 0)
            self.assertTrue(self.manager.delete_subscription(db, 1, record.id))
            self.assertFalse(self.manager.delete_subscription(db, 1, record.id))
        finally:
            db.close()

    def test_invalid_url_and_event(self):
        db = self.Session()
        try:
            with self.assertRaises(WebhookError):
                self.manager.create_subscription(db, 1, "ftp://example.com")
            with self.assertRaises(WebhookError):
                self.manager.create_subscription(db, 1, "https://example.com", ["unknown.event"])
        finally:
            db.close()

    def test_events_filter(self):
        db = self.Session()
        try:
            record = self.manager.create_subscription(
                db, 1, "https://example.com/hook", ["execution.completed"]
            )
            self.assertEqual(self.manager._events_of(record), ["execution.completed"])
        finally:
            db.close()


class MesAdapterTests(OpenPlatformBase):
    def test_mapping(self):
        record_id = self._make_record()
        db = self.Session()
        try:
            record = db.query(ExecutionRecord).filter_by(id=record_id).one()
            steps = db.query(StepRecord).filter_by(record_id=record_id).all()
            payload = execution_to_mes(record, steps)
            self.assertEqual(payload["source"], "ai_sop")
            self.assertEqual(payload["execution"]["id"], record_id)
            self.assertEqual(len(payload["steps"]), 2)
            self.assertEqual(payload["quality"]["defect_steps"], 1)
            self.assertTrue(payload["quality"]["passed"])
        finally:
            db.close()


class OpenApiTests(OpenPlatformBase):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add(SOPDefinitionDB(tenant_id=1, name="装配工序", version="1.0",
                               steps_json='[{"step_id":1,"name":"取料"}]'))
        db.commit()
        self.record_id = self._make_record()
        _, self.raw_key = api_gateway.create_key(db, 1, "测试 Key", ["read"])
        db.close()

        app = FastAPI()
        app.dependency_overrides[real_get_db] = self._get_db_override()
        app.include_router(open_router, prefix="/api/v1")
        self.client = TestClient(app)

    def _get_db_override(self):
        factory = self.Session

        def override():
            db = factory()
            try:
                yield db
            finally:
                db.close()

        return override

    def test_missing_key_rejected(self):
        self.assertEqual(self.client.get("/api/v1/open/sop").status_code, 401)

    def test_invalid_key_rejected(self):
        response = self.client.get("/api/v1/open/sop", headers={"X-API-Key": "sk_nope"})
        self.assertEqual(response.status_code, 401)

    def test_open_endpoints_with_key(self):
        headers = {"X-API-Key": self.raw_key}

        sops = self.client.get("/api/v1/open/sop", headers=headers)
        self.assertEqual(sops.status_code, 200, sops.text)
        self.assertEqual(sops.json()["sops"][0]["name"], "装配工序")

        executions = self.client.get("/api/v1/open/execution", headers=headers)
        self.assertEqual(executions.status_code, 200, executions.text)
        self.assertEqual(executions.json()["total"], 1)

        detail = self.client.get(
            "/api/v1/open/execution/{}".format(self.record_id), headers=headers
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["execution"]["status"], "completed")

        mes = self.client.get(
            "/api/v1/open/mes/execution/{}".format(self.record_id), headers=headers
        )
        self.assertEqual(mes.status_code, 200)
        self.assertEqual(mes.json()["source"], "ai_sop")

        overview = self.client.get("/api/v1/open/analytics/overview", headers=headers)
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["total_runs"], 1)

    def test_cross_tenant_key_sees_own_data_only(self):
        db = self.Session()
        _, acme_key = api_gateway.create_key(db, 2, "Acme", ["read"])
        db.close()

        response = self.client.get(
            "/api/v1/open/execution", headers={"X-API-Key": acme_key}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
