import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from planner.models import MAX_PROJECTS, PlanError
from planner.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "plans" / "projects.json"
        self.store = Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_name_is_rejected(self):
        with self.assertRaises(PlanError) as caught:
            self.store.create_project("   ")
        self.assertIn("project name", str(caught.exception))
        self.assertEqual(self.store.list_projects(), [])

    def test_plan_round_trip_and_progress(self):
        created = self.store.create_project(
            "Saturday stall",
            "The stall is packed up and the takings are counted.",
            "One day. Two people.",
        )
        project = self.store.add_phase(created["id"], "Set up", "Be ready before the gate opens.")
        phase_id = project["phases"][0]["id"]
        project = self.store.add_task(created["id"], phase_id, "Borrow a table", "Ask Nia.")
        task_id = project["phases"][0]["tasks"][0]["id"]
        project = self.store.cycle_task(created["id"], phase_id, task_id)
        self.assertEqual(project["phases"][0]["tasks"][0]["status"], "active")
        self.assertEqual(project["stats"]["focus"], "Set up")
        self.assertEqual(project["stats"]["percent"], 0)

        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("stats", saved["projects"][0])

        reloaded = Store(self.path)
        again = reloaded.get_project(created["id"])
        self.assertEqual(again["name"], "Saturday stall")
        self.assertEqual(again["phases"][0]["tasks"][0]["status"], "active")

    def test_sample_plan_focus_and_unique_names(self):
        first = self.store.create_example()
        self.assertEqual(first["stats"]["tasks"], 6)
        self.assertEqual(first["stats"]["done"], 1)
        self.assertEqual(first["stats"]["focus"], "Frame")

        active = next(
            task
            for phase in first["phases"]
            for task in phase["tasks"]
            if task["status"] == "active"
        )
        phase_id = next(
            phase["id"]
            for phase in first["phases"]
            for task in phase["tasks"]
            if task["id"] == active["id"]
        )
        moved = self.store.cycle_task(first["id"], phase_id, active["id"])
        self.assertEqual(moved["stats"]["focus"], "Draft")
        self.assertEqual(moved["stats"]["done"], 2)

        second = self.store.create_example()
        self.assertEqual(second["name"], "Publish a short field guide (2)")

    def test_move_phase_stops_at_the_ends(self):
        project = self.store.create_project("Move me")
        project = self.store.add_phase(project["id"], "First")
        project = self.store.add_phase(project["id"], "Second")
        first_id, second_id = (phase["id"] for phase in project["phases"])
        stayed = self.store.move_phase(project["id"], first_id, "up")
        self.assertEqual([phase["name"] for phase in stayed["phases"]], ["First", "Second"])
        swapped = self.store.move_phase(project["id"], second_id, "up")
        self.assertEqual([phase["name"] for phase in swapped["phases"]], ["Second", "First"])

    def test_delete_and_missing(self):
        project = self.store.create_project("Gone")
        self.store.delete_project(project["id"])
        with self.assertRaises(PlanError) as caught:
            self.store.get_project(project["id"])
        self.assertEqual(caught.exception.status, 404)

    def test_project_cap(self):
        with patch("planner.store.MAX_PROJECTS", 1):
            self.store.create_project("Only")
            with self.assertRaises(PlanError):
                self.store.create_project("Another")
        self.assertEqual(MAX_PROJECTS, 40)


if __name__ == "__main__":
    unittest.main()
