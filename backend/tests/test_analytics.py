"""阶段 M4：数据分析与 BI 指标测试。"""

import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware

from analytics import metrics_calculator, trend_analyzer
from api.v1.analytics import router as analytics_router
from database import Base
from database import get_db as real_get_db
from db_models import ExecutionRecord, StepRecord, TenantDB


class _AnalyticsBase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.now = datetime(2026, 11, 20, 12, 0, 0)

        db = self.Session()
        db.add_all([
            TenantDB(id=1, code="default", name="默认租户"),
            TenantDB(id=2, code="acme", name="Acme"),
        ])
        db.commit()
        db.close()

    def _add_run(self, tenant_id, status, duration, minutes_ago, steps=(), name="装配工序"):
        db = self.Session()
        start = self.now - timedelta(minutes=minutes_ago)
        end = start + timedelta(seconds=duration or 0)
        record = ExecutionRecord(
            tenant_id=tenant_id,
            sop_name=name,
            start_time=start,
            end_time=end,
            status=status,
            total_duration=duration,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        for index, (step_name, step_status, step_duration) in enumerate(steps):
            db.add(
                StepRecord(
                    record_id=record.id,
                    step_name=step_name,
                    step_index=index,
                    status=step_status,
                    duration=step_duration,
                    completed_at=end,
                )
            )
        db.commit()
        record_id = record.id
        db.close()
        return record_id


class MetricsTests(_AnalyticsBase):
    def setUp(self):
        super().setUp()
        self._add_run(1, "completed", 30, 60, steps=[("取料", "completed", 10), ("放置", "timeout", 15)])
        self._add_run(1, "completed", 20, 30, steps=[("取料", "completed", 8), ("放置", "completed", 9)])
        self._add_run(1, "error", None, 20, steps=[("取料", "error", 3)])
        self._add_run(1, "interrupted", None, 10)
        # 其他租户的数据不应被统计
        self._add_run(2, "completed", 999, 15)

    def test_overview_metrics(self):
        data = metrics_calculator.compute_overview(
            self.Session(), days=7, tenant_id=1, now=self.now
        )
        self.assertEqual(data["total_runs"], 4)
        self.assertEqual(data["completed_runs"], 2)
        self.assertEqual(data["failed_runs"], 2)
        self.assertEqual(data["fpy"], 0.5)
        self.assertEqual(data["cycle_time_sec"], 25.0)
        self.assertEqual(data["step_opportunities"], 5)
        self.assertEqual(data["defect_steps"], 2)
        self.assertAlmostEqual(data["dpmo"], 2 * 1_000_000 / (5 * 4), places=1)
        detail = data["oee_detail"]
        # 可用率按窗口内的执行覆盖时长计算，测试数据只占几秒，数值很小但必须非零
        self.assertGreater(detail["availability"], 0)
        self.assertAlmostEqual(detail["performance"], 0.8, places=4)
        self.assertEqual(detail["quality"], 0.5)
        self.assertAlmostEqual(
            data["oee"], round(detail["availability"] * 0.8 * 0.5, 4), places=4
        )
        self.assertGreater(data["coverage_sec"], 0)
        self.assertIsNotNone(data["mtbf_sec"])

    def test_tenant_isolation(self):
        data = metrics_calculator.compute_overview(
            self.Session(), days=7, tenant_id=2, now=self.now
        )
        self.assertEqual(data["total_runs"], 1)
        self.assertEqual(data["fpy"], 1.0)


class TrendTests(_AnalyticsBase):
    def setUp(self):
        super().setUp()
        self._add_run(1, "completed", 30, 60, steps=[("取料", "completed", 10), ("放置", "completed", 12)])
        self._add_run(1, "completed", 20, 30, steps=[("取料", "completed", 8), ("放置", "completed", 9)])
        self._add_run(1, "error", None, 10, steps=[("取料", "timeout", 4)])

    def test_daily_series_shape(self):
        series = trend_analyzer.daily_series(
            self.Session(), days=7, tenant_id=1, now=self.now
        )
        self.assertEqual(len(series), 7)
        self.assertEqual(sum(item["runs"] for item in series), 3)
        today = series[-1]
        self.assertEqual(today["runs"], 3)
        self.assertEqual(today["completed"], 2)
        self.assertEqual(today["fpy"], round(2 / 3, 4))
        self.assertEqual(today["avg_duration_sec"], 25.0)

    def test_step_ranking(self):
        rows = trend_analyzer.step_ranking(
            self.Session(), days=30, tenant_id=1, now=self.now, limit=5
        )
        self.assertTrue(rows)
        durations = [row["avg_duration_sec"] or 0 for row in rows]
        self.assertEqual(durations, sorted(durations, reverse=True))

    def test_sop_breakdown(self):
        rows = trend_analyzer.sop_breakdown(
            self.Session(), days=30, tenant_id=1, now=self.now
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sop_name"], "装配工序")
        self.assertEqual(rows[0]["runs"], 3)


class AnalyticsApiTests(_AnalyticsBase):
    def setUp(self):
        super().setUp()
        self._add_run(1, "completed", 30, 60, steps=[("取料", "completed", 10)])
        self._add_run(1, "completed", 20, 30, steps=[("取料", "completed", 8)])

        app = FastAPI()
        app.dependency_overrides[real_get_db] = self._get_db_override()

        class FakeAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.user = {"sub": "admin", "role": "admin", "tid": 1}
                return await call_next(request)

        app.add_middleware(FakeAuth)
        app.include_router(analytics_router, prefix="/api/v1")
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

    def test_overview_endpoint(self):
        response = self.client.get("/api/v1/analytics/overview?days=7")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_runs"], 2)
        self.assertEqual(body["fpy"], 1.0)
        self.assertIn("oee_detail", body)

    def test_trend_endpoint(self):
        response = self.client.get("/api/v1/analytics/trend?days=7")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["days"], 7)
        self.assertEqual(len(body["series"]), 7)

    def test_steps_and_sops_endpoints(self):
        steps = self.client.get("/api/v1/analytics/steps?days=7")
        self.assertEqual(steps.status_code, 200, steps.text)
        self.assertGreaterEqual(len(steps.json()["steps"]), 1)

        sops = self.client.get("/api/v1/analytics/sops?days=7")
        self.assertEqual(sops.status_code, 200, sops.text)
        self.assertEqual(sops.json()["sops"][0]["runs"], 2)

    def test_invalid_days_rejected(self):
        self.assertEqual(self.client.get("/api/v1/analytics/overview?days=0").status_code, 422)
        self.assertEqual(self.client.get("/api/v1/analytics/overview?days=999").status_code, 422)


if __name__ == "__main__":
    unittest.main()
