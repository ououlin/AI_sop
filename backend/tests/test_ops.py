"""阶段 M3：设备管理与远程运维测试。"""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.ops import agent_router, router as ops_router
from central.aggregation_server import AggregationServer, StationReport
from dependencies import get_aggregation_server, get_device_manager
from ops import ota_updater
from ops.device_manager import DeviceManager
from ops.health_monitor import evaluate


class DeviceManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = DeviceManager()

    def test_config_push_creates_command_and_version(self):
        command = self.manager.set_config("W-001", {"report_interval": 2.0})
        self.assertEqual(command["type"], "config")
        self.assertEqual(command["payload"]["version"], 1)
        self.assertEqual(command["status"], "pending")

        again = self.manager.set_config("W-001", {"report_interval": 3.0})
        self.assertEqual(again["payload"]["version"], 2)
        self.assertEqual(self.manager.state_of("W-001")["config_version"], 2)

    def test_pending_and_ack(self):
        command = self.manager.set_config("W-001", {"report_interval": 2.0})
        self.assertEqual(len(self.manager.pending("W-001")), 1)

        self.assertTrue(self.manager.ack("W-001", command["command_id"]))
        self.assertEqual(self.manager.pending("W-001"), [])
        self.assertEqual(self.manager.state_of("W-001")["last_ack"]["status"], "acked")

    def test_ack_unknown_command(self):
        self.assertFalse(self.manager.ack("W-001", "missing"))

    def test_ack_invalid_status(self):
        with self.assertRaises(ValueError):
            self.manager.ack("W-001", "x", status="done")

    def test_pending_is_limited(self):
        for index in range(8):
            self.manager.set_config("W-001", {"n": index})
        self.assertEqual(len(self.manager.pending("W-001")), 5)

    def test_ota_catalog(self):
        versions = ota_updater.list_versions()
        self.assertGreaterEqual(len(versions), 2)
        resolved = ota_updater.resolve("yolov8n", "8.3.0")
        self.assertEqual(resolved["channel"], "candidate")
        with self.assertRaises(ota_updater.UpgradeError):
            ota_updater.resolve("yolov8n", "9.9.9")


class HealthMonitorTests(unittest.TestCase):
    def _info(self, **kwargs):
        defaults = {
            "station_id": "W-001",
            "is_online": True,
            "camera_ok": True,
            "fps": 25.0,
            "latency_ms": 10.0,
        }
        defaults.update(kwargs)
        info = StationReport(**defaults)
        # StationInfo 才有 is_online，这里用轻量对象模拟
        class Holder:
            pass

        holder = Holder()
        for key, value in defaults.items():
            setattr(holder, key, value)
        return holder

    def test_healthy(self):
        status, issues = evaluate(self._info())
        self.assertEqual(status, "healthy")
        self.assertEqual(issues, [])

    def test_offline(self):
        status, issues = evaluate(self._info(is_online=False))
        self.assertEqual(status, "offline")

    def test_warning_on_camera_and_fps(self):
        status, issues = evaluate(self._info(camera_ok=False, fps=1.5, latency_ms=900))
        self.assertEqual(status, "warning")
        self.assertEqual(len(issues), 3)


class OpsApiTests(unittest.TestCase):
    def setUp(self):
        self.aggregation = AggregationServer()
        self.manager = DeviceManager()
        self.aggregation.report(
            StationReport(
                station_id="W-001",
                station_name="工位1",
                fps=25.0,
                app_version="1.0.0",
                model_version="yolov8n@8.2.0",
            )
        )
        self.aggregation.report(
            StationReport(
                station_id="W-002",
                station_name="工位2",
                fps=2.0,
                camera_ok=False,
            )
        )

        app = FastAPI()
        app.dependency_overrides[get_aggregation_server] = lambda: self.aggregation
        app.dependency_overrides[get_device_manager] = lambda: self.manager

        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = {"sub": "admin", "role": "admin", "tid": 1}
                return await call_next(request)

        app.add_middleware(FakeAuth)
        app.include_router(ops_router, prefix="/api/v1")
        app.include_router(agent_router, prefix="/api/v1")
        self.client = TestClient(app)

    def test_list_devices_with_health(self):
        response = self.client.get("/api/v1/ops/devices")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["summary"]["total"], 2)
        self.assertEqual(body["summary"]["healthy"], 1)
        self.assertEqual(body["summary"]["warning"], 1)
        by_id = {item["device_id"]: item for item in body["devices"]}
        self.assertEqual(by_id["W-001"]["model_version"], "yolov8n@8.2.0")
        self.assertIn("摄像头异常", by_id["W-002"]["issues"])

    def test_device_detail_and_404(self):
        detail = self.client.get("/api/v1/ops/devices/W-001")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("commands", detail.json())
        self.assertEqual(self.client.get("/api/v1/ops/devices/none").status_code, 404)

    def test_push_config_and_ack_flow(self):
        pushed = self.client.post(
            "/api/v1/ops/devices/W-001/config",
            json={"config": {"report_interval": 2.0}},
        )
        self.assertEqual(pushed.status_code, 200, pushed.text)
        command_id = pushed.json()["command"]["command_id"]

        pending = self.aggregation_report_commands("W-001")
        self.assertEqual(pending, ["config"])

        acked = self.client.post(
            "/api/v1/station/ack",
            json={"station_id": "W-001", "command_id": command_id, "status": "acked"},
        )
        self.assertEqual(acked.status_code, 200, acked.text)
        self.assertEqual(self.manager.pending("W-001"), [])

    def test_upgrade_command_and_validation(self):
        ok = self.client.post(
            "/api/v1/ops/devices/W-001/upgrade",
            json={"model_id": "yolov8n", "version": "8.3.0"},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["command"]["type"], "upgrade")

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

    def test_model_versions(self):
        response = self.client.get("/api/v1/ops/model-versions")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 2)

    def aggregation_report_commands(self, device_id):
        return [item["type"] for item in self.manager.pending(device_id)]


if __name__ == "__main__":
    unittest.main()
