"""Find Bob Dylan album folders in a live Music library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dylantrackcheck.names import parse_album_folder

_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".aiff", ".aif", ".wav", ".m4p"}
_ARTIST_NAMES = {"bob dylan", "dylan, bob"}


@dataclass(frozen=True)
class LiveTrack:
    path: Path
    filename: str


@dataclass(frozen=True)
class LiveAlbum:
    path: Path
    year: int
    title: str
    tracks: tuple[LiveTrack, ...]


def find_dylan_root(live_root: Path) -> Path:
    """Return the Bob Dylan artist folder under ``live_root``.

    ``live_root`` may already be that artist folder.
    """

    if _is_dylan_folder(live_root):
        return live_root

    matches = [
        path
        for path in live_root.iterdir()
        if path.is_dir() and _is_dylan_folder(path)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(
            f"no Bob Dylan artist folder under {live_root}"
        )
    names = ", ".join(sorted(path.name for path in matches))
    raise FileNotFoundError(
        f"multiple Bob Dylan folders under {live_root}: {names}"
    )


def scan_live_albums(dylan_root: Path) -> list[LiveAlbum]:
    """List album folders named ``YYYY - Title`` that contain audio files."""

    albums: list[LiveAlbum] = []
    for path in sorted(dylan_root.iterdir(), key=lambda p: p.name.casefold()):
        if not path.is_dir():
            continue
        parsed = parse_album_folder(path.name)
        if parsed is None:
            continue
        year, title = parsed
        tracks = tuple(_audio_files(path))
        if not tracks:
            continue
        albums.append(
            LiveAlbum(path=path, year=year, title=title, tracks=tracks)
        )
    return albums


def _is_dylan_folder(path: Path) -> bool:
    return path.name.strip().casefold() in _ARTIST_NAMES


def _audio_files(album_path: Path) -> list[LiveTrack]:
    found: list[LiveTrack] = []
    for path in sorted(album_path.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("._"):
            continue
        if path.suffix.casefold() not in _AUDIO_EXTENSIONS:
            continue
        found.append(LiveTrack(path=path, filename=path.name))
    return found
