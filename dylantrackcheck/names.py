"""Normalize live folder and track names for comparison."""

from __future__ import annotations

import re
import unicodedata

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
# Match keys treat these as the same separator (a single space).
_SEPARATORS = re.compile(r"[/_-]+")
# Match keys ignore these characters entirely.
_IGNORE_CHARS = re.compile(r"[,.'’‘]")
# After the track number is gone, drop trailing "(With …)", "(feat. …)", etc.
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
# After punctuation is gone, these spoken/-in forms match the -ing spelling.
_ING_EQUIV = {
    "talkin": "talking",
    "blowin": "blowing",
    "givin": "giving",
}


def parse_album_folder(name: str) -> tuple[int, str] | None:
    """Return ``(year, album title)`` for ``YYYY - Title`` folders."""

    match = _ALBUM_FOLDER.match(name.strip())
    if not match:
        return None
    return int(match.group(1)), match.group(2).strip()


def album_key(title: str) -> str:
    """Compare album titles without year, case, or match-key punctuation."""

    return _match_key(title)


def song_name(filename: str) -> str:
    """Display name: no extension, track number, or Finder copy marker."""

    stem = _stem(filename)
    cleaned = _strip_name_marks(stem)
    return cleaned or stem.strip() or filename


def track_key(name: str) -> str:
    """Key for matching an expected title to a live audio file name.

    Track numbers and Finder copy markers are stripped first (same as
    ``song_name``). Trailing parentheticals such as ``(With …)``,
    ``(feat. …)``, ``(Album Version)`` are removed for matching only.
    Then ``/``, ``_``, and ``-`` count as one separator; ``,`` ``.``
    ``'`` and ``’`` are ignored; spoken ``-in`` forms match ``-ing``.
    Spreadsheet display still uses the full file name. Files are never
    renamed.
    """

    text = song_name(name) if _looks_like_filename(name) else name
    text = _strip_trailing_parentheticals(text)
    return _normalize_ing_words(_match_key(text))


def _strip_trailing_parentheticals(text: str) -> str:
    """Remove trailing ``(…)`` segments used for guests, remasters, etc."""

    previous = None
    while text != previous:
        previous = text
        text = _TRAILING_PAREN.sub("", text).strip()
    return text


def _match_key(text: str) -> str:
    text = text.strip()
    text = text.strip("\"“”‘’'")
    text = text.translate(_DASHES)
    text = text.replace("♯", "#")
    text = _IGNORE_CHARS.sub("", text)
    text = _SEPARATORS.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def _normalize_ing_words(text: str) -> str:
    """Map talkin/blowin/givin to talking/blowing/giving (whole words)."""

    if not text:
        return text
    return " ".join(_ING_EQUIV.get(word, word) for word in text.split(" "))


def _looks_like_filename(name: str) -> bool:
    folded = name.casefold()
    return any(folded.endswith(ext) for ext in _AUDIO_EXTENSIONS)


def _stem(filename: str) -> str:
    # Do not use Path(...).name: a title may contain "/" (e.g. Love/Theft).
    # Live files are already basenames from the scanner.
    name = filename
    folded = name.casefold()
    for extension in _AUDIO_EXTENSIONS:
        if folded.endswith(extension):
            return name[: -len(extension)]
    return name


def _strip_name_marks(stem: str) -> str:
    text = stem
    previous = None
    while text != previous:
        previous = text
        text = _COPY_PREFIX.sub("", text).strip()
        text = _COPY_SUFFIX.sub("", text).strip()
        text = _TRACK_PREFIX.sub("", text, count=1).strip()
    return re.sub(r"\s+", " ", text).strip(" .-_")
