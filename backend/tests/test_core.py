import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

import execution_tracker as execution_tracker_module
from auth.dependencies import require_permission
from config import WORK_ZONES, update_work_zones
from database import Base
from db_models import ExecutionRecord
from execution_tracker import ExecutionTracker
from models import GestureType, HandResult, HandType, SOPDefinition, SOPStep, StepStatus
from sop_manager import SOPManager
from step_recognizer import StepRecognizer


def make_hand(zone="center_area", gesture=GestureType.OPEN):
    return HandResult(
        handedness=HandType.RIGHT,
        gesture=gesture,
        current_zone=zone,
    )


class PermissionTests(unittest.TestCase):
    @staticmethod
    def request_for(role):
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
        request.state.user = {"sub": "test", "role": role}
        return request

    def test_permission_dependency_enforces_role(self):
        dependency = require_permission("sop:edit")
        self.assertEqual(dependency(self.request_for("admin"))["role"], "admin")
        with self.assertRaises(HTTPException) as context:
            dependency(self.request_for("operator"))
        self.assertEqual(context.exception.status_code, 403)


class RecognizerTests(unittest.TestCase):
    def setUp(self):
        self.steps = [
            SOPStep(
                step_id=1,
                name="first",
                target_zone="left_area",
                required_gesture=GestureType.PINCH,
                hold_duration_sec=0,
            ),
            SOPStep(
                step_id=2,
                name="second",
                target_zone="center_area",
                required_gesture=GestureType.OPEN,
                hold_duration_sec=0,
            ),
        ]

    def test_detects_future_step_without_advancing(self):
        recognizer = StepRecognizer(self.steps)
        future = recognizer.find_out_of_sequence_match([make_hand()])
        self.assertIsNotNone(future)
        self.assertEqual(future.step_id, 2)
        self.assertEqual(recognizer.current_index, 0)

    def test_pause_resets_partial_hold(self):
        step = self.steps[1].model_copy(update={"hold_duration_sec": 10})
        recognizer = StepRecognizer([step])
        recognizer.update([make_hand()])
        self.assertEqual(recognizer.states[0].status, StepStatus.IN_PROGRESS)
        recognizer.suspend_timing()
        self.assertEqual(recognizer.states[0].status, StepStatus.PENDING)
        self.assertEqual(recognizer.states[0].matched_duration, 0)


class ZoneTests(unittest.TestCase):
    def test_live_zone_update_replaces_map(self):
        original = {name: list(coords) for name, coords in WORK_ZONES.items()}
        try:
            update_work_zones({"work": [0.1, 0.2, 0.8, 0.9]})
            self.assertEqual(WORK_ZONES, {"work": (0.1, 0.2, 0.8, 0.9)})
            with self.assertRaises(ValueError):
                update_work_zones({"bad": [-1, 0, 1, 1]})
        finally:
            update_work_zones(original)


class ExecutionTrackerTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(bind=engine)

    def test_completed_run_is_persisted(self):
        manager = SOPManager()
        manager.load_definition(
            SOPDefinition(
                sop_name="test-sop",
                steps=[
                    SOPStep(
                        step_id=1,
                        name="finish",
                        target_zone="center_area",
                        required_gesture=GestureType.OPEN,
                        hold_duration_sec=0,
                    )
                ],
            ),
            source="test",
        )
        tracker = ExecutionTracker()
        with patch.object(
            execution_tracker_module,
            "SessionLocal",
            self.session_factory,
        ):
            record_id = tracker.start(manager)
            manager.recognizer.update([make_hand()])
            tracker.sync(manager.recognizer)

        db = self.session_factory()
        try:
            record = db.query(ExecutionRecord).filter_by(id=record_id).one()
            self.assertEqual(record.status, "completed")
            self.assertIsNotNone(record.end_time)
            self.assertEqual(record.steps[0].status, "completed")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
