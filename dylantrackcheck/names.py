"""Normalize live folder and track names for comparison."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Live album folders look like "1965 - Highway 61 Revisited".
_ALBUM_FOLDER = re.compile(r"^(\d{4})\s+-\s+(.+)$")

# "01 - Title", "01. Title", "01 Title", "1-01 Title".
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
_COPY_SUFFIX = re.compile(r"\s+copy(?:\s+\d+)?$", re.IGNORECASE)
_COPY_PREFIX = re.compile(r"^copy\s+of\s+", re.IGNORECASE)
_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".flac", ".aiff", ".aif", ".wav", ".m4p")

# Catalog titles use curly quotes and fancy dashes; live folders often do not.
_DASHES = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
    }
)


def parse_album_folder(name: str) -> tuple[int, str] | None:
    """Return ``(year, album title)`` for ``YYYY - Title`` folders."""

    match = _ALBUM_FOLDER.match(name.strip())
    if not match:
        return None
    return int(match.group(1)), match.group(2).strip()


def album_key(title: str) -> str:
    """Compare album titles without year, case, or fancy punctuation."""

    text = title.strip()
    text = text.strip("\"“”‘’'")
    text = text.translate(_DASHES)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def song_name(filename: str) -> str:
    """Display name: no extension, track number, or Finder copy marker."""

    stem = _stem(filename)
    cleaned = _strip_name_marks(stem)
    return cleaned or stem.strip() or Path(filename).stem


def track_key(name: str) -> str:
    """Key for matching an expected title to a live audio file name."""

    text = song_name(name) if _looks_like_filename(name) else name
    text = text.translate(_DASHES)
    text = text.strip("\"“”‘’'")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    # Catalog sometimes uses "#" / "№"; treat as equivalent space/number mark.
    text = text.replace("♯", "#")
    return text.casefold()


def _looks_like_filename(name: str) -> bool:
    folded = name.casefold()
    return any(folded.endswith(ext) for ext in _AUDIO_EXTENSIONS) or "/" in name


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
