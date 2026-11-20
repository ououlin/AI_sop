"""阶段 M2：工序模板市场测试。"""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.marketplace import router as marketplace_router
from database import Base
from database import get_db as real_get_db
from db_models import SOPDefinitionDB, TenantDB
from dependencies import get_alarm_manager, get_execution_tracker, get_sop_manager
from marketplace import template_registry


class RegistryTests(unittest.TestCase):
    def test_templates_load_and_validate(self):
        templates = template_registry.list_templates()
        self.assertGreaterEqual(len(templates), 20)
        self.assertEqual(
            template_registry.list_industries(),
            sorted(["电子装配", "汽车零部件", "食品包装", "医疗器械"]),
        )

        allowed_zones = {"left_area", "center_area", "right_area", "top_area"}
        for summary in templates:
            definition = template_registry.get_definition(summary["template_id"])
            self.assertIsNotNone(definition)
            self.assertGreater(len(definition.steps), 0)
            self.assertEqual(summary["step_count"], len(definition.steps))

            step_ids = [item.step_id for item in definition.steps]
            self.assertEqual(step_ids, sorted(step_ids), summary["template_id"])
            self.assertEqual(len(step_ids), len(set(step_ids)), summary["template_id"])

            for item in definition.steps:
                self.assertIn(item.target_zone, allowed_zones, summary["template_id"])
                self.assertGreater(item.hold_duration_sec, 0, summary["template_id"])
                self.assertGreater(item.timeout_sec, 0, summary["template_id"])
                for requirement in item.required_objects:
                    self.assertTrue(requirement.class_name, summary["template_id"])

        for industry in template_registry.list_industries():
            count = len(template_registry.list_templates(industry))
            self.assertGreaterEqual(count, 4, industry)

    def test_industry_filter(self):
        electronics = template_registry.list_templates("电子装配")
        self.assertGreaterEqual(len(electronics), 2)
        self.assertTrue(all(item["industry"] == "电子装配" for item in electronics))

    def test_unknown_template(self):
        self.assertIsNone(template_registry.get_template("nope"))
        self.assertIsNone(template_registry.describe("nope"))

    def test_model_catalog(self):
        models = template_registry.list_models()
        self.assertGreaterEqual(len(models), 3)
        self.assertIn("yolov8n", [item["model_id"] for item in models])


class _FakeSopManager:
    def __init__(self):
        self.definition = None
        self.source = None

    def load_definition(self, definition, source="database"):
        self.definition = definition
        self.source = source


class _FakeTracker:
    def interrupt(self):
        pass


class _FakeAlarm:
    def reset_execution(self):
        pass


class MarketplaceApiTests(unittest.TestCase):
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

        self.sop_manager = _FakeSopManager()
        app = FastAPI()
        app.state.session_factory = self.Session
        app.dependency_overrides[real_get_db] = self._get_db_override()
        app.dependency_overrides[get_sop_manager] = lambda: self.sop_manager
        app.dependency_overrides[get_execution_tracker] = lambda: _FakeTracker()
        app.dependency_overrides[get_alarm_manager] = lambda: _FakeAlarm()

        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = {"sub": "admin", "role": "admin", "tid": 1}
                return await call_next(request)

        app.add_middleware(FakeAuth)
        app.include_router(marketplace_router, prefix="/api/v1")
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

    def test_list_and_detail(self):
        listed = self.client.get("/api/v1/marketplace/templates")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertGreaterEqual(len(listed.json()), 6)

        detail = self.client.get("/api/v1/marketplace/templates/electronics-pcb-assembly")
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(body["industry"], "电子装配")
        self.assertEqual(len(body["steps"]), body["step_count"])
        self.assertEqual(body["steps"][0]["target_zone"], "left_area")

    def test_unknown_template_404(self):
        self.assertEqual(
            self.client.get("/api/v1/marketplace/templates/nope").status_code, 404
        )
        self.assertEqual(
            self.client.post("/api/v1/marketplace/templates/nope/apply", json={}).status_code,
            404,
        )

    def test_apply_writes_sop_and_activates(self):
        applied = self.client.post(
            "/api/v1/marketplace/templates/automotive-bolt-tightening/apply",
            json={"activate": True},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        body = applied.json()
        self.assertEqual(body["name"], "螺栓拧紧")
        self.assertTrue(body["source"].startswith("db:"))
        self.assertTrue(body["activated"])
        self.assertEqual(self.sop_manager.source, body["source"])
        self.assertEqual(self.sop_manager.definition.sop_name, "螺栓拧紧")

        db = self.Session()
        try:
            row = db.query(SOPDefinitionDB).filter(SOPDefinitionDB.id == body["id"]).one()
            self.assertEqual(row.tenant_id, 1)
            self.assertIn("螺栓拧紧", row.name)
        finally:
            db.close()

    def test_apply_with_custom_name_and_no_activation(self):
        applied = self.client.post(
            "/api/v1/marketplace/templates/food-filling-sealing/apply",
            json={"activate": False, "name": "一号线灌装"},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        body = applied.json()
        self.assertEqual(body["name"], "一号线灌装")
        self.assertFalse(body["activated"])
        self.assertIsNone(self.sop_manager.source)

    def test_apply_twice_updates_same_record(self):
        first = self.client.post(
            "/api/v1/marketplace/templates/medical-sterile-packaging/apply", json={}
        ).json()
        second = self.client.post(
            "/api/v1/marketplace/templates/medical-sterile-packaging/apply", json={}
        ).json()
        self.assertEqual(first["id"], second["id"])

    def test_models_catalog(self):
        response = self.client.get("/api/v1/marketplace/models")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreaterEqual(len(response.json()), 3)


if __name__ == "__main__":
    unittest.main()
