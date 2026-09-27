"""Matching rules: file name, duration, bitrate, and sort order."""

from __future__ import annotations

import time
import unittest
from pathlib import Path

from mp3missing.compare import find_missing, name_key, song_name
from mp3missing.model import Track


def track(
    filename: str,
    duration: float,
    bitrate: int,
    artist: str = "Artist",
    album: str = "Album",
    directory: str = "/music",
) -> Track:
    return Track(
        path=Path(directory) / filename,
        filename=filename,
        duration=duration,
        bitrate_kbps=bitrate,
        artist=artist,
        album=album,
    )


class NameKeyTests(unittest.TestCase):
    def test_casefold_and_unicode_normalization(self) -> None:
        self.assertEqual(name_key("Song.mp3"), name_key("song.MP3"))
        nfc = "Caf\u00e9.mp3"
        nfd = "Cafe\u0301.mp3"
        self.assertNotEqual(nfc, nfd)
        self.assertEqual(name_key(nfc), name_key(nfd))

    def test_track_numbers_and_copy_markers_are_the_same_song(self) -> None:
        self.assertEqual(song_name("01 - Airbag.mp3"), "Airbag")
        self.assertEqual(song_name("01 Airbag.m4a"), "Airbag")
        self.assertEqual(song_name("1-01 Airbag copy 2.mp3"), "Airbag")
        self.assertEqual(song_name("Copy of Airbag.mp3"), "Airbag")
        self.assertEqual(name_key("01 - Airbag.mp3"), name_key("Airbag copy.m4a"))
        self.assertNotEqual(name_key("19-2000.mp3"), name_key("2000.mp3"))
        self.assertEqual(name_key("1979.mp3"), name_key("1979.m4a"))

    def test_track_number_and_copy_do_not_count_as_missing(self) -> None:
        archive = [track("01 - Airbag.mp3", 241.2, 320, "Radiohead", "OK Computer")]
        live = [track("Airbag copy.m4a", 241.0, 320, directory="/live")]
        self.assertEqual(find_missing(archive, live), [])


class FindMissingTests(unittest.TestCase):
    def test_same_recording_in_another_folder_is_not_missing(self) -> None:
        archive = [track("Airbag.mp3", 241.2, 320, "Radiohead", "OK Computer", "/archive/old")]
        live = [track("Airbag.mp3", 241.2, 320, "Renamed", "Renamed Album", "/live/new")]
        self.assertEqual(find_missing(archive, live), [])

    def test_file_name_match_is_case_insensitive(self) -> None:
        archive = [track("Airbag.mp3", 241.2, 320)]
        live = [track("airbag.MP3", 241.0, 320, directory="/live")]
        self.assertEqual(find_missing(archive, live), [])

    def test_accent_normalization_does_not_look_like_a_different_file(self) -> None:
        archive = [track("Caf\u00e9.mp3", 180.0, 192)]
        live = [track("Cafe\u0301.mp3", 180.0, 192, directory="/live")]
        self.assertEqual(find_missing(archive, live), [])

    def test_duration_within_one_second_matches(self) -> None:
        archive = [track("Song.mp3", 100.0, 320)]
        live = [track("Song.mp3", 101.0, 320, directory="/live")]
        self.assertEqual(find_missing(archive, live, tolerance=1.0), [])

    def test_duration_just_over_tolerance_is_missing(self) -> None:
        archive = [track("Song.mp3", 100.0, 320)]
        live = [track("Song.mp3", 101.01, 320, directory="/live")]
        missing = find_missing(archive, live, tolerance=1.0)
        self.assertEqual([item.filename for item in missing], ["Song.mp3"])

    def test_different_bitrate_is_missing_even_when_name_and_duration_match(self) -> None:
        archive = [track("Song.mp3", 200.0, 320)]
        live = [track("Song.mp3", 200.0, 128, directory="/live")]
        missing = find_missing(archive, live)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].bitrate_kbps, 320)

    def test_different_file_name_is_missing(self) -> None:
        archive = [track("Album Version.mp3", 200.0, 320)]
        live = [track("Single Version.mp3", 200.0, 320, directory="/live")]
        self.assertEqual(len(find_missing(archive, live)), 1)

    def test_artist_and_album_tags_do_not_affect_identity(self) -> None:
        archive = [track("Song.mp3", 180.0, 192, "Old Artist", "Old Album")]
        live = [track("Song.mp3", 180.0, 192, "New Artist", "New Album", "/live/renamed/renamed")]
        self.assertEqual(find_missing(archive, live), [])

    def test_live_only_files_are_not_listed(self) -> None:
        live = [track("Only Live.mp3", 180.0, 192, directory="/live")]
        self.assertEqual(find_missing([], live), [])

    def test_one_live_copy_covers_duplicate_archive_copies(self) -> None:
        archive = [
            track("Song.mp3", 180.0, 192, directory="/archive/cd1"),
            track("Song.mp3", 180.0, 192, directory="/archive/cd2"),
        ]
        live = [track("Song.mp3", 180.0, 192, directory="/live")]
        self.assertEqual(find_missing(archive, live), [])

    def test_match_can_be_any_live_file_with_that_name(self) -> None:
        archive = [track("Song.mp3", 180.0, 320)]
        live = [
            track("Song.mp3", 180.0, 128, directory="/live/low"),
            track("Song.mp3", 90.0, 320, directory="/live/short"),
            track("Song.mp3", 180.4, 320, directory="/live/right"),
        ]
        self.assertEqual(find_missing(archive, live), [])

    def test_none_of_the_same_name_candidates_match(self) -> None:
        archive = [track("Song.mp3", 180.0, 320)]
        live = [
            track("Song.mp3", 180.0, 128, directory="/live/low"),
            track("Song.mp3", 400.0, 320, directory="/live/long"),
        ]
        self.assertEqual(len(find_missing(archive, live)), 1)

    def test_sort_is_artist_then_album_then_filename_case_insensitive(self) -> None:
        archive = [
            track("z.mp3", 10, 128, "Zebra", "Late"),
            track("b.mp3", 10, 128, "Same", "C"),
            track("a.mp3", 10, 128, "Same", "b"),
            track("m.mp3", 10, 128, "aardvark", "Beta"),
            track("m.mp3", 10, 128, "Aardvark", "Alpha", "/other"),
        ]
        missing = find_missing(archive, [])
        self.assertEqual(
            [(item.artist, item.album, item.filename) for item in missing],
            [
                ("Aardvark", "Alpha", "m.mp3"),
                ("aardvark", "Beta", "m.mp3"),
                ("Same", "b", "a.mp3"),
                ("Same", "C", "b.mp3"),
                ("Zebra", "Late", "z.mp3"),
            ],
        )

    def test_negative_tolerance_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            find_missing([], [], tolerance=-0.1)

    def test_twelve_thousand_files_match_quickly(self) -> None:
        archive = [
            track(f"{index}.mp3", 100.0, 320, "A", "B", f"/archive/{index}")
            for index in range(12000)
        ]
        live = [
            track(f"{index}.mp3", 100.5, 320, "Other", "Other", f"/live/{index}")
            for index in range(11990)
        ]
        started = time.perf_counter()
        missing = find_missing(archive, live)
        elapsed = time.perf_counter() - started
        self.assertEqual([item.filename for item in missing], [f"{index}.mp3" for index in range(11990, 12000)])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
