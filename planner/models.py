"""The shape of a plan, and the checks that keep it readable.

A project is a stack of phases. A phase is a stack of tasks.
Only tasks have a status: open, then active, then done.
"""

from __future__ import annotations

from typing import TypedDict


class PlanError(Exception):
    """A problem the page can explain in one sentence."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class Task(TypedDict):
    id: str
    title: str
    detail: str
    status: str


class Phase(TypedDict):
    id: str
    name: str
    intent: str
    tasks: list[Task]


class Project(TypedDict):
    id: str
    name: str
    outcome: str
    constraints: str
    created_at: str
    updated_at: str
    phases: list[Phase]


STATUSES = ("open", "active", "done")
NEXT_STATUS = {"open": "active", "active": "done", "done": "open"}
STATUS_LABELS = {"open": "Open", "active": "Active", "done": "Done"}

PROJECT_NAME_LIMIT = 80
OUTCOME_LIMIT = 400
CONSTRAINTS_LIMIT = 400
PHASE_NAME_LIMIT = 80
INTENT_LIMIT = 200
TASK_TITLE_LIMIT = 140
DETAIL_LIMIT = 300

MAX_PROJECTS = 40
MAX_PHASES = 24
MAX_TASKS = 40


def line(value: str, limit: int, field: str, *, required: bool = True) -> str:
    """Collapse a single-line field and enforce its limit."""

    text = " ".join(value.split())
    if required and not text:
        article = "an" if field[:1].lower() in "aeiou" else "a"
        raise PlanError(f"Add {article} {field}.")
    if len(text) > limit:
        raise PlanError(f"Use fewer than {limit} characters for the {field}.")
    return text


def block(value: str, limit: int, field: str) -> str:
    """Trim a short paragraph. Empty is allowed."""

    text = value.strip()
    if len(text) > limit:
        raise PlanError(f"Use fewer than {limit} characters for the {field}.")
    return text
