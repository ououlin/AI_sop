"""阶段 M3（落库版）：设备管理与远程运维测试。"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.ops import agent_router, router as ops_router
from central.aggregation_server import StationReport
from database import Base
from database import get_db as real_get_db
from db_models import DeviceCommandDB, DeviceDB, TenantDB
from dependencies import get_device_manager
from ops import ota_updater
from ops.device_manager import DeviceManager
from ops.health_monitor import evaluate


def make_report(**kwargs):
    defaults = {
        "station_id": "W-001",
        "station_name": "一号工位",
        "status": "running",
        "fps": 25.0,
        "app_version": "1.0.0",
        "model_version": "yolov8n@8.2.0",
        "camera_ok": True,
        "latency_ms": 12.0,
    }
    defaults.update(kwargs)
    return StationReport(**defaults)


class DeviceManagerTests(unittest.TestCase):
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
        self.manager = DeviceManager()

    def test_touch_creates_and_updates_device(self):
        db = self.Session()
        try:
            device = self.manager.touch(db, 1, make_report())
            self.assertEqual(device.device_id, "W-001")
            self.assertEqual(device.model_version, "yolov8n@8.2.0")
            self.assertTrue(self.manager.is_online(device))

            self.manager.touch(db, 1, make_report(fps=10.0, station_name="改名工位"))
            rows = db.query(DeviceDB).filter(DeviceDB.tenant_id == 1).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].fps, 10.0)
            self.assertEqual(rows[0].name, "改名工位")
        finally:
            db.close()

    def test_offline_after_timeout(self):
        db = self.Session()
        try:
            device = self.manager.touch(db, 1, make_report())
            later = datetime.now() + timedelta(seconds=60)
            self.assertFalse(self.manager.is_online(device, now=later))
        finally:
            db.close()

    def test_tenant_isolation(self):
        db = self.Session()
        try:
            self.manager.touch(db, 1, make_report())
            self.assertEqual(len(self.manager.list_devices(db, 2)), 0)
            self.assertIsNone(self.manager.get_device(db, 2, "W-001"))
        finally:
            db.close()

    def test_config_push_and_ack(self):
        db = self.Session()
        try:
            self.manager.touch(db, 1, make_report())
            command = self.manager.set_config(db, 1, "W-001", {"report_interval": 2.0})
            self.assertEqual(command["payload"]["version"], 1)
            self.assertEqual(len(self.manager.pending(db, "W-001")), 1)

            again = self.manager.set_config(db, 1, "W-001", {"report_interval": 3.0})
            self.assertEqual(again["payload"]["version"], 2)
            self.assertEqual(len(self.manager.pending(db, "W-001")), 2)

            self.assertTrue(self.manager.ack(db, "W-001", command["command_id"]))
            self.assertEqual(len(self.manager.pending(db, "W-001")), 1)
            state = self.manager.state_of(db, "W-001")
            self.assertEqual(state["last_ack"]["status"], "acked")
            self.assertEqual(state["config_version"], 2)
        finally:
            db.close()

    def test_config_unknown_device(self):
        db = self.Session()
        try:
            with self.assertRaises(KeyError):
                self.manager.set_config(db, 1, "W-404", {"a": 1})
        finally:
            db.close()

    def test_ack_invalid_status_and_unknown(self):
        db = self.Session()
        try:
            self.manager.touch(db, 1, make_report())
            command = self.manager.set_config(db, 1, "W-001", {"x": 1})
            with self.assertRaises(ValueError):
                self.manager.ack(db, "W-001", command["command_id"], status="done")
            self.assertFalse(self.manager.ack(db, "W-001", "missing"))
        finally:
            db.close()

    def test_pending_limit(self):
        db = self.Session()
        try:
            self.manager.touch(db, 1, make_report())
            for index in range(8):
                self.manager.set_config(db, 1, "W-001", {"n": index})
            self.assertEqual(len(self.manager.pending(db, "W-001")), 5)
        finally:
            db.close()

    def test_commands_persist_in_table(self):
        db = self.Session()
        try:
            self.manager.touch(db, 1, make_report())
            self.manager.set_config(db, 1, "W-001", {"report_interval": 2.0})
            self.assertEqual(db.query(DeviceCommandDB).count(), 1)
        finally:
            db.close()

    def test_ota_catalog(self):
        versions = ota_updater.list_versions()
        self.assertGreaterEqual(len(versions), 2)
        with self.assertRaises(ota_updater.UpgradeError):
            ota_updater.resolve("yolov8n", "9.9.9")


class HealthTests(unittest.TestCase):
    def test_levels(self):
        healthy = SimpleNamespace(is_online=True, camera_ok=True, fps=25.0, latency_ms=10.0)
        warning = SimpleNamespace(is_online=True, camera_ok=False, fps=1.0, latency_ms=900.0)
        offline = SimpleNamespace(is_online=False, camera_ok=True, fps=25.0, latency_ms=10.0)

        self.assertEqual(evaluate(healthy), ("healthy", []))
        status, issues = evaluate(warning)
        self.assertEqual(status, "warning")
        self.assertEqual(len(issues), 3)
        self.assertEqual(evaluate(offline)[0], "offline")


class OpsApiTests(unittest.TestCase):
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

        self.manager = DeviceManager()
        db = self.Session()
        self.manager.touch(db, 1, make_report())
        self.manager.touch(db, 1, make_report(station_id="W-002", camera_ok=False, fps=2.0, latency_ms=800.0))
        db.close()

        app = FastAPI()
        app.state.session_factory = self.Session
        app.dependency_overrides[real_get_db] = self._get_db_override()
        app.dependency_overrides[get_device_manager] = lambda: self.manager

        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = {"sub": "admin", "role": "admin", "tid": 1}
                return await call_next(request)

        app.add_middleware(FakeAuth)
        app.include_router(ops_router, prefix="/api/v1")
        app.include_router(agent_router, prefix="/api/v1")
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

    def test_list_devices_health(self):
        response = self.client.get("/api/v1/ops/devices")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["summary"]["total"], 2)
        self.assertEqual(body["summary"]["healthy"], 1)
        self.assertEqual(body["summary"]["warning"], 1)
        by_id = {item["device_id"]: item for item in body["devices"]}
        self.assertEqual(by_id["W-001"]["model_version"], "yolov8n@8.2.0")
        self.assertIn("摄像头异常", by_id["W-002"]["issues"])

    def test_detail_and_404(self):
        detail = self.client.get("/api/v1/ops/devices/W-001")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("commands", detail.json())
        self.assertEqual(self.client.get("/api/v1/ops/devices/none").status_code, 404)

    def test_config_then_ack(self):
        pushed = self.client.post(
            "/api/v1/ops/devices/W-001/config",
            json={"config": {"report_interval": 2.0}},
        )
        self.assertEqual(pushed.status_code, 200, pushed.text)
        command_id = pushed.json()["command"]["command_id"]

        detail = self.client.get("/api/v1/ops/devices/W-001").json()
        self.assertEqual(detail["pending_commands"], 1)

        acked = self.client.post(
            "/api/v1/station/ack",
            json={"station_id": "W-001", "command_id": command_id},
        )
        self.assertEqual(acked.status_code, 200, acked.text)

        detail = self.client.get("/api/v1/ops/devices/W-001").json()
        self.assertEqual(detail["pending_commands"], 0)
        self.assertEqual(detail["last_ack"]["status"], "acked")

    def test_upgrade_and_validation(self):
        ok = self.client.post(
            "/api/v1/ops/devices/W-001/upgrade",
            json={"model_id": "yolov8n", "version": "8.3.0"},
        )
        self.assertEqual(ok.status_code, 200)
        bad = self.client.post(
            "/api/v1/ops/devices/W-001/upgrade",
            json={"model_id": "yolov8n", "version": "9.9.9"},
        )
        self.assertEqual(bad.status_code, 400)
        missing = self.client.post(
            "/api/v1/ops/devices/none/upgrade",
            json={"model_id": "yolov8n", "version": "8.3.0"},
        )
        self.assertEqual(missing.status_code, 404)

    def test_persistence_across_manager_instances(self):
        """换一个 Manager 实例仍能看到设备与命令（验证落库）。"""
        self.client.post(
            "/api/v1/ops/devices/W-001/config", json={"config": {"report_interval": 5.0}}
        )
        fresh = DeviceManager()
        db = self.Session()
        try:
            device = fresh.get_device(db, 1, "W-001")
            self.assertIsNotNone(device)
            self.assertEqual(len(fresh.pending(db, "W-001")), 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
