# Plot

Plot is a small project planner. You name the work, say what finished looks like, split it into phases, and track each step as open, active, or done.

Plans are saved in `data/projects.json` on the machine running the app. There is no account and no network service.

## See the code

You do not need Cursor Desktop to read this. In a Cloud Agent session the files are already in the agent view.

Read them in this order:

1. `planner/examples.py` — one complete plan, written as Python data
2. `planner/models.py` — what a project, phase, and task contain
3. `planner/store.py` — how a plan is saved and updated
4. `planner/main.py` — the routes the page posts to
5. `templates/page.html` — the page itself
6. `static/app.css` — the layout

Cursor Desktop is the local editor. Install it only if you want this project on your computer inside Cursor. Running it locally needs Python 3.11 or newer, which works in any editor.

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m planner
```

On Windows, activate with `.venv\Scripts\activate` instead.

Then open [http://127.0.0.1:47291](http://127.0.0.1:47291).

Set `PORT` if you want a different port.

## Tests

```bash
python -m unittest discover -s tests -t .
```
