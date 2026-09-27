"""Header reads: duration, bitrate, tags, and files that are skipped."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mutagen.id3 import TALB, TPE1
from mutagen.mp3 import MP3

from mp3missing.model import UNKNOWN_ALBUM, UNKNOWN_ARTIST
from mp3missing.scan import UnreadableMP3, is_audio_filename, is_mp3_filename, read_track, scan_library
from tests.mp3gen import (
    expected_cbr_duration,
    expected_vbr_duration,
    write_cbr_mp3,
    write_vbr_mp3,
)


class FilenameTests(unittest.TestCase):
    def test_extension_is_case_insensitive_and_sidecars_are_skipped(self) -> None:
        self.assertTrue(is_mp3_filename("Song.mp3"))
        self.assertTrue(is_mp3_filename("Song.MP3"))
        self.assertFalse(is_mp3_filename("Song.flac"))
        self.assertFalse(is_mp3_filename("notes.txt"))
        self.assertFalse(is_mp3_filename("._Song.mp3"))
        self.assertTrue(is_audio_filename("Song.m4a"))
        self.assertTrue(is_audio_filename("Song.M4A"))
        self.assertFalse(is_audio_filename("._Song.m4a"))


class ReadTrackTests(unittest.TestCase):
    def test_cbr_duration_and_bitrate_come_from_the_header(self) -> None:
        with TemporaryDirectory() as tmp:
            path = write_cbr_mp3(
                Path(tmp) / "Old Name" / "Airbag.mp3",
                bitrate_kbps=320,
                frames=40,
                artist="Radiohead",
                album="OK Computer",
            )
            track = read_track(path)

        self.assertEqual(track.filename, "Airbag.mp3")
        self.assertEqual(track.bitrate_kbps, 320)
        self.assertAlmostEqual(track.duration, expected_cbr_duration(320, 40), places=6)
        self.assertEqual(track.artist, "Radiohead")
        self.assertEqual(track.album, "OK Computer")

    def test_tags_do_not_change_header_duration(self) -> None:
        with TemporaryDirectory() as tmp:
            plain = write_cbr_mp3(Path(tmp) / "plain.mp3", bitrate_kbps=128, frames=40)
            tagged = write_cbr_mp3(
                Path(tmp) / "tagged.mp3",
                bitrate_kbps=128,
                frames=40,
                artist="Bj\u00f6rk",
                album="Vespertine",
            )
            plain_track = read_track(plain)
            tagged_track = read_track(tagged)

        self.assertAlmostEqual(plain_track.duration, tagged_track.duration, places=6)
        self.assertEqual(plain_track.bitrate_kbps, 128)
        self.assertEqual(tagged_track.bitrate_kbps, 128)
        self.assertEqual(tagged_track.artist, "Bj\u00f6rk")
        self.assertEqual(tagged_track.album, "Vespertine")

    def test_vbr_uses_the_xing_average_bitrate_and_frame_count(self) -> None:
        with TemporaryDirectory() as tmp:
            path = write_vbr_mp3(
                Path(tmp) / "vbr.mp3",
                frames=100,
                audio_bytes=62694,
                artist="Autechre",
                album="LP5",
            )
            track = read_track(path)

        self.assertEqual(track.bitrate_kbps, 192)
        self.assertAlmostEqual(track.duration, expected_vbr_duration(100), places=5)
        self.assertEqual(track.artist, "Autechre")
        self.assertEqual(track.album, "LP5")

    def test_utf16_id3v23_tags_from_mutagen(self) -> None:
        with TemporaryDirectory() as tmp:
            path = write_cbr_mp3(Path(tmp) / "utf16.mp3", bitrate_kbps=192, frames=8)
            audio_file = MP3(path)
            audio_file.add_tags()
            audio_file.tags.add(TPE1(encoding=1, text="Bj\u00f6rk"))
            audio_file.tags.add(TALB(encoding=1, text="Vespertine"))
            audio_file.save(v2_version=3)
            track = read_track(path)
        self.assertEqual(track.artist, "Bj\u00f6rk")
        self.assertEqual(track.album, "Vespertine")
        self.assertEqual(track.bitrate_kbps, 192)

    def test_missing_tags_get_display_labels(self) -> None:
        with TemporaryDirectory() as tmp:
            path = write_cbr_mp3(Path(tmp) / "bare.mp3", bitrate_kbps=192, frames=8)
            track = read_track(path)
        self.assertEqual(track.artist, UNKNOWN_ARTIST)
        self.assertEqual(track.album, UNKNOWN_ALBUM)

    def test_garbage_is_unreadable(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.mp3"
            path.write_bytes(b"this is not audio")
            with self.assertRaises(UnreadableMP3):
                read_track(path)

    def test_id3v1_artist_and_album_are_read(self) -> None:
        with TemporaryDirectory() as tmp:
            path = write_cbr_mp3(Path(tmp) / "v1.mp3", bitrate_kbps=128, frames=8)
            tag = bytearray(b"TAG" + (b"\x00" * 125))
            tag[33:63] = b"Nina Simone".ljust(30, b"\x00")
            tag[63:93] = b"Wild Is the Wind".ljust(30, b"\x00")
            path.write_bytes(path.read_bytes() + bytes(tag))
            track = read_track(path)
        self.assertEqual(track.artist, "Nina Simone")
        self.assertEqual(track.album, "Wild Is the Wind")

    def test_artwork_frame_is_skipped_and_text_after_it_is_kept(self) -> None:
        with TemporaryDirectory() as tmp:
            path = write_cbr_mp3(Path(tmp) / "art.mp3", bitrate_kbps=128, frames=8)
            audio = path.read_bytes()
            path.write_bytes(_id3v24_with_artwork(artist="Alice", album="First") + audio)
            track = read_track(path)
        self.assertEqual(track.artist, "Alice")
        self.assertEqual(track.album, "First")
        self.assertEqual(track.bitrate_kbps, 128)

    def test_id3v23_and_id3v22_text_frames(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            v23 = write_cbr_mp3(root / "v23.mp3", bitrate_kbps=192, frames=8)
            v22 = write_cbr_mp3(root / "v22.mp3", bitrate_kbps=192, frames=8)
            v23.write_bytes(_id3v23(artist="Alice", album="Second") + v23.read_bytes())
            v22.write_bytes(_id3v22(artist="Bob", album="Third") + v22.read_bytes())
            self.assertEqual(read_track(v23).artist, "Alice")
            self.assertEqual(read_track(v23).album, "Second")
            self.assertEqual(read_track(v22).artist, "Bob")
            self.assertEqual(read_track(v22).album, "Third")

    def test_two_artist_values_are_joined(self) -> None:
        with TemporaryDirectory() as tmp:
            path = write_cbr_mp3(Path(tmp) / "split.mp3", bitrate_kbps=128, frames=8)
            body = b"\x03" + "Alice".encode() + b"\x00" + "Bob".encode()
            frame = b"TPE1" + _synchsafe(len(body)) + b"\x00\x00" + body
            album = _text_frame_v24(b"TALB", "Shared")
            tag = _tag_v24(frame + album)
            path.write_bytes(tag + path.read_bytes())
            track = read_track(path)
        self.assertEqual(track.artist, "Alice, Bob")
        self.assertEqual(track.album, "Shared")


class ScanLibraryTests(unittest.TestCase):
    def test_walks_subfolders_and_ignores_non_mp3_and_sidecars(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_cbr_mp3(
                root / "Artist" / "Album" / "Keep.mp3",
                bitrate_kbps=320,
                frames=8,
                artist="Keep Artist",
                album="Keep Album",
            )
            write_cbr_mp3(root / "Other" / "Also.MP3", bitrate_kbps=128, frames=8)
            (root / "Artist" / "cover.jpg").write_bytes(b"jpeg")
            (root / "notes.txt").write_bytes(b"hello")
            (root / "Artist" / "._Keep.mp3").write_bytes(b"sidecar")
            (root / "broken.mp3").write_bytes(b"nope")

            result = scan_library(root)

        names = sorted(track.filename for track in result.tracks)
        self.assertEqual(names, ["Also.MP3", "Keep.mp3"])
        self.assertEqual([path.name for path, _reason in result.unreadable], ["broken.mp3"])
        keep = next(track for track in result.tracks if track.filename == "Keep.mp3")
        self.assertEqual(keep.artist, "Keep Artist")
        self.assertEqual(keep.bitrate_kbps, 320)

    def test_reads_m4a_artist_album_duration_and_bitrate(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "tiny.m4a"
        track = read_track(fixture)
        self.assertEqual(track.filename, "tiny.m4a")
        self.assertEqual(track.artist, "Fixture Artist")
        self.assertEqual(track.album, "Fixture Album")
        self.assertAlmostEqual(track.duration, 0.323, places=2)
        self.assertGreater(track.bitrate_kbps, 0)


def _synchsafe(size: int) -> bytes:
    return bytes(
        (
            (size >> 21) & 0x7F,
            (size >> 14) & 0x7F,
            (size >> 7) & 0x7F,
            size & 0x7F,
        )
    )


def _text_frame_v24(frame_id: bytes, text: str) -> bytes:
    body = b"\x03" + text.encode("utf-8")
    return frame_id + _synchsafe(len(body)) + b"\x00\x00" + body


def _tag_v24(frames: bytes) -> bytes:
    return b"ID3" + bytes((4, 0, 0)) + _synchsafe(len(frames)) + frames


def _id3v24_with_artwork(artist: str, album: str) -> bytes:
    artwork = b"APIC" + _synchsafe(80_000) + b"\x00\x00" + (b"\x00" * 80_000)
    frames = artwork + _text_frame_v24(b"TPE1", artist) + _text_frame_v24(b"TALB", album)
    return _tag_v24(frames)


def _text_frame_v23(frame_id: bytes, text: str) -> bytes:
    body = b"\x03" + text.encode("utf-8")
    return frame_id + len(body).to_bytes(4, "big") + b"\x00\x00" + body


def _id3v23(artist: str, album: str) -> bytes:
    frames = _text_frame_v23(b"TPE1", artist) + _text_frame_v23(b"TALB", album)
    return b"ID3" + bytes((3, 0, 0)) + _synchsafe(len(frames)) + frames


def _id3v22(artist: str, album: str) -> bytes:
    def frame(frame_id: bytes, text: str) -> bytes:
        body = b"\x00" + text.encode("latin-1")
        return frame_id + len(body).to_bytes(3, "big") + body

    frames = frame(b"TP1", artist) + frame(b"TAL", album)
    return b"ID3" + bytes((2, 0, 0)) + _synchsafe(len(frames)) + frames


if __name__ == "__main__":
    unittest.main()
