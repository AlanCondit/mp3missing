import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from planner.main import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.tmp.name) / "projects.json")
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_empty_home_explains_the_first_step(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("What are you making?", page.text)
        self.assertIn("Start this plan", page.text)
        self.assertIn("/static/app.css", page.text)

    def test_create_redirects_and_home_opens_the_latest_plan(self):
        created = self.client.post(
            "/projects",
            data={
                "name": "Saturday stall",
                "outcome": "The stall is packed up.",
                "constraints": "One day.",
            },
            follow_redirects=False,
        )
        self.assertEqual(created.status_code, 303)
        self.assertTrue(created.headers["location"].startswith("/p/"))

        page = self.client.get(created.headers["location"])
        self.assertEqual(page.status_code, 200)
        self.assertIn("Saturday stall", page.text)
        self.assertIn("Save brief", page.text)

        home = self.client.get("/", follow_redirects=False)
        self.assertEqual(home.status_code, 302)
        self.assertEqual(home.headers["location"], created.headers["location"])

    def test_blank_name_keeps_what_you_typed(self):
        page = self.client.post(
            "/projects",
            data={"name": "  ", "outcome": "Still here", "constraints": ""},
        )
        self.assertEqual(page.status_code, 400)
        self.assertIn("Add a project name.", page.text)
        self.assertIn("Still here", page.text)

    def test_sample_plan_page_lists_phases(self):
        created = self.client.post("/projects/example", follow_redirects=False)
        page = self.client.get(created.headers["location"])
        self.assertIn("Publish a short field guide", page.text)
        self.assertIn("Frame", page.text)
        self.assertIn("Active", page.text)
        self.assertIn("working in Frame", page.text)

    def test_add_phase_task_and_advance_status(self):
        created = self.client.post(
            "/projects",
            data={"name": "Stall", "outcome": "", "constraints": ""},
            follow_redirects=False,
        )
        url = created.headers["location"]
        project_id = url.rsplit("/", 1)[-1]

        added = self.client.post(
            f"/p/{project_id}/phases",
            data={"name": "Set up", "intent": "Before the gate opens."},
            follow_redirects=False,
        )
        self.assertEqual(added.status_code, 303)
        phase_page = self.client.get(url)
        self.assertIn("Set up", phase_page.text)

        phase_id = phase_page.text.split('id="phase-', 1)[1].split('"', 1)[0]
        task = self.client.post(
            f"/p/{project_id}/phases/{phase_id}/tasks",
            data={"title": "Borrow a table"},
            follow_redirects=False,
        )
        self.assertEqual(task.status_code, 303)
        task_id = task.headers["location"].split("task-", 1)[1]

        advanced = self.client.post(
            f"/p/{project_id}/phases/{phase_id}/tasks/{task_id}",
            data={"op": "status", "title": "Borrow a table", "detail": ""},
            follow_redirects=False,
        )
        self.assertEqual(advanced.status_code, 303)
        page = self.client.get(url)
        self.assertIn("Active", page.text)
        self.assertIn("working in Set up", page.text)

    def test_delete_requires_the_checkbox(self):
        created = self.client.post(
            "/projects",
            data={"name": "Keep me", "outcome": "", "constraints": ""},
            follow_redirects=False,
        )
        url = created.headers["location"]
        blocked = self.client.post(url, data={"op": "delete"})
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("Tick the box", blocked.text)

        removed = self.client.post(
            url,
            data={"op": "delete", "confirm": "yes"},
            follow_redirects=False,
        )
        self.assertEqual(removed.status_code, 303)
        self.assertEqual(removed.headers["location"], "/")
        self.assertIn("What are you making?", self.client.get("/").text)

    def test_missing_plan(self):
        page = self.client.get("/p/does-not-exist")
        self.assertEqual(page.status_code, 404)
        self.assertIn("That plan is not here.", page.text)

    def test_missing_phase_keeps_the_plan_on_screen(self):
        created = self.client.post(
            "/projects",
            data={"name": "Stay", "outcome": "", "constraints": ""},
            follow_redirects=False,
        )
        page = self.client.post(
            f"{created.headers['location']}/phases/not-a-phase",
            data={"op": "delete", "name": "Set up"},
        )
        self.assertEqual(page.status_code, 404)
        self.assertIn("Stay", page.text)
        self.assertIn("That phase is not in this plan.", page.text)


if __name__ == "__main__":
    unittest.main()
