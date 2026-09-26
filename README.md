# MP3 missing

This tool compares an archive of an MP3 library (on another disk) with the live library on a Mac. It lists archive MP3s that are not in the live library.

The check is one-way. A file that exists only on the Mac is not listed. Nothing is copied, deleted, or retagged. Both folders are read only.

You do not need Cursor Desktop to read this. The code is ordinary Python. Open it in any editor.

Read it in this order:

1. `mp3missing/compare.py` — how two files count as the same recording, and how the list is sorted
2. `mp3missing/scan.py` — how a folder is walked and how duration and bitrate are read
3. `mp3missing/id3text.py` — where the archive artist and album labels come from
4. `mp3missing/cli.py` — the arguments and the printed report
5. `tests/` — small generated MP3s that lock the matching rules

## How matching works

A live file is the same recording as an archive file only when all three of these agree:

1. **File name.** The basename only, such as `01 Airbag.mp3`. The folders are ignored. Album and artist folder names often differ because those names were changed in the live library.
2. **Duration.** The two lengths are equal within **1 second**, inclusive (`--tolerance` changes this). Header estimates for the same recording can differ slightly. A different edit is usually much further apart than that.
3. **Quality.** MP3 bitrate in **kbps**. The integers must be the same. A 128 kbps copy on the Mac does not stand in for a 320 kbps archive file.

File names are compared **case-insensitively** (Unicode casefold), and NFC and NFD forms of the same name are treated as equal. That matches a typical Mac volume: default APFS and HFS are case-insensitive, and Finder stores names in decomposed Unicode. The tool always compares names this way, including if you run it on Linux, because the live library is the Mac one.

**Artist and album tags are not used to decide identity.** They are read from the **archive** file only to sort and label the missing list. The order is archive artist, then archive album, then file name, case-insensitive. A missing tag is shown as `Unknown Artist` or `Unknown Album`. The artist label is the track artist (`TPE1`), not the folder name and not the album-artist tag.

The check is existence, not a count. One matching live file covers every archive copy of that recording.

These files are ignored:

- anything that is not `.mp3` (any capitalization)
- AppleDouble sidecars named `._Something.mp3`

An `.mp3` whose header cannot be read is not guessed at. It is counted as unreadable on stderr and left out of the missing list. An unreadable live file can hide a match, so those warnings are worth a look.

Duration and bitrate are taken from the MPEG header, not by decoding the audio:

- Constant bitrate: the bitrate in the first MPEG frame. Duration is mutagen's header estimate (audio size and that bitrate) when the file has no Xing header.
- Variable bitrate: the average bitrate and the duration from the Xing or VBRI header.

The average bitrate is rounded to the nearest integer kbps. A one-kbps difference counts as a different quality.

About 12,000 files stays a directory walk plus a header read per file. Cover art is skipped rather than loaded. Samples are not decoded.

## Run it on a Mac

Python 3.11 or newer. Mount the archive disk, then point the tool at the two folders that contain the MP3s (it walks subfolders).

The archive disk is the volume named HD, folder `Music`. On a Mac that is `/Volumes/HD/Music`. The live library is `/Users/AC/Music/Music/Media.localized/Music`.

From the project folder, with the HD disk plugged in:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m mp3missing "/Volumes/HD/Music" "/Users/AC/Music/Music/Media.localized/Music"
```

`mutagen` is pinned in `requirements.txt`. It reads the MPEG header and ID3 text. It does not decode the audio.

Save the list and leave the summary in the terminal:

```bash
python -m mp3missing "/Volumes/HD/Music" "/Users/AC/Music/Music/Media.localized/Music" > missing.txt
```

The summary (counts, the match rule, unreadable files) goes to stderr. The missing list goes to stdout.

Example list:

```text
Missing from the live library: 1

Autechre
  LP5
    Acroyear2.mp3
      duration: 8:32 (512.14s)
      quality:  320 kbps
      path:     /Volumes/ArchiveDisk/Music/Autechre/LP5/Acroyear2.mp3
```

A wider tolerance, if header durations in your libraries drift by more than a second:

```bash
python -m mp3missing "/Volumes/HD/Music" "/Users/AC/Music/Music/Media.localized/Music" --tolerance 2
```

The command exits 0 when the report was written, including when some files are missing. It exits 2 if a path is missing, is not a folder, or both arguments are the same folder.

If Terminal says the archive folder does not exist, the disk may be mounted under a different name. Run `ls /Volumes` and use the name Finder shows for that drive, still ending in `/Music`.

## Tests

The tests build tiny real MP3 frames (and a Xing header for the variable-bitrate case). They do not need a 12,000-file library.

```bash
python -m unittest discover -s tests -t .
```
