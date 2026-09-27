"""Load the bundled Bob Dylan studio-album track catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class ExpectedTrack:
    position: str
    title: str
    disc: int
    disc_title: str | None
    length_seconds: int | None


@dataclass(frozen=True)
class ExpectedAlbum:
    title: str
    year: int
    tracks: tuple[ExpectedTrack, ...]


def load_catalog(path: Path | None = None) -> list[ExpectedAlbum]:
    """Return studio albums with their expected track titles.

    When ``path`` is omitted, the JSON shipped under
    ``dylantrackcheck/data/`` is used.
    """

    if path is None:
        data_file = resources.files("dylantrackcheck.data").joinpath(
            "bob_dylan_studio_albums.json"
        )
        raw = json.loads(data_file.read_text(encoding="utf-8"))
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))

    albums: list[ExpectedAlbum] = []
    for entry in raw["albums"]:
        tracks = tuple(
            ExpectedTrack(
                position=str(track["position"]),
                title=str(track["title"]),
                disc=int(track.get("disc") or 1),
                disc_title=track.get("disc_title"),
                length_seconds=track.get("length_seconds"),
            )
            for track in entry["tracks"]
        )
        albums.append(
            ExpectedAlbum(
                title=str(entry["album"]),
                year=int(entry["year"]),
                tracks=tracks,
            )
        )
    return albums
