"""Build tiny MP3s for tests.

The files are real MPEG frames with a valid header, not a decoded
waveform. mutagen reads duration from the frame size and bitrate from
the header, which is the same path used on a real library.

Constant-bitrate duration (no Xing header), which is what mutagen
reports for these files::

    seconds = 8 * frame_count * frame_length / bitrate_bps

``frame_length`` is the MPEG1 Layer III formula
``(144 * bitrate) // 44100``.
"""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import TALB, TPE1
from mutagen.mp3 import MP3

SAMPLE_RATE = 44100

# Third header byte: bitrate index, 44100 Hz, no padding.
_BITRATE_BYTE = {
    128: 0x90,
    192: 0xB0,
    320: 0xE0,
}


def frame_length(bitrate_kbps: int, sample_rate: int = SAMPLE_RATE) -> int:
    return (144 * bitrate_kbps * 1000) // sample_rate


def expected_cbr_duration(bitrate_kbps: int, frames: int) -> float:
    bitrate_bps = bitrate_kbps * 1000
    return 8 * frames * frame_length(bitrate_kbps) / bitrate_bps


def write_cbr_mp3(
    path: Path,
    *,
    bitrate_kbps: int,
    frames: int,
    artist: str | None = None,
    album: str | None = None,
) -> Path:
    """Write a constant-bitrate MP3 of ``frames`` silent frames.

    At least four frames lets mutagen accept the header without a Xing tag.
    """

    if bitrate_kbps not in _BITRATE_BYTE:
        raise ValueError(f"test generator has no header for {bitrate_kbps} kbps")
    if frames < 4:
        raise ValueError("write at least 4 frames so the header is accepted")

    header = bytes([0xFF, 0xFB, _BITRATE_BYTE[bitrate_kbps], 0x00])
    length = frame_length(bitrate_kbps)
    frame = header + (b"\x00" * (length - 4))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(frame * frames)
    if artist is not None or album is not None:
        _write_tags(path, artist, album)
    return path


def write_vbr_mp3(
    path: Path,
    *,
    frames: int = 100,
    audio_bytes: int = 62694,
    artist: str | None = None,
    album: str | None = None,
) -> Path:
    """Write one MPEG frame with a Xing header.

    The first-frame header says 128 kbps so the frame is a legal size.
    mutagen replaces that with the average bitrate from the Xing
    frame and byte counts. ``audio_bytes=62694`` and ``frames=100``
    average to 192 kbps at 44100 Hz.
    """

    container = frame_length(128)
    buf = bytearray(container)
    buf[0:4] = bytes([0xFF, 0xFB, _BITRATE_BYTE[128], 0x00])
    flags = 0x1 | 0x2 | 0x8  # frames, bytes, vbr scale
    xing = b"Xing" + flags.to_bytes(4, "big")
    xing += frames.to_bytes(4, "big")
    xing += (audio_bytes + container).to_bytes(4, "big")
    xing += (78).to_bytes(4, "big")
    buf[36 : 36 + len(xing)] = xing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf)
    if artist is not None or album is not None:
        _write_tags(path, artist, album)
    return path


def expected_vbr_duration(frames: int, sample_rate: int = SAMPLE_RATE) -> float:
    return frames * 1152 / sample_rate


def _write_tags(path: Path, artist: str | None, album: str | None) -> None:
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    if artist is not None:
        audio.tags.add(TPE1(encoding=3, text=artist))
    if album is not None:
        audio.tags.add(TALB(encoding=3, text=album))
    audio.save()
