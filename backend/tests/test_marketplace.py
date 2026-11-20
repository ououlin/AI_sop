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

    def test_create_custom_template_and_apply(self):
        payload = {
            "template_id": "custom-demo",
            "name": "自定义装配",
            "industry": "电子装配",
            "summary": "自建模板",
            "sop": {
                "sop_name": "自定义装配",
                "steps": [
                    {
                        "step_id": 1,
                        "name": "取料",
                        "target_zone": "left_area",
                        "required_gesture": "pinch",
                        "hold_duration_sec": 1.0,
                        "timeout_sec": 60,
                    }
                ],
            },
        }
        created = self.client.post("/api/v1/marketplace/templates", json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["source"], "custom")

        listed = self.client.get("/api/v1/marketplace/templates").json()
        self.assertIn("custom-demo", [item["template_id"] for item in listed])

        applied = self.client.post(
            "/api/v1/marketplace/templates/custom-demo/apply", json={"activate": False}
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["name"], "自定义装配")

        deleted = self.client.delete("/api/v1/marketplace/templates/custom-demo")
        self.assertEqual(deleted.status_code, 200, deleted.text)

    def test_duplicate_custom_template_conflict(self):
        payload = {
            "template_id": "custom-dup",
            "name": "重复模板",
            "sop": {
                "sop_name": "重复模板",
                "steps": [
                    {
                        "step_id": 1,
                        "name": "取料",
                        "target_zone": "left_area",
                        "required_gesture": "pinch",
                        "hold_duration_sec": 1.0,
                        "timeout_sec": 60,
                    }
                ],
            },
        }
        self.assertEqual(
            self.client.post("/api/v1/marketplace/templates", json=payload).status_code, 200
        )
        self.assertEqual(
            self.client.post("/api/v1/marketplace/templates", json=payload).status_code, 409
        )

    def test_invalid_custom_template_rejected(self):
        created = self.client.post(
            "/api/v1/marketplace/templates",
            json={"name": "空步骤", "sop": {"sop_name": "空步骤", "steps": []}},
        )
        self.assertEqual(created.status_code, 400)

    def test_builtin_template_cannot_be_deleted(self):
        response = self.client.delete(
            "/api/v1/marketplace/templates/electronics-pcb-assembly"
        )
        self.assertEqual(response.status_code, 400)




class ZonePresetTests(unittest.TestCase):
    def test_apply_preset_updates_work_zones(self):
        import tempfile
        from pathlib import Path as _Path
        from config import WORK_ZONES
        from marketplace import zone_presets

        original = {name: list(coords) for name, coords in WORK_ZONES.items()}
        tmpdir = tempfile.mkdtemp()
        try:
            zones = zone_presets.apply_preset("standard", zones_file=_Path(tmpdir) / "zones.json")
            self.assertEqual(zones["left_area"][0], 0.0)
            self.assertEqual(WORK_ZONES["right_area"][2], 1.0)
            self.assertTrue((_Path(tmpdir) / "zones.json").exists())

            two = zone_presets.apply_preset("two_zone", zones_file=_Path(tmpdir) / "zones2.json")
            self.assertAlmostEqual(two["left_area"][2], 0.45)
        finally:
            zone_presets.apply_preset.__globals__["update_work_zones"](original)

    def test_unknown_preset(self):
        from marketplace import zone_presets

        with self.assertRaises(zone_presets.ZonePresetError):
            zone_presets.get_preset("nope")



class ModelSubmissionTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from database import Base
        from db_models import TenantDB

        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
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

    def _app(self, role):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.base import BaseHTTPMiddleware
        from api.v1.marketplace import router
        from database import get_db as real_get_db

        app = FastAPI()
        factory = self.Session

        def override():
            db = factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[real_get_db] = override

        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = {"sub": "u", "role": role, "tid": 1}
                return await call_next(request)

        app.add_middleware(FakeAuth)
        app.include_router(router, prefix="/api/v1")
        return TestClient(app)

    def _payload(self):
        return {
            "model_id": "custom-yolo",
            "name": "社区 YOLO 变体",
            "task": "object-detection",
            "version": "1.0",
            "license": "MIT",
            "size_mb": 6.5,
            "note": "自训练小目标模型",
        }

    def test_submit_then_approve_appears_in_catalog(self):
        admin = self._app("admin")
        created = admin.post("/api/v1/marketplace/models/submissions", json=self._payload())
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["status"], "pending")
        submission_id = created.json()["id"]

        catalog = admin.get("/api/v1/marketplace/models").json()
        self.assertNotIn("custom-yolo", [item["model_id"] for item in catalog])

        platform = self._app("platform_admin")
        reviewed = platform.post(
            "/api/v1/marketplace/models/submissions/{}/review".format(submission_id),
            json={"approve": True, "note": "验证通过"},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["status"], "approved")

        catalog = admin.get("/api/v1/marketplace/models").json()
        self.assertIn("custom-yolo", [item["model_id"] for item in catalog])

    def test_tenant_admin_cannot_review(self):
        admin = self._app("admin")
        created = admin.post("/api/v1/marketplace/models/submissions", json=self._payload())
        submission_id = created.json()["id"]
        reviewed = admin.post(
            "/api/v1/marketplace/models/submissions/{}/review".format(submission_id),
            json={"approve": True},
        )
        self.assertEqual(reviewed.status_code, 403)

    def test_duplicate_pending_rejected(self):
        admin = self._app("admin")
        self.assertEqual(
            admin.post("/api/v1/marketplace/models/submissions", json=self._payload()).status_code,
            200,
        )
        again = admin.post("/api/v1/marketplace/models/submissions", json=self._payload())
        self.assertEqual(again.status_code, 400)

    def test_missing_fields_rejected(self):
        admin = self._app("admin")
        bad = admin.post(
            "/api/v1/marketplace/models/submissions", json={"model_id": "x"}
        )
        self.assertEqual(bad.status_code, 422)


if __name__ == "__main__":
    unittest.main()
