"""Compare live Dylan album folders to the studio catalog.

Only albums present in the live library are checked. Catalog albums that
are not on disk are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dylantrackcheck.catalog import ExpectedAlbum, load_catalog
from dylantrackcheck.names import album_key, track_key
from dylantrackcheck.scan import LiveAlbum, find_dylan_root, scan_live_albums


@dataclass(frozen=True)
class TrackIssue:
    """One mismatch for a live album that exists in the catalog."""

    album_year: int
    album_title: str
    album_folder: str
    issue: str
    expected_track: str
    live_file: str


@dataclass(frozen=True)
class AlbumResult:
    album_year: int
    album_title: str
    album_folder: str
    expected_count: int
    live_count: int
    missing_count: int
    extra_count: int
    matched_count: int
    issues: tuple[TrackIssue, ...]

    @property
    def ok(self) -> bool:
        return self.missing_count == 0 and self.extra_count == 0


@dataclass(frozen=True)
class CheckReport:
    dylan_root: Path
    results: tuple[AlbumResult, ...]
    unmatched_live: tuple[LiveAlbum, ...]

    @property
    def albums_checked(self) -> int:
        return len(self.results)

    @property
    def albums_ok(self) -> int:
        return sum(1 for result in self.results if result.ok)

    @property
    def albums_with_issues(self) -> int:
        return sum(1 for result in self.results if not result.ok)


def check_live_albums(
    live_root: Path,
    catalog: list[ExpectedAlbum] | None = None,
) -> CheckReport:
    """Check track listings for Dylan albums present under ``live_root``.

    ``live_root`` may be the Music library folder or the Bob Dylan artist
    folder. Album folders must be named ``YYYY - Album Title``.
    """

    if catalog is None:
        catalog = load_catalog()

    dylan_root = find_dylan_root(live_root)
    live_albums = scan_live_albums(dylan_root)
    by_key = _catalog_index(catalog)

    results: list[AlbumResult] = []
    unmatched: list[LiveAlbum] = []
    for live in live_albums:
        expected = by_key.get((live.year, album_key(live.title)))
        if expected is None:
            # Year in the folder can differ from the catalog year; try title only.
            expected = by_key.get((-1, album_key(live.title)))
        if expected is None:
            unmatched.append(live)
            continue
        results.append(_compare_album(live, expected))

    results.sort(key=lambda r: (r.album_year, album_key(r.album_title)))
    unmatched.sort(key=lambda a: (a.year, album_key(a.title)))
    return CheckReport(
        dylan_root=dylan_root,
        results=tuple(results),
        unmatched_live=tuple(unmatched),
    )


def _catalog_index(
    catalog: list[ExpectedAlbum],
) -> dict[tuple[int, str], ExpectedAlbum]:
    index: dict[tuple[int, str], ExpectedAlbum] = {}
    for album in catalog:
        key = album_key(album.title)
        index[(album.year, key)] = album
        # Title-only fallback for a mismatched year prefix on disk.
        index.setdefault((-1, key), album)
    return index


def _compare_album(live: LiveAlbum, expected: ExpectedAlbum) -> AlbumResult:
    expected_keys = [track_key(track.title) for track in expected.tracks]
    live_keys = [track_key(track.filename) for track in live.tracks]

    expected_remaining = list(enumerate(expected_keys))
    live_remaining = list(enumerate(live_keys))
    matched = 0
    issues: list[TrackIssue] = []

    # Greedy one-to-one match on normalized titles.
    still_expected: list[tuple[int, str]] = []
    for exp_i, exp_key in expected_remaining:
        found_at = None
        for live_pos, (live_i, live_key) in enumerate(live_remaining):
            if live_key == exp_key:
                found_at = live_pos
                break
        if found_at is None:
            still_expected.append((exp_i, exp_key))
        else:
            live_remaining.pop(found_at)
            matched += 1

    for exp_i, _exp_key in still_expected:
        track = expected.tracks[exp_i]
        issues.append(
            TrackIssue(
                album_year=live.year,
                album_title=expected.title,
                album_folder=live.path.name,
                issue="missing from live",
                expected_track=track.title,
                live_file="",
            )
        )

    for live_i, _live_key in live_remaining:
        track = live.tracks[live_i]
        issues.append(
            TrackIssue(
                album_year=live.year,
                album_title=expected.title,
                album_folder=live.path.name,
                issue="extra on live",
                expected_track="",
                live_file=track.filename,
            )
        )

    issues.sort(key=lambda i: (i.issue, i.expected_track.casefold(), i.live_file.casefold()))
    return AlbumResult(
        album_year=live.year,
        album_title=expected.title,
        album_folder=live.path.name,
        expected_count=len(expected.tracks),
        live_count=len(live.tracks),
        missing_count=sum(1 for i in issues if i.issue == "missing from live"),
        extra_count=sum(1 for i in issues if i.issue == "extra on live"),
        matched_count=matched,
        issues=tuple(issues),
    )
