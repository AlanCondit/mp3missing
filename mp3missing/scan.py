"""Walk a library folder and read each audio header.

Audio samples are not decoded. MP3 duration and bitrate come from the
MPEG frame header (or the Xing/VBRI header). M4A duration and bitrate
come from the MP4 header. Artist and album come from tags.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from mutagen import MutagenError
from mutagen.mp3 import HeaderNotFoundError, MPEGInfo
from mutagen.mp4 import MP4, MP4StreamInfoError

from mp3missing.id3text import artist_and_album
from mp3missing.model import UNKNOWN_ALBUM, UNKNOWN_ARTIST, Track


class UnreadableMP3(Exception):
    """The file looks like audio but its header could not be read."""


@dataclass(frozen=True)
class ScanResult:
    tracks: list[Track]
    unreadable: list[tuple[Path, str]]


def is_mp3_filename(name: str) -> bool:
    """True for ``.mp3`` / ``.MP3`` files, excluding AppleDouble sidecars."""

    return _is_audio_filename(name, ".mp3")


def is_audio_filename(name: str) -> bool:
    """True for ``.mp3`` and ``.m4a``, excluding AppleDouble sidecars.

    ``._Song.mp3`` is the resource-fork sidecar macOS writes on some
    disks. It is not an audio file.
    """

    return _is_audio_filename(name, ".mp3", ".m4a")


def _is_audio_filename(name: str, *suffixes: str) -> bool:
    if name.startswith("._"):
        return False
    folded = name.casefold()
    return folded.endswith(suffixes)


def scan_library(root: Path, *, label: str = "library") -> ScanResult:
    """Read every MP3 and M4A under ``root``.

    Other file types are ignored. A file that cannot be parsed is listed
    in ``unreadable`` and left out of ``tracks``; one bad file does not
    stop the scan. Progress is printed to stderr when reading starts, on
    the first file, and every 25 files after that.
    """

    tracks: list[Track] = []
    unreadable: list[tuple[Path, str]] = []

    def onerror(err: OSError) -> None:
        unreadable.append((Path(err.filename or root), err.strerror or str(err)))

    print(f"{label}: reading {root}", file=sys.stderr, flush=True)
    seen = 0
    for dirpath, _dirnames, filenames in os.walk(root, onerror=onerror):
        for name in filenames:
            if not is_audio_filename(name):
                continue
            seen += 1
            path = Path(dirpath) / name
            if seen == 1 or seen % 25 == 0:
                print(f"{label}: {seen} — {name}", file=sys.stderr, flush=True)
            try:
                tracks.append(read_track(path))
            except UnreadableMP3 as exc:
                unreadable.append((path, str(exc)))

    print(f"{label}: finished, {seen} audio files", file=sys.stderr, flush=True)
    return ScanResult(tracks=tracks, unreadable=unreadable)


def read_track(path: Path) -> Track:
    """Read one audio file's header and tags. Does not decode samples."""

    if path.suffix.casefold() == ".m4a":
        duration, bitrate_kbps, artist, album = _read_m4a(path)
    else:
        duration, bitrate_kbps = _read_mp3(path)
        artist, album = artist_and_album(path)
    return Track(
        path=path,
        filename=path.name,
        duration=duration,
        bitrate_kbps=bitrate_kbps,
        artist=artist.strip() or UNKNOWN_ARTIST,
        album=album.strip() or UNKNOWN_ALBUM,
    )


def _read_mp3(path: Path) -> tuple[float, int]:
    try:
        with path.open("rb") as handle:
            info = MPEGInfo(handle)
    except (HeaderNotFoundError, MutagenError, OSError) as exc:
        raise UnreadableMP3(str(exc)) from exc
    return _duration_and_bitrate(info, "MPEG header has no duration or bitrate")


def _read_m4a(path: Path) -> tuple[float, int, str, str]:
    try:
        audio = MP4(path)
    except (MP4StreamInfoError, MutagenError, OSError) as exc:
        raise UnreadableMP3(str(exc)) from exc
    duration, bitrate_kbps = _duration_and_bitrate(
        audio.info,
        "MP4 header has no duration or bitrate",
    )
    tags = audio.tags or {}
    return duration, bitrate_kbps, _mp4_text(tags, "\xa9ART"), _mp4_text(tags, "\xa9alb")


def _duration_and_bitrate(info, empty_message: str) -> tuple[float, int]:
    if info is None or info.bitrate <= 0 or info.length <= 0:
        raise UnreadableMP3(empty_message)
    return float(info.length), int(round(info.bitrate / 1000.0))


def _mp4_text(tags, key: str) -> str:
    values = tags.get(key) or []
    parts = [str(value).strip() for value in values if str(value).strip()]
    return ", ".join(parts)
