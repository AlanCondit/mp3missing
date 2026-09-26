"""Walk a library folder and read each MP3 header.

Audio samples are not decoded. Duration and bitrate come from the MPEG
frame header (or the Xing/VBRI header, when the file has one), via
mutagen's ``MPEGInfo``. Artist and album come from ID3 text frames.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from mutagen import MutagenError
from mutagen.mp3 import HeaderNotFoundError, MPEGInfo

from mp3missing.id3text import artist_and_album
from mp3missing.model import UNKNOWN_ALBUM, UNKNOWN_ARTIST, Track


class UnreadableMP3(Exception):
    """The file ends in .mp3 but its MPEG header could not be read."""


@dataclass(frozen=True)
class ScanResult:
    tracks: list[Track]
    unreadable: list[tuple[Path, str]]


def is_mp3_filename(name: str) -> bool:
    """True for ``.mp3`` / ``.MP3`` files, excluding AppleDouble sidecars.

    ``._Song.mp3`` is the resource-fork sidecar macOS writes on some
    disks. It is not an MP3.
    """

    if name.startswith("._"):
        return False
    return name.casefold().endswith(".mp3")


def scan_library(root: Path, *, label: str = "library") -> ScanResult:
    """Read every MP3 under ``root``.

    Other file types are ignored. A file that cannot be parsed is listed
    in ``unreadable`` and left out of ``tracks``; one bad file does not
    stop the scan. Progress is printed to stderr every 1000 files.
    """

    tracks: list[Track] = []
    unreadable: list[tuple[Path, str]] = []

    def onerror(err: OSError) -> None:
        unreadable.append((Path(err.filename or root), err.strerror or str(err)))

    seen = 0
    for dirpath, _dirnames, filenames in os.walk(root, onerror=onerror):
        for name in filenames:
            if not is_mp3_filename(name):
                continue
            seen += 1
            path = Path(dirpath) / name
            try:
                tracks.append(read_track(path))
            except UnreadableMP3 as exc:
                unreadable.append((path, str(exc)))
            if seen % 1000 == 0:
                print(f"{label}: read {seen} MP3s...", file=sys.stderr, flush=True)

    return ScanResult(tracks=tracks, unreadable=unreadable)


def read_track(path: Path) -> Track:
    """Read one MP3's header and tags. Does not decode audio samples."""

    try:
        with path.open("rb") as handle:
            info = MPEGInfo(handle)
    except (HeaderNotFoundError, MutagenError, OSError) as exc:
        raise UnreadableMP3(str(exc)) from exc

    if info.bitrate <= 0 or info.length <= 0:
        raise UnreadableMP3("MPEG header has no duration or bitrate")

    artist, album = artist_and_album(path)
    return Track(
        path=path,
        filename=path.name,
        duration=float(info.length),
        bitrate_kbps=int(round(info.bitrate / 1000.0)),
        artist=artist.strip() or UNKNOWN_ARTIST,
        album=album.strip() or UNKNOWN_ALBUM,
    )
