"""A finished sample plan.

This is ordinary Python data. Choosing "Use the sample plan" in the app
copies it into a new project.
"""

from __future__ import annotations

FIELD_GUIDE = {
    "name": "Publish a short field guide",
    "outcome": (
        "A twelve-page guide a stranger can finish in one sitting "
        "and know what to do next."
    ),
    "constraints": "One weekend. No budget. Just me.",
    "phases": [
        {
            "name": "Frame",
            "intent": "Decide who it is for and the single promise of the guide.",
            "tasks": [
                {
                    "title": "Write one sentence for who it is for",
                    "detail": (
                        "If the sentence needs a comma list of audiences, "
                        "the audience is still too broad."
                    ),
                    "status": "done",
                },
                {
                    "title": "Cut the scope to twelve pages",
                    "detail": "Six sections, two pages each.",
                    "status": "active",
                },
            ],
        },
        {
            "name": "Draft",
            "intent": "Get a complete first pass, rough on purpose.",
            "tasks": [
                {
                    "title": "Outline the six sections",
                    "detail": "",
                    "status": "open",
                },
                {
                    "title": "Draft the sections in order",
                    "detail": "Stop at the end of each section instead of polishing the opening.",
                    "status": "open",
                },
            ],
        },
        {
            "name": "Release",
            "intent": "Make it readable and put it where someone can find it.",
            "tasks": [
                {
                    "title": "Read it aloud and fix what snags",
                    "detail": "",
                    "status": "open",
                },
                {
                    "title": "Export a PDF and send it to two people",
                    "detail": "Ask each of them what they would do next.",
                    "status": "open",
                },
            ],
        },
    ],
}
