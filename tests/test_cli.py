"""The report lists archive files the live library does not have."""

from __future__ import annotations

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from mp3missing.cli import main
from mp3missing.compare import find_missing
from mp3missing.scan import scan_library
from tests.mp3gen import expected_cbr_duration, write_cbr_mp3

ROOT = Path(__file__).resolve().parent.parent


class LibraryReportTests(unittest.TestCase):
    def test_generated_libraries_match_on_headers_and_sort_the_gaps(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "archive"
            live = Path(tmp) / "live"

            # Same recording, renamed folders and tags, different case.
            write_cbr_mp3(
                archive / "Old Artist" / "Old Album" / "Shared.mp3",
                bitrate_kbps=128,
                frames=40,
                artist="Zebra",
                album="Late",
            )
            write_cbr_mp3(
                live / "New Artist" / "New Album" / "shared.mp3",
                bitrate_kbps=128,
                frames=40,
                artist="Not Used",
                album="Not Used",
            )

            # Duration difference is under one second: 4 frames vs 40.
            write_cbr_mp3(
                archive / "Old Artist" / "Old Album" / "Near.mp3",
                bitrate_kbps=128,
                frames=4,
                artist="Zebra",
                album="Late",
            )
            write_cbr_mp3(
                live / "New Artist" / "New Album" / "near.mp3",
                bitrate_kbps=128,
                frames=40,
            )
            self.assertLess(
                abs(expected_cbr_duration(128, 40) - expected_cbr_duration(128, 4)),
                1.0,
            )

            # Duration difference is over one second: 4 frames vs 44.
            write_cbr_mp3(
                archive / "A" / "B" / "Long.mp3",
                bitrate_kbps=128,
                frames=4,
                artist="Aardvark",
                album="Alpha",
            )
            write_cbr_mp3(
                live / "Renamed" / "Renamed" / "long.mp3",
                bitrate_kbps=128,
                frames=44,
            )
            self.assertGreater(
                abs(expected_cbr_duration(128, 44) - expected_cbr_duration(128, 4)),
                1.0,
            )

            # Same name and duration, different quality.
            write_cbr_mp3(
                archive / "A" / "B" / "Low.mp3",
                bitrate_kbps=128,
                frames=40,
                artist="Aardvark",
                album="Alpha",
            )
            write_cbr_mp3(
                live / "Renamed" / "Renamed" / "Low.mp3",
                bitrate_kbps=320,
                frames=40,
            )

            # Archive only.
            write_cbr_mp3(
                archive / "Somewhere" / "Else" / "Only.mp3",
                bitrate_kbps=320,
                frames=40,
                artist="Aardvark",
                album="Beta",
            )

            # Live only. Must not be reported.
            write_cbr_mp3(
                live / "Renamed" / "Renamed" / "Extra.mp3",
                bitrate_kbps=192,
                frames=40,
                artist="Live Only",
                album="Live Only",
            )
            (archive / "Old Artist" / "notes.txt").write_text("not audio", encoding="utf-8")
            (archive / "bad.mp3").write_bytes(b"not an mp3")

            archive_scan = scan_library(archive)
            live_scan = scan_library(live)
            missing = find_missing(archive_scan.tracks, live_scan.tracks)

            self.assertEqual(
                [(item.artist, item.album, item.filename, item.bitrate_kbps) for item in missing],
                [
                    ("Aardvark", "Alpha", "Long.mp3", 128),
                    ("Aardvark", "Alpha", "Low.mp3", 128),
                    ("Aardvark", "Beta", "Only.mp3", 320),
                ],
            )
            long = missing[0]
            self.assertAlmostEqual(long.duration, expected_cbr_duration(128, 4), places=6)
            self.assertEqual([path.name for path, _reason in archive_scan.unreadable], ["bad.mp3"])

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([str(archive), str(live)])

        self.assertEqual(code, 0)
        report = stdout.getvalue()
        self.assertIn("Missing from the live library: 3", report)
        self.assertLess(report.index("Aardvark"), report.index("Alpha"))
        self.assertLess(report.index("Long.mp3"), report.index("Low.mp3"))
        self.assertLess(report.index("Low.mp3"), report.index("Beta"))
        self.assertLess(report.index("Beta"), report.index("Only.mp3"))
        self.assertIn("duration:", report)
        self.assertIn("quality:  128 kbps", report)
        self.assertIn("quality:  320 kbps", report)
        self.assertNotIn("Shared.mp3", report)
        self.assertNotIn("Near.mp3", report)
        self.assertNotIn("Extra.mp3", report)
        self.assertNotIn("Not Used", report)
        summary = stderr.getvalue()
        self.assertIn("Missing: 3", summary)
        self.assertIn("bad.mp3", summary)
        self.assertIn("1 unreadable", summary)

    def test_empty_gap_is_a_clear_sentence(self) -> None:
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_cbr_mp3(folder / "a" / "Song.mp3", bitrate_kbps=192, frames=8)
            write_cbr_mp3(folder / "b" / "song.mp3", bitrate_kbps=192, frames=8)
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                code = main([str(folder / "a"), str(folder / "b")])
        self.assertEqual(code, 0)
        self.assertIn("No archive MP3s are missing", stdout.getvalue())

    def test_file_instead_of_folder_is_an_error(self) -> None:
        with TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "not-a-folder"
            file_path.write_text("x", encoding="utf-8")
            folder = Path(tmp) / "folder"
            folder.mkdir()
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main([str(file_path), str(folder)])
        self.assertEqual(code, 2)
        self.assertIn("not a folder", stderr.getvalue())

    def test_missing_folder_is_an_error(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["/no/such/archive", "/no/such/live"])
        self.assertEqual(code, 2)
        self.assertIn("does not exist", stderr.getvalue())

    def test_same_folder_is_an_error(self) -> None:
        with TemporaryDirectory() as tmp:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main([tmp, tmp])
        self.assertEqual(code, 2)
        self.assertIn("same", stderr.getvalue())

    def test_module_entry_point(self) -> None:
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "archive"
            live = Path(tmp) / "live"
            write_cbr_mp3(
                archive / "Only.mp3",
                bitrate_kbps=320,
                frames=8,
                artist="Ada",
                album="One",
            )
            live.mkdir()
            completed = subprocess.run(
                [sys.executable, "-m", "mp3missing", str(archive), str(live)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Ada", completed.stdout)
        self.assertIn("Only.mp3", completed.stdout)
        self.assertIn("320 kbps", completed.stdout)


if __name__ == "__main__":
    unittest.main()
