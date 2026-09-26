"""Load and change plans.

Plans are saved as JSON in one file. The page never edits that file
directly; it calls these methods, and each method saves before it returns.
"""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from planner.examples import FIELD_GUIDE
from planner.models import (
    CONSTRAINTS_LIMIT,
    DETAIL_LIMIT,
    INTENT_LIMIT,
    MAX_PHASES,
    MAX_PROJECTS,
    MAX_TASKS,
    NEXT_STATUS,
    OUTCOME_LIMIT,
    PHASE_NAME_LIMIT,
    PROJECT_NAME_LIMIT,
    TASK_TITLE_LIMIT,
    Phase,
    PlanError,
    Project,
    Task,
    block,
    line,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, list[Project]] = {"projects": []}
        self._load()

    def list_projects(self) -> list[dict]:
        with self._lock:
            ordered = sorted(
                self._data["projects"],
                key=lambda project: project["updated_at"],
                reverse=True,
            )
            return [self._present(project) for project in ordered]

    def get_project(self, project_id: str) -> dict:
        with self._lock:
            return self._present(self._find(project_id))

    def create_project(self, name: str, outcome: str = "", constraints: str = "") -> dict:
        with self._lock:
            self._room_for_project()
            project = self._new_project(name, outcome, constraints)
            self._data["projects"].append(project)
            self._save()
            return self._present(project)

    def create_example(self) -> dict:
        """Copy the field-guide sample. Repeat visits get a numbered name."""

        with self._lock:
            self._room_for_project()
            spec = FIELD_GUIDE
            project = self._new_project(
                self._unique_name(spec["name"]),
                spec["outcome"],
                spec["constraints"],
            )
            for phase_spec in spec["phases"]:
                self._room_for_phase(project)
                phase = self._new_phase(phase_spec["name"], phase_spec["intent"])
                for task_spec in phase_spec["tasks"]:
                    self._room_for_task(phase)
                    phase["tasks"].append(
                        self._new_task(
                            task_spec["title"],
                            task_spec.get("detail", ""),
                            task_spec.get("status", "open"),
                        )
                    )
                project["phases"].append(phase)
            self._data["projects"].append(project)
            self._save()
            return self._present(project)

    def update_project(
        self,
        project_id: str,
        name: str,
        outcome: str,
        constraints: str,
    ) -> dict:
        with self._lock:
            project = self._find(project_id)
            project["name"] = self._project_name(name)
            project["outcome"] = block_outcome(outcome)
            project["constraints"] = block_constraints(constraints)
            self._touch(project)
            self._save()
            return self._present(project)

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            project = self._find(project_id)
            self._data["projects"].remove(project)
            self._save()

    def add_phase(self, project_id: str, name: str, intent: str = "") -> dict:
        with self._lock:
            project = self._find(project_id)
            self._room_for_phase(project)
            project["phases"].append(self._new_phase(name, intent))
            self._touch(project)
            self._save()
            return self._present(project)

    def update_phase(self, project_id: str, phase_id: str, name: str, intent: str) -> dict:
        with self._lock:
            project = self._find(project_id)
            phase = self._find_phase(project, phase_id)
            phase["name"] = self._phase_name(name)
            phase["intent"] = block_intent(intent)
            self._touch(project)
            self._save()
            return self._present(project)

    def move_phase(self, project_id: str, phase_id: str, direction: str) -> dict:
        with self._lock:
            project = self._find(project_id)
            self._find_phase(project, phase_id)
            if self._move(project["phases"], phase_id, direction):
                self._touch(project)
                self._save()
            return self._present(project)

    def delete_phase(self, project_id: str, phase_id: str) -> dict:
        with self._lock:
            project = self._find(project_id)
            phase = self._find_phase(project, phase_id)
            project["phases"].remove(phase)
            self._touch(project)
            self._save()
            return self._present(project)

    def add_task(self, project_id: str, phase_id: str, title: str, detail: str = "") -> dict:
        with self._lock:
            project = self._find(project_id)
            phase = self._find_phase(project, phase_id)
            self._room_for_task(phase)
            phase["tasks"].append(self._new_task(title, detail, "open"))
            self._touch(project)
            self._save()
            return self._present(project)

    def update_task(
        self,
        project_id: str,
        phase_id: str,
        task_id: str,
        title: str,
        detail: str,
    ) -> dict:
        with self._lock:
            project = self._find(project_id)
            task = self._find_task(project, phase_id, task_id)
            task["title"] = self._task_title(title)
            task["detail"] = block_detail(detail)
            self._touch(project)
            self._save()
            return self._present(project)

    def cycle_task(self, project_id: str, phase_id: str, task_id: str) -> dict:
        with self._lock:
            project = self._find(project_id)
            task = self._find_task(project, phase_id, task_id)
            task["status"] = NEXT_STATUS.get(task["status"], "open")
            self._touch(project)
            self._save()
            return self._present(project)

    def move_task(self, project_id: str, phase_id: str, task_id: str, direction: str) -> dict:
        with self._lock:
            project = self._find(project_id)
            phase = self._find_phase(project, phase_id)
            self._find_task(project, phase_id, task_id)
            if self._move(phase["tasks"], task_id, direction):
                self._touch(project)
                self._save()
            return self._present(project)

    def delete_task(self, project_id: str, phase_id: str, task_id: str) -> dict:
        with self._lock:
            project = self._find(project_id)
            phase = self._find_phase(project, phase_id)
            task = self._find_task(project, phase_id, task_id)
            phase["tasks"].remove(task)
            self._touch(project)
            self._save()
            return self._present(project)

    # --- internal helpers. Callers hold self._lock. ---

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {"projects": []}
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Could not read {self.path}: {exc}") from exc
        projects = loaded.get("projects") if isinstance(loaded, dict) else None
        if not isinstance(projects, list):
            raise ValueError(f"{self.path} does not contain a list of projects.")
        self._data = {"projects": projects}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        payload = json.dumps(self._data, indent=2, ensure_ascii=False) + "\n"
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)

    def _find(self, project_id: str) -> Project:
        for project in self._data["projects"]:
            if project["id"] == project_id:
                return project
        raise PlanError("That plan is not here.", 404)

    def _find_phase(self, project: Project, phase_id: str) -> Phase:
        for phase in project["phases"]:
            if phase["id"] == phase_id:
                return phase
        raise PlanError("That phase is not in this plan.", 404)

    def _find_task(self, project: Project, phase_id: str, task_id: str) -> Task:
        phase = self._find_phase(project, phase_id)
        for task in phase["tasks"]:
            if task["id"] == task_id:
                return task
        raise PlanError("That task is not in this phase.", 404)

    def _room_for_project(self) -> None:
        if len(self._data["projects"]) >= MAX_PROJECTS:
            raise PlanError("Delete a plan before starting another. Forty is the limit.")

    def _room_for_phase(self, project: Project) -> None:
        if len(project["phases"]) >= MAX_PHASES:
            raise PlanError("This plan already has 24 phases.")

    def _room_for_task(self, phase: Phase) -> None:
        if len(phase["tasks"]) >= MAX_TASKS:
            raise PlanError("This phase already has 40 tasks.")

    def _unique_name(self, name: str) -> str:
        taken = {project["name"] for project in self._data["projects"]}
        if name not in taken:
            return name
        number = 2
        while f"{name} ({number})" in taken:
            number += 1
        candidate = f"{name} ({number})"
        if len(candidate) > PROJECT_NAME_LIMIT:
            raise PlanError("Rename an existing sample plan before adding another.")
        return candidate

    def _new_project(self, name: str, outcome: str, constraints: str) -> Project:
        now = _stamp()
        return {
            "id": _new_id(),
            "name": self._project_name(name),
            "outcome": block_outcome(outcome),
            "constraints": block_constraints(constraints),
            "created_at": now,
            "updated_at": now,
            "phases": [],
        }

    def _new_phase(self, name: str, intent: str) -> Phase:
        return {
            "id": _new_id(),
            "name": self._phase_name(name),
            "intent": block_intent(intent),
            "tasks": [],
        }

    def _new_task(self, title: str, detail: str, status: str) -> Task:
        if status not in NEXT_STATUS:
            raise PlanError("Status must be open, active, or done.")
        return {
            "id": _new_id(),
            "title": self._task_title(title),
            "detail": block_detail(detail),
            "status": status,
        }

    def _project_name(self, name: str) -> str:
        return line(name, PROJECT_NAME_LIMIT, "project name")

    def _phase_name(self, name: str) -> str:
        return line(name, PHASE_NAME_LIMIT, "phase name")

    def _task_title(self, title: str) -> str:
        return line(title, TASK_TITLE_LIMIT, "task title")

    def _touch(self, project: Project) -> None:
        project["updated_at"] = _stamp()

    def _move(self, items: list[dict], item_id: str, direction: str) -> bool:
        if direction not in {"up", "down"}:
            raise PlanError("Pick up or down.")
        index = next((i for i, item in enumerate(items) if item["id"] == item_id), None)
        if index is None:
            raise PlanError("That item is not in the plan.", 404)
        target = index - 1 if direction == "up" else index + 1
        if target < 0 or target >= len(items):
            return False
        items[index], items[target] = items[target], items[index]
        return True

    def _present(self, project: Project) -> dict:
        """Return a copy plus progress numbers. The saved file stays plain."""

        shown = deepcopy(project)
        focus_id = None
        focus_name = None
        fallback_id = None
        fallback_name = None
        done = 0
        total = 0
        for phase in shown["phases"]:
            for task in phase["tasks"]:
                if task.get("status") not in NEXT_STATUS:
                    task["status"] = "open"
                total += 1
                if task["status"] == "done":
                    done += 1
            if focus_id is None and any(task["status"] == "active" for task in phase["tasks"]):
                focus_id = phase["id"]
                focus_name = phase["name"]
            if fallback_id is None and any(task["status"] == "open" for task in phase["tasks"]):
                fallback_id = phase["id"]
                fallback_name = phase["name"]
        if focus_id is None:
            focus_id = fallback_id
            focus_name = fallback_name
        shown["stats"] = {
            "phases": len(shown["phases"]),
            "tasks": total,
            "done": done,
            "focus": focus_name,
            "focus_id": focus_id,
            "percent": round(100 * done / total) if total else 0,
        }
        return shown


def block_outcome(value: str) -> str:
    return block(value, OUTCOME_LIMIT, "outcome")


def block_constraints(value: str) -> str:
    return block(value, CONSTRAINTS_LIMIT, "limits")


def block_intent(value: str) -> str:
    return block(value, INTENT_LIMIT, "phase note")


def block_detail(value: str) -> str:
    return block(value, DETAIL_LIMIT, "task note")
