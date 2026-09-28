"""Compare live Dylan album folders to the studio catalog.

Only albums present in the live library are checked. Catalog albums that
are not on disk are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dylantrackcheck.catalog import ExpectedAlbum, load_catalog
from dylantrackcheck.names import album_key, is_title_prefix, keys_match, track_key
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

    live_remaining = list(enumerate(live_keys))
    matched = 0

    # Pass 1: exact key, or one title is the other plus a trailing word (now).
    still_expected: list[tuple[int, str]] = []
    for exp_i, exp_key in enumerate(expected_keys):
        found_at = None
        for live_pos, (live_i, live_key) in enumerate(live_remaining):
            if keys_match(exp_key, live_key):
                found_at = live_pos
                break
        if found_at is None:
            still_expected.append((exp_i, exp_key))
        else:
            live_remaining.pop(found_at)
            matched += 1

    # Pass 2 (same album only): whole-word prefix when exactly one live file
    # on this album could match that expected track (and that file is not a
    # prefix candidate for any other remaining expected track).
    still_expected, live_remaining, prefix_hits = _unique_prefix_matches(
        still_expected, live_remaining
    )
    matched += prefix_hits

    issues: list[TrackIssue] = []
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


def _unique_prefix_matches(
    still_expected: list[tuple[int, str]],
    live_remaining: list[tuple[int, str]],
) -> tuple[list[tuple[int, str]], list[tuple[int, str]], int]:
    """Match when one cleaned title prefixes the other and the pair is unique."""

    if not still_expected or not live_remaining:
        return still_expected, live_remaining, 0

    # expected_index -> list of positions in live_remaining
    candidates: dict[int, list[int]] = {}
    for exp_pos, (_exp_i, exp_key) in enumerate(still_expected):
        hits = [
            live_pos
            for live_pos, (_live_i, live_key) in enumerate(live_remaining)
            if is_title_prefix(exp_key, live_key)
        ]
        if hits:
            candidates[exp_pos] = hits

    # live_remaining position -> expected positions that list it
    claimed_by: dict[int, list[int]] = {}
    for exp_pos, live_positions in candidates.items():
        for live_pos in live_positions:
            claimed_by.setdefault(live_pos, []).append(exp_pos)

    matched_exp: set[int] = set()
    matched_live: set[int] = set()
    for exp_pos, live_positions in candidates.items():
        if len(live_positions) != 1:
            continue
        live_pos = live_positions[0]
        if len(claimed_by.get(live_pos, ())) != 1:
            continue
        matched_exp.add(exp_pos)
        matched_live.add(live_pos)

    if not matched_exp:
        return still_expected, live_remaining, 0

    new_expected = [
        item for pos, item in enumerate(still_expected) if pos not in matched_exp
    ]
    new_live = [
        item for pos, item in enumerate(live_remaining) if pos not in matched_live
    ]
    return new_expected, new_live, len(matched_exp)
