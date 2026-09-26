"""One MP3, as far as this tool cares about it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# MPEG header durations for the same recording can differ by a fraction of
# a second (ID3 padding, a missing Xing header, integer frame sizes).
# One second absorbs that. A different edit is still longer or shorter
# than that, so it stays a different file.
DURATION_TOLERANCE_SECONDS = 1.0

# Used only when the archive file has no artist or album tag.
# These labels are what the report sorts and prints.
UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"


@dataclass(frozen=True)
class Track:
    """An MP3 that was read from disk.

    ``artist`` and ``album`` come from tags and are for display.
    They are not part of the match.
    """

    path: Path
    filename: str
    duration: float
    bitrate_kbps: int
    artist: str
    album: str
