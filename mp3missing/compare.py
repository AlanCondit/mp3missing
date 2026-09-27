"""Decide which archive audio files are missing from the live library.

Identity is three fields, and only these three:

1. File name — the basename, not the folder path. A leading track number
   and a Finder "copy" marker are ignored. ``.mp3`` and ``.m4a`` are the
   same name when the rest matches.
2. Duration — equal within ``DURATION_TOLERANCE_SECONDS`` (inclusive).
3. Bitrate — the same integer kbps.

Artist and album are not compared. Folder names are not compared.
The result is sorted by archive artist, then archive album, then song name.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from mp3missing.model import DURATION_TOLERANCE_SECONDS, Track

# "01 - Title", "01. Title", "01 Title", "1-01 Title".
# "19-2000" stays whole: a hyphen only counts when it is not followed by
# another digit, or when there is a space around it.
_TRACK_PREFIX = re.compile(
    r"^(?:"
    r"\d{1,2}[-.]\d{1,3}(?:\s*[-–—.)]\s*|\s+)"
    r"|\d{1,3}\s*[-–—.)]\s+"
    r"|\d{1,3}\s+[-–—.)]\s*"
    r"|\d{1,3}[.]"
    r"|\d{1,3}-(?!\d)"
    r"|(?:\d{1,2}|0\d{2})\s+"
    r")"
)
# Finder duplicates: "Title copy", "Title copy 2", and "Copy of Title".
_COPY_SUFFIX = re.compile(r"\s+copy(?:\s+\d+)?$", re.IGNORECASE)
_COPY_PREFIX = re.compile(r"^copy\s+of\s+", re.IGNORECASE)
_AUDIO_EXTENSIONS = (".mp3", ".m4a")


def song_name(filename: str) -> str:
    """Song name for display: no extension, track number, or copy marker.

    Original spelling is kept. ``01 - Airbag copy.mp3`` becomes ``Airbag``.
    """

    stem = _stem(filename)
    cleaned = _strip_name_marks(stem)
    return cleaned or stem.strip() or Path(filename).stem


def name_key(filename: str) -> str:
    """Key for file-name comparison.

    macOS APFS and HFS are usually case-insensitive, and Finder stores
    names in Unicode NFD. NFC plus casefold treats ``Song.mp3``,
    ``song.MP3``, and the NFD form of an accented name as the same file.
    Track numbers and "copy" are removed first, so ``01 - Song.mp3`` matches
    ``Song copy.m4a``. The comparison always works this way, including on
    Linux, because the live library this tool is aimed at is on a Mac.
    """

    return unicodedata.normalize("NFC", song_name(filename)).casefold()


def _stem(filename: str) -> str:
    name = Path(filename).name
    folded = name.casefold()
    for extension in _AUDIO_EXTENSIONS:
        if folded.endswith(extension):
            return name[: -len(extension)]
    return Path(name).stem


def _strip_name_marks(stem: str) -> str:
    text = stem
    previous = None
    while text != previous:
        previous = text
        text = _COPY_PREFIX.sub("", text).strip()
        text = _COPY_SUFFIX.sub("", text).strip()
        text = _TRACK_PREFIX.sub("", text, count=1).strip()
    return re.sub(r"\s+", " ", text).strip(" .-_")


def find_missing(
    archive: list[Track],
    live: list[Track],
    tolerance: float = DURATION_TOLERANCE_SECONDS,
) -> list[Track]:
    """Return archive tracks that no live track matches.

    This is existence, not a count. One matching live file covers every
    archive copy of that recording. Files that exist only in the live
    library are not returned.

    Matching does not remove a live file from further comparisons, so
    two archive copies of the same recording both count as present when
    the live library has one of them.
    """

    if tolerance < 0:
        raise ValueError("duration tolerance must be zero or positive")

    live_by_name: dict[str, list[Track]] = defaultdict(list)
    for track in live:
        live_by_name[name_key(track.filename)].append(track)

    missing = [
        track
        for track in archive
        if not _has_live_match(track, live_by_name, tolerance)
    ]
    missing.sort(key=_sort_key)
    return missing


def _has_live_match(
    track: Track,
    live_by_name: dict[str, list[Track]],
    tolerance: float,
) -> bool:
    for other in live_by_name.get(name_key(track.filename), ()):
        if other.bitrate_kbps != track.bitrate_kbps:
            continue
        if abs(other.duration - track.duration) <= tolerance:
            return True
    return False


def _sort_key(track: Track) -> tuple[str, str, str, str, str, str, str]:
    """Archive artist, then album, then file name.

    Case and Unicode normalization do not change the order, so ``b``
    sorts before ``C``. The original spelling and the path break ties.
    """

    return (
        _sort_text(track.artist),
        _sort_text(track.album),
        name_key(track.filename),
        song_name(track.filename),
        track.artist,
        track.album,
        str(track.path),
    )


def _sort_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()
