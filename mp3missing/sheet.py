"""Write the missing list as an Excel workbook."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from mp3missing.compare import song_name
from mp3missing.model import Track


def write_xlsx(path: Path, missing: list[Track]) -> None:
    """Save artist, album, and song. One row per missing archive file."""

    book = Workbook()
    sheet = book.active
    sheet.title = "Missing"
    sheet.append(["Artist", "Album", "Song"])
    for track in missing:
        sheet.append([track.artist, track.album, song_name(track.filename)])
    for column, width in (("A", 28), ("B", 28), ("C", 42)):
        sheet.column_dimensions[column].width = width
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
