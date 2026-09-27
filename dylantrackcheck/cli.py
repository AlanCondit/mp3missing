"""Command-line check of live Bob Dylan album track listings.

Only albums that exist in the live library (folders named
``YYYY - Album Title``) are checked against the bundled studio catalog.
Albums you do not have are ignored.

Stdout is a short human report. The spreadsheet path defaults to
``dylan-track-check.xlsx`` in the current folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dylantrackcheck.compare import CheckReport, check_live_albums
from dylantrackcheck.sheet import write_xlsx


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dylantrackcheck",
        description=(
            "For Bob Dylan albums present in a live Music library, check "
            "that each YYYY - Album folder's audio files match the studio "
            "track listing. Albums not on disk are skipped."
        ),
    )
    parser.add_argument(
        "live",
        help=(
            "live Music library folder, or the Bob Dylan artist folder "
            "(read only)"
        ),
    )
    parser.add_argument(
        "--xlsx",
        default="dylan-track-check.xlsx",
        help=(
            "spreadsheet to write "
            "(default: dylan-track-check.xlsx in the current folder)"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    args = parse_args(argv)
    live = Path(args.live).expanduser().absolute()
    print("dylantrackcheck: started", file=sys.stderr, flush=True)

    try:
        exists = live.exists()
        is_dir = live.is_dir() if exists else False
    except OSError as exc:
        print(f"error: live folder could not be read: {exc}", file=sys.stderr)
        return 2
    if not exists:
        print(f"error: live folder does not exist: {live}", file=sys.stderr)
        return 2
    if not is_dir:
        print(f"error: live path is not a folder: {live}", file=sys.stderr)
        return 2

    try:
        report = check_live_albums(live)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    xlsx_path = Path(args.xlsx).expanduser()
    if not xlsx_path.is_absolute():
        xlsx_path = Path.cwd() / xlsx_path
    write_xlsx(xlsx_path, report)
    _print_report(report, xlsx_path)
    return 0


def _print_report(report: CheckReport, xlsx_path: Path) -> None:
    print(f"Dylan folder: {report.dylan_root}")
    print(f"Albums checked: {report.albums_checked}")
    print(f"Albums OK: {report.albums_ok}")
    print(f"Albums with mismatches: {report.albums_with_issues}")
    if report.unmatched_live:
        print(
            f"Live folders not in studio catalog: {len(report.unmatched_live)}"
        )
    print()

    for result in report.results:
        if result.ok:
            print(
                f"OK  {result.album_folder} "
                f"({result.matched_count}/{result.expected_count})"
            )
            continue
        print(
            f"MISMATCH  {result.album_folder} "
            f"(missing {result.missing_count}, extra {result.extra_count})"
        )
        for issue in result.issues:
            if issue.issue == "missing from live":
                print(f"  - missing: {issue.expected_track}")
            else:
                print(f"  - extra:   {issue.live_file}")

    if report.unmatched_live:
        print()
        print("Not in studio catalog (skipped for track matching):")
        for album in report.unmatched_live:
            print(f"  - {album.path.name} ({len(album.tracks)} files)")

    print()
    print(f"Wrote {xlsx_path}")


if __name__ == "__main__":
    raise SystemExit(main())
