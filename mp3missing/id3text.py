"""Read the artist and album tags from an MP3.

Only the text frames are decoded. Embedded artwork (APIC) and every
other frame are skipped by seeking past them, so a library of thousands
of files does not load cover images into memory.

Duration and bitrate are not read here. See ``scan.py``.

Unusual tags (unsynchronised, or a compressed artist/album frame) fall
back to mutagen for that one file.
"""

from __future__ import annotations

from pathlib import Path

from mutagen import MutagenError
from mutagen.id3 import ID3, ID3NoHeaderError

_ARTIST_IDS = {b"TPE1", b"TP1"}
_ALBUM_IDS = {b"TALB", b"TAL"}


class _UnsupportedTag(Exception):
    """The light parser will not handle this tag. Use mutagen."""


def artist_and_album(path: Path) -> tuple[str, str]:
    """Return ``(artist, album)`` from ID3, or empty strings if absent.

    ID3v2 wins over ID3v1. Empty strings mean the tag was not there;
    the caller supplies the display labels.
    """

    try:
        with path.open("rb") as handle:
            return _read_id3_text(handle)
    except _UnsupportedTag:
        return _read_with_mutagen(path)
    except OSError:
        return "", ""


def _read_with_mutagen(path: Path) -> tuple[str, str]:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        return "", ""
    except MutagenError:
        return "", ""
    return _mutagen_text(tags, "TPE1"), _mutagen_text(tags, "TALB")


def _mutagen_text(tags: ID3, key: str) -> str:
    if key not in tags:
        return ""
    parts = [str(value).strip() for value in tags[key].text if str(value).strip()]
    return ", ".join(parts)


def _read_id3_text(handle) -> tuple[str, str]:
    artist, album = _read_id3v2(handle)
    if artist and album:
        return artist, album
    v1_artist, v1_album = _read_id3v1(handle)
    return artist or v1_artist, album or v1_album


def _read_id3v2(handle) -> tuple[str, str]:
    handle.seek(0)
    header = handle.read(10)
    if len(header) < 10 or header[0:3] != b"ID3":
        return "", ""

    major = header[3]
    flags = header[5]
    if major not in (2, 3, 4):
        raise _UnsupportedTag(f"ID3v2.{major} is not supported")
    if flags & 0x80:
        raise _UnsupportedTag("unsynchronised ID3 tag")
    if major == 2 and flags & 0x40:
        raise _UnsupportedTag("compressed ID3v2.2 tag")

    tag_size = _synchsafe(header[6:10])
    tag_end = 10 + tag_size
    handle.seek(0, 2)
    if tag_end > handle.tell():
        raise _UnsupportedTag("ID3 tag size extends past the file")
    handle.seek(10)

    if major >= 3 and flags & 0x40:
        _skip_extended_header(handle, major, tag_end)

    if major == 2:
        id_len, size_len, flag_len = 3, 3, 0
    else:
        id_len, size_len, flag_len = 4, 4, 2

    artist = ""
    album = ""
    header_len = id_len + size_len + flag_len
    while handle.tell() + header_len <= tag_end:
        frame_id = handle.read(id_len)
        if len(frame_id) < id_len or frame_id[0:1] == b"\x00":
            break
        raw_size = handle.read(size_len)
        if major == 4:
            frame_size = _synchsafe(raw_size)
        else:
            frame_size = int.from_bytes(raw_size, "big")
        frame_flags = handle.read(flag_len) if flag_len else b""
        start = handle.tell()
        if frame_size < 0 or start + frame_size > tag_end:
            raise _UnsupportedTag("ID3 frame extends past the tag")

        wanted = frame_id in _ARTIST_IDS or frame_id in _ALBUM_IDS
        if wanted and frame_flags not in (b"", b"\x00\x00"):
            raise _UnsupportedTag(f"{frame_id!r} is compressed or flagged")
        if not wanted:
            handle.seek(start + frame_size)
            continue

        text = _decode_text_frame(handle.read(frame_size))
        if frame_id in _ARTIST_IDS and not artist:
            artist = text
        elif frame_id in _ALBUM_IDS and not album:
            album = text
        if artist and album:
            break

    return artist, album


def _skip_extended_header(handle, major: int, tag_end: int) -> None:
    size_field = handle.read(4)
    if len(size_field) != 4:
        raise _UnsupportedTag("truncated ID3 extended header")
    if major == 4:
        # v2.4 size includes these four bytes and is synchsafe.
        ext_size = _synchsafe(size_field)
        if ext_size < 6:
            raise _UnsupportedTag("ID3v2.4 extended header is too small")
        remaining = ext_size - 4
    else:
        # v2.3 size excludes these four bytes and is a plain integer.
        remaining = int.from_bytes(size_field, "big")
    if handle.tell() + remaining > tag_end:
        raise _UnsupportedTag("ID3 extended header extends past the tag")
    handle.seek(remaining, 1)


def _read_id3v1(handle) -> tuple[str, str]:
    handle.seek(0, 2)
    if handle.tell() < 128:
        return "", ""
    handle.seek(-128, 2)
    blob = handle.read(128)
    if blob[:3] != b"TAG":
        return "", ""
    return _latin1_field(blob[33:63]), _latin1_field(blob[63:93])


def _latin1_field(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin-1", errors="replace").strip()


def _decode_text_frame(data: bytes) -> str:
    if not data:
        return ""
    encoding = data[0]
    payload = data[1:]
    if encoding == 0:
        text = payload.decode("latin-1", errors="replace")
    elif encoding == 1:
        text = payload.decode("utf-16", errors="replace")
    elif encoding == 2:
        text = payload.decode("utf-16-be", errors="replace")
    elif encoding == 3:
        text = payload.decode("utf-8", errors="replace")
    else:
        raise _UnsupportedTag(f"unknown text encoding {encoding}")
    parts = [part.strip() for part in text.split("\x00") if part.strip()]
    return ", ".join(parts)


def _synchsafe(data: bytes) -> int:
    value = 0
    for byte in data:
        if byte & 0x80:
            raise _UnsupportedTag("ID3 size is not synchsafe")
        value = (value << 7) | byte
    return value
