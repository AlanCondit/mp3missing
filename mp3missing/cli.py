"""Command-line report of archive MP3s missing from a live library.

Stdout is the missing list, grouped by archive artist and album.
Stderr is the short summary and any files that could not be read.
The tool only reads the two folders. It does not change either library.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mp3missing.compare import find_missing
from mp3missing.model import DURATION_TOLERANCE_SECONDS, Track
from mp3missing.scan import ScanResult, scan_library


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mp3missing",
        description=(
            "List MP3s that are in an archive library but not in a live "
            "library. Matching uses the file name, duration, and bitrate "
            "only. Artist and album tags label and sort the missing list; "
            "they are not used to decide identity."
        ),
    )
    parser.add_argument(
        "archive",
        help="archive library folder (read only)",
    )
    parser.add_argument(
        "live",
        help="live library folder (read only)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DURATION_TOLERANCE_SECONDS,
        metavar="SECONDS",
        help=(
            "durations within this many seconds count as equal "
            f"(default: {DURATION_TOLERANCE_SECONDS:g})"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass

    args = parse_args(argv)
    print("mp3missing: started", file=sys.stderr, flush=True)
    if args.tolerance < 0:
        print("error: --tolerance must be zero or positive", file=sys.stderr)
        return 2

    # absolute() does not touch the disk. resolve() follows symlinks and can
    # sit forever on an external drive that is plugged in but not responding.
    archive = Path(args.archive).expanduser().absolute()
    live = Path(args.live).expanduser().absolute()

    for label, folder in (("archive", archive), ("live", live)):
        print(f"mp3missing: checking {label} folder {folder}", file=sys.stderr, flush=True)
        try:
            exists = folder.exists()
            is_dir = folder.is_dir() if exists else False
        except OSError as exc:
            print(f"error: {label} folder could not be read: {exc}", file=sys.stderr)
            return 2
        if not exists:
            print(f"error: {label} folder does not exist: {folder}", file=sys.stderr)
            return 2
        if not is_dir:
            print(f"error: {label} path is not a folder: {folder}", file=sys.stderr)
            return 2
    if archive == live:
        print("error: archive and live folders are the same", file=sys.stderr)
        return 2

    archive_scan = scan_library(archive, label="archive")
    live_scan = scan_library(live, label="live")
    missing = find_missing(archive_scan.tracks, live_scan.tracks, args.tolerance)

    _print_summary(archive, live, archive_scan, live_scan, missing, args.tolerance)
    _warn_unreadable("archive", archive_scan.unreadable)
    _warn_unreadable("live", live_scan.unreadable)
    sys.stdout.write(render_report(missing))
    return 0


def render_report(missing: list[Track]) -> str:
    if not missing:
        return "No archive MP3s are missing from the live library.\n"

    lines = [f"Missing from the live library: {len(missing)}", ""]
    current: tuple[str, str] | None = None
    for track in missing:
        group = (track.artist, track.album)
        if group != current:
            if current is not None:
                lines.append("")
            current = group
            lines.append(track.artist)
            lines.append(f"  {track.album}")
        lines.append(f"    {track.filename}")
        lines.append(f"      duration: {format_duration(track.duration)}")
        lines.append(f"      quality:  {track.bitrate_kbps} kbps")
        lines.append(f"      path:     {track.path}")
    lines.append("")
    return "\n".join(lines)


def format_duration(seconds: float) -> str:
    """Clock time plus seconds, e.g. ``3:41 (221.08s)``."""

    total = max(0.0, seconds)
    whole = int(round(total))
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        clock = f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        clock = f"{minutes}:{secs:02d}"
    return f"{clock} ({total:.2f}s)"


def _print_summary(
    archive: Path,
    live: Path,
    archive_scan: ScanResult,
    live_scan: ScanResult,
    missing: list[Track],
    tolerance: float,
) -> None:
    print(
        f"Archive: {len(archive_scan.tracks)} MP3s "
        f"({len(archive_scan.unreadable)} unreadable) — {archive}",
        file=sys.stderr,
    )
    print(
        f"Live:    {len(live_scan.tracks)} MP3s "
        f"({len(live_scan.unreadable)} unreadable) — {live}",
        file=sys.stderr,
    )
    print(
        "Match:   file name (case-insensitive), "
        f"duration (±{tolerance:g}s), bitrate (kbps)",
        file=sys.stderr,
    )
    print(f"Missing: {len(missing)}", file=sys.stderr)


def _warn_unreadable(label: str, items: list[tuple[Path, str]]) -> None:
    if not items:
        return
    print(
        f"warning: could not read {len(items)} {label} MP3(s):",
        file=sys.stderr,
    )
    for path, reason in items[:20]:
        print(f"  {path}: {reason}", file=sys.stderr)
    extra = len(items) - 20
    if extra > 0:
        print(f"  ... and {extra} more", file=sys.stderr)
