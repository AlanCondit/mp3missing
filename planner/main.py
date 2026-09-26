"""Plot serves one page and a handful of form posts.

Routes
------
GET  /                                          empty state, or redirect to the latest plan
GET  /?new=1                                    form for a new plan
GET  /p/{project_id}                            one plan
POST /projects                                  create a plan
POST /projects/example                          create the sample plan
POST /p/{project_id}                            save or delete the brief
POST /p/{project_id}/phases                     add a phase
POST /p/{project_id}/phases/{phase_id}          save, move, or delete a phase
POST /p/{project_id}/phases/{phase_id}/tasks    add a task
POST /p/{project_id}/phases/{phase_id}/tasks/{task_id}
                                                save, advance status, move, or delete a task

Run it from the repository root with: python -m planner
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from planner.models import STATUS_LABELS, PlanError
from planner.store import Store

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
DEFAULT_DATA = ROOT / "data" / "projects.json"
PORT = int(os.environ.get("PORT", "47291"))


def create_app(data_path: Path | None = None) -> FastAPI:
    store = Store(data_path or DEFAULT_DATA)
    app = FastAPI(title="Plot", docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def render_page(
        request: Request,
        *,
        project: dict | None = None,
        missing: bool = False,
        error: str = "",
        status_code: int = 200,
        draft: dict | None = None,
    ):
        context = {
            "projects": store.list_projects(),
            "project": project,
            "missing": missing,
            "error": error,
            "status_labels": STATUS_LABELS,
            "draft": draft or {"name": "", "outcome": "", "constraints": ""},
        }
        return templates.TemplateResponse(
            request,
            "page.html",
            context,
            status_code=status_code,
        )

    def recover(request: Request, project_id: str | None, exc: PlanError, *, fresh: bool = False):
        if fresh or not project_id:
            return render_page(request, error=str(exc), status_code=exc.status)
        try:
            project = store.get_project(project_id)
        except PlanError:
            return render_page(request, missing=True, status_code=404)
        return render_page(request, project=project, error=str(exc), status_code=exc.status)

    def go(project_id: str, fragment: str = "") -> RedirectResponse:
        url = f"/p/{project_id}"
        if fragment:
            url = f"{url}#{fragment}"
        return RedirectResponse(url, status_code=303)

    @app.get("/")
    def home(request: Request, new: str = ""):
        projects = store.list_projects()
        if new == "1" or not projects:
            return render_page(request)
        return RedirectResponse(f"/p/{projects[0]['id']}", status_code=302)

    @app.get("/p/{project_id}")
    def show_project(request: Request, project_id: str):
        try:
            project = store.get_project(project_id)
        except PlanError as exc:
            return render_page(request, missing=True, status_code=exc.status)
        return render_page(request, project=project)

    @app.post("/projects")
    def create_project(
        request: Request,
        name: str = Form(""),
        outcome: str = Form(""),
        constraints: str = Form(""),
    ):
        try:
            project = store.create_project(name, outcome, constraints)
        except PlanError as exc:
            return render_page(
                request,
                error=str(exc),
                status_code=exc.status,
                draft={"name": name, "outcome": outcome, "constraints": constraints},
            )
        return go(project["id"])

    @app.post("/projects/example")
    def create_example(request: Request):
        try:
            project = store.create_example()
        except PlanError as exc:
            return recover(request, None, exc, fresh=True)
        return go(project["id"])

    @app.post("/p/{project_id}")
    def update_project(
        request: Request,
        project_id: str,
        op: str = Form("save"),
        name: str = Form(""),
        outcome: str = Form(""),
        constraints: str = Form(""),
        confirm: str = Form(""),
    ):
        try:
            if op == "delete":
                if confirm != "yes":
                    raise PlanError("Tick the box before deleting this plan.")
                store.delete_project(project_id)
                return RedirectResponse("/", status_code=303)
            if op != "save":
                raise PlanError("Unknown action.")
            store.update_project(project_id, name, outcome, constraints)
        except PlanError as exc:
            return recover(request, project_id, exc)
        return go(project_id)

    @app.post("/p/{project_id}/phases")
    def add_phase(
        request: Request,
        project_id: str,
        name: str = Form(""),
        intent: str = Form(""),
    ):
        try:
            project = store.add_phase(project_id, name, intent)
        except PlanError as exc:
            return recover(request, project_id, exc)
        fragment = f"phase-{project['phases'][-1]['id']}"
        return go(project_id, fragment)

    @app.post("/p/{project_id}/phases/{phase_id}")
    def update_phase(
        request: Request,
        project_id: str,
        phase_id: str,
        op: str = Form("save"),
        name: str = Form(""),
        intent: str = Form(""),
    ):
        try:
            if op == "delete":
                store.delete_phase(project_id, phase_id)
                return go(project_id)
            if op in {"up", "down"}:
                store.move_phase(project_id, phase_id, op)
                return go(project_id, f"phase-{phase_id}")
            if op != "save":
                raise PlanError("Unknown action.")
            store.update_phase(project_id, phase_id, name, intent)
        except PlanError as exc:
            return recover(request, project_id, exc)
        return go(project_id, f"phase-{phase_id}")

    @app.post("/p/{project_id}/phases/{phase_id}/tasks")
    def add_task(
        request: Request,
        project_id: str,
        phase_id: str,
        title: str = Form(""),
        detail: str = Form(""),
    ):
        try:
            project = store.add_task(project_id, phase_id, title, detail)
        except PlanError as exc:
            return recover(request, project_id, exc)
        phase = next(item for item in project["phases"] if item["id"] == phase_id)
        return go(project_id, f"task-{phase['tasks'][-1]['id']}")

    @app.post("/p/{project_id}/phases/{phase_id}/tasks/{task_id}")
    def update_task(
        request: Request,
        project_id: str,
        phase_id: str,
        task_id: str,
        op: str = Form("save"),
        title: str = Form(""),
        detail: str = Form(""),
    ):
        try:
            if op == "delete":
                store.delete_task(project_id, phase_id, task_id)
                return go(project_id, f"phase-{phase_id}")
            if op == "status":
                store.cycle_task(project_id, phase_id, task_id)
            elif op in {"up", "down"}:
                store.move_task(project_id, phase_id, task_id, op)
            elif op == "save":
                store.update_task(project_id, phase_id, task_id, title, detail)
            else:
                raise PlanError("Unknown action.")
        except PlanError as exc:
            return recover(request, project_id, exc)
        return go(project_id, f"task-{task_id}")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


app = create_app()


def serve() -> None:
    import uvicorn

    uvicorn.run(
        "planner.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=PORT,
        reload=False,
    )
