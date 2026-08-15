"""
Second Life Audio Converter
- Local mode: Convert a folder of MP3s to SL-ready WAV segments.
- YouTube mode: Download from a YouTube URL/playlist, then convert + split.
Output: WAV, 44100 Hz, 16-bit PCM, configurable segment length/count.

SPDX-License-Identifier: GPL-3.0-only

Copyright (C) 2026 Squeedledorf

This program is free software: you can redistribute it and/or modify it under
the terms of version 3 of the GNU General Public License as published by the
Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program.  If not, see <https://www.gnu.org/licenses/gpl-3.0.html>.
"""

import json
import math
import os
import re
import sys
import subprocess
import threading
import time
import urllib.error
import urllib.request
import tkinter as tk
from tkinter import filedialog, ttk, messagebox


APP_VERSION = "2.2"

# Hide console windows from subprocess calls on Windows
_SUBPROCESS_KWARGS = {}
if os.name == "nt":
    _SUBPROCESS_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW


# ── Settings persistence ────────────────────────────────────────────────────

def get_config_path():
    """Per-user config file (kept out of the portable folder so it survives
    re-extracting / moving the app)."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "SL Audio Converter", "config.json")


def load_config():
    try:
        with open(get_config_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    path = get_config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ── Utilities ──────────────────────────────────────────────────────────────

def get_base_dir():
    """Return the directory containing the script or the bundled exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_ffmpeg_path():
    base = get_base_dir()
    for name in ["ffmpeg.exe", "ffmpeg"]:
        candidate = os.path.join(base, name)
        if os.path.isfile(candidate):
            return candidate
    try:
        result = subprocess.run(
            ["where", "ffmpeg"], capture_output=True, text=True, shell=True
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return "ffmpeg"


# ── yt-dlp management ──────────────────────────────────────────────────────
#
# yt-dlp is fetched at runtime rather than shipped with the app. YouTube breaks
# extraction often enough that any bundled copy is stale within weeks, so the
# app keeps its own and refreshes it. It lives under LOCALAPPDATA so it stays
# writable no matter where the app itself was unzipped (Program Files, a
# read-only share, a USB stick).

YT_DLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YT_DLP_CHECK_INTERVAL = 24 * 60 * 60   # seconds between update checks
_USER_AGENT = f"SL-Audio-Converter/{APP_VERSION}"


def get_data_dir():
    """Per-machine folder for things the app downloads and owns."""
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            or os.path.expanduser("~"))
    return os.path.join(base, "SL Audio Converter")


def get_managed_yt_dlp_path():
    """Where our own copy of yt-dlp lives (may not exist yet)."""
    return os.path.join(get_data_dir(), "yt-dlp.exe")


def find_fallback_yt_dlp():
    """Any yt-dlp we can borrow if downloading isn't possible.

    Older portable folders shipped one next to the exe, and plenty of people
    already have it on PATH. We never update these -- they aren't ours and the
    folder may not even be writable -- but they keep the app usable offline.
    """
    for candidate in [
        os.path.join(get_base_dir(), "yt-dlp.exe"),
        os.path.join(os.path.expanduser("~"), "Downloads", "yt-dlp.exe"),
    ]:
        if os.path.isfile(candidate):
            return candidate
    try:
        result = subprocess.run(
            ["where", "yt-dlp"], capture_output=True, text=True, shell=True,
            **_SUBPROCESS_KWARGS,
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


def download_yt_dlp(progress_fn=None, cancel_fn=None):
    """Download the current yt-dlp.exe into our data folder; return its path.

    Writes to a temp name and renames on success, so an interrupted or failed
    download can never leave a half-written binary in place of a working one.
    """
    dest = get_managed_yt_dlp_path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"

    req = urllib.request.Request(YT_DLP_URL, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(part, "wb") as f:
                while True:
                    if cancel_fn is not None and cancel_fn():
                        raise RuntimeError("cancelled")
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_fn:
                        progress_fn(done, total)
        os.replace(part, dest)
        return dest
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise


def get_yt_dlp_version(path):
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=30,
            **_SUBPROCESS_KWARGS,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def update_yt_dlp(path):
    """Let yt-dlp update itself in place. Returns (changed, message).

    'yt-dlp -U' does the version check, the download and the swap, and is a
    quick no-op when there's nothing new -- so we don't second-guess it with
    our own release-API call.
    """
    before = get_yt_dlp_version(path)
    try:
        result = subprocess.run(
            [path, "-U"], capture_output=True, text=True, timeout=300,
            **_SUBPROCESS_KWARGS,
        )
    except Exception as e:
        return (False, f"update check failed ({e})")
    after = get_yt_dlp_version(path)
    if after and before and after != before:
        return (True, f"updated {before} -> {after}")
    if result.returncode != 0:
        return (False, "update check failed")
    return (False, f"up to date ({after or 'unknown version'})")


def ensure_yt_dlp(config, log_fn=None, progress_fn=None, cancel_fn=None,
                  force_update=False):
    """Return a working yt-dlp path, installing or refreshing it as needed.

    Called off the UI thread. Never raises: if every option fails we return
    None and the caller tells the user what to do about it.
    """
    def log(msg):
        if log_fn:
            log_fn(msg)

    managed = get_managed_yt_dlp_path()

    # First run (or someone cleared the folder): fetch it.
    if not os.path.isfile(managed):
        log("First run: downloading yt-dlp (about 18 MB)...")
        try:
            download_yt_dlp(progress_fn=progress_fn, cancel_fn=cancel_fn)
        except Exception as e:
            fallback = find_fallback_yt_dlp()
            if fallback:
                log(f"Could not download yt-dlp ({e}); using {fallback}")
                return fallback
            log(f"Could not download yt-dlp: {e}")
            return None
        config["yt_dlp_last_check"] = int(time.time())
        save_config(config)
        log(f"yt-dlp {get_yt_dlp_version(managed) or 'installed'} ready.")
        return managed

    # Already installed: check for a newer build now and then.
    last = config.get("yt_dlp_last_check", 0)
    due = force_update or (time.time() - last) > YT_DLP_CHECK_INTERVAL
    if due:
        changed, msg = update_yt_dlp(managed)
        config["yt_dlp_last_check"] = int(time.time())
        save_config(config)
        if changed or force_update:
            log(f"yt-dlp: {msg}")
    return managed


def get_deno_path():
    """Locate a deno.exe for yt-dlp's JS challenge solver, if installed.

    yt-dlp only auto-detects deno on PATH, which may be stale until the shell
    restarts after a winget install. We search common locations and pass the
    path explicitly via --js-runtimes so detection doesn't depend on PATH.
    """
    # A deno.exe shipped alongside the app (packaged build) wins.
    bundled = os.path.join(get_base_dir(), "deno.exe")
    if os.path.isfile(bundled):
        return bundled

    try:
        result = subprocess.run(
            ["where", "deno"], capture_output=True, text=True, shell=True,
            **_SUBPROCESS_KWARGS,
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates = [os.path.join(local, "Microsoft", "WinGet", "Links", "deno.exe")]
        pkgs = os.path.join(local, "Microsoft", "WinGet", "Packages")
        try:
            for entry in os.listdir(pkgs):
                if entry.startswith("DenoLand.Deno"):
                    candidates.append(os.path.join(pkgs, entry, "deno.exe"))
        except OSError:
            pass
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
    return None


def get_duration(ffmpeg_path, filepath):
    """Read a file's duration in seconds using ffmpeg (no ffprobe needed).

    ffmpeg prints "Duration: HH:MM:SS.ss" to stderr and exits non-zero when
    given no output target; we parse that line regardless of exit code.
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-i", filepath],
            capture_output=True, text=True, **_SUBPROCESS_KWARGS,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
        if m:
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception:
        pass
    return 0


def ceil_tenth(seconds):
    """Round a clip length UP to the nearest 0.1s.

    Rounding up (not nearest) guarantees N equal clips still cover the whole
    track, so nothing is dropped off the end. The 1e-9 nudge absorbs float
    artifacts (e.g. 28.6 stored as 28.59999...).
    """
    return math.ceil(seconds * 10 - 1e-9) / 10.0


def sanitize_filename(name):
    """Remove characters that are illegal in Windows filenames."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name


# Windows: a single path component is capped at 255 chars and the full path at
# 260 (unless long-path support is enabled). We keep the " <n>.wav" numbering
# suffix intact and trim the title to fit.
_MAX_COMPONENT = 255
_MAX_PATH = 259  # 260 minus the trailing NUL

# Second Life: inventory item names are capped at 63 characters. On upload SL
# strips the ".wav" extension and, if the name is too long, truncates from the
# END -- which silently eats the " <n>" numbering and makes the clips
# impossible to order. So we must pre-trim the *title* here, keeping the number,
# and the SL budget is measured WITHOUT the extension (SL never sees it).
_MAX_SL_NAME = 63


def truncate_track_name(track_name, output_dir, max_seg):
    """Trim track_name so the numbered clip name fits every relevant limit.

    Constraints, all measured against the widest segment number (max_seg) so
    every clip shares the same truncated title:
      * Second Life inventory name: '<name> <max_seg>' <= 63 chars (no ext).
      * Windows filename component: '<name> <max_seg>.wav' <= 255 chars.
      * Windows full path: output_dir + '\\' + that filename <= 259 chars.

    The numbering suffix is always preserved; only the title is shortened.
    """
    sl_suffix = f" {max_seg}"          # SL strips the extension
    win_suffix = f" {max_seg}.wav"     # on disk we keep it
    # Room left for the title under each limit; take the tightest.
    room = _MAX_SL_NAME - len(sl_suffix)
    room = min(room, _MAX_COMPONENT - len(win_suffix))
    room = min(room, _MAX_PATH - len(output_dir) - 1 - len(win_suffix))
    room = max(room, 1)
    if len(track_name) <= room:
        return track_name
    return track_name[:room].rstrip()


# ── Core: Convert + Split ─────────────────────────────────────────────────

def convert_and_split(audio_path, track_name, output_dir, ffmpeg_path, log_fn,
                      split_mode="length", split_value=30, result_fn=None):
    """Convert a single audio file to WAV and split into segments.

    split_mode: "length" - split_value is clip length in seconds (max 30)
                "count"  - split_value is number of equal-length clips
                "auto"   - fewest equal clips that are each <= 30s
    result_fn: optional callback(track_name, clip_length, segments, output_dir)
               invoked on success so the UI can surface the SL clip length.
    Returns True on success.
    """
    duration = get_duration(ffmpeg_path, audio_path)
    if duration <= 0:
        log_fn(f"  ERROR: Could not read duration, skipping.\n")
        return False

    if split_mode == "length":
        clip_length = ceil_tenth(min(split_value, 30))
        total_segments = max(1, math.ceil(duration / clip_length))
    elif split_mode == "auto":
        # Fewest equal parts where each is <= 30s, so each is as long as
        # possible. SL's per-upload limit is 30s; equal parts keep playback
        # gap-free when chained. Length is snapped UP to a tenth of a second.
        total_segments = max(1, math.ceil(duration / 30.0))
        clip_length = ceil_tenth(duration / total_segments)
    else:  # "count"
        total_segments = split_value
        if duration / total_segments > 30:
            min_clips = max(1, math.ceil(duration / 30))
            log_fn(f"  ERROR: {total_segments} clips would be {duration / total_segments:.1f}s each (max 30s).")
            log_fn(f"  This track needs at least {min_clips} clips.\n")
            return False
        clip_length = ceil_tenth(duration / total_segments)

    log_fn(f"  Duration: {duration:.1f}s -> {total_segments} segment(s) of ~{clip_length:.1f}s each")
    log_fn(f"  Clip length (SL): {clip_length:.1f} seconds")

    # Readable name for the results table (before any path-limit trimming).
    display_name = track_name

    # Keep numbering intact even when the title is long enough to blow past the
    # Windows path limit; trim the title, never the " <n>.wav" suffix.
    track_name = truncate_track_name(track_name, output_dir, total_segments)

    # Step 1: Convert to clean temporary WAV
    temp_wav = os.path.join(output_dir, f"_temp_{sanitize_filename(track_name)}.wav")
    convert_cmd = [
        ffmpeg_path, "-y",
        "-i", audio_path,
        "-map", "0:a:0",
        "-map_metadata", "-1",
        "-fflags", "+bitexact",
        "-ar", "44100",
        "-acodec", "pcm_s16le",
        "-ac", "2",
        temp_wav,
    ]
    result = subprocess.run(convert_cmd, capture_output=True, text=True,
                            **_SUBPROCESS_KWARGS)
    if result.returncode != 0:
        log_fn(f"  ERROR converting: {result.stderr.splitlines()[-1] if result.stderr else 'Unknown'}")
        return False

    # Step 2: Split into segments
    seg = 1
    offset = 0.0
    errors = False
    while seg <= total_segments:
        out_file = os.path.join(output_dir, f"{track_name} {seg}.wav")
        split_cmd = [
            ffmpeg_path, "-y",
            "-ss", str(offset),
            "-i", temp_wav,
            "-t", str(clip_length),
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            out_file,
        ]
        result = subprocess.run(split_cmd, capture_output=True, text=True,
                                **_SUBPROCESS_KWARGS)
        if result.returncode != 0:
            log_fn(f"  ERROR on segment {seg}: {result.stderr.splitlines()[-1] if result.stderr else 'Unknown'}")
            errors = True
            break
        seg += 1
        offset += clip_length

    try:
        os.remove(temp_wav)
    except OSError:
        pass

    if not errors:
        log_fn(f"  Done. ({seg - 1} segments)\n")
        if result_fn:
            result_fn(display_name, clip_length, total_segments, output_dir)
    return not errors


# ── Local folder processing ───────────────────────────────────────────────

def process_local(input_dir, output_dir, ffmpeg_path, log_fn, done_fn,
                  split_mode="length", split_value=30, cancel_event=None,
                  result_fn=None):
    mp3_files = sorted(
        [f for f in os.listdir(input_dir) if f.lower().endswith(".mp3")]
    )
    if not mp3_files:
        log_fn("No .mp3 files found in the selected folder.")
        done_fn()
        return

    os.makedirs(output_dir, exist_ok=True)
    log_fn(f"Found {len(mp3_files)} track(s). Output: {output_dir}\n")

    for i, filename in enumerate(mp3_files, start=1):
        if cancel_event is not None and cancel_event.is_set():
            log_fn("\n--- Cancelled. ---")
            done_fn()
            return
        name = os.path.splitext(filename)[0]
        input_path = os.path.join(input_dir, filename)
        log_fn(f"[{i}/{len(mp3_files)}] {filename}")
        convert_and_split(input_path, name, output_dir, ffmpeg_path, log_fn,
                          split_mode, split_value, result_fn=result_fn)

    log_fn("\n--- All tracks processed! ---")
    done_fn()


# ── YouTube download + processing ─────────────────────────────────────────

def is_playlist_url(url):
    """True if the URL refers to a YouTube playlist (a watch?v=...&list=... URL
    counts, since yt-dlp would otherwise grab the whole list)."""
    u = url.lower()
    return "list=" in u or "/playlist" in u


def fetch_playlist_entries(url, yt_dlp_path):
    """Return [{'index': 1, 'title': '...'}, ...] for a playlist, fast.

    Uses --flat-playlist so it only reads the listing page, not every video.
    Raises on failure (caller decides how to surface it).
    """
    base_cmd = [yt_dlp_path] if yt_dlp_path else ["python", "-m", "yt_dlp"]
    cmd = base_cmd + ["--flat-playlist", "--no-warnings", "-J", url]
    result = subprocess.run(cmd, capture_output=True, text=True, **_SUBPROCESS_KWARGS)
    data = json.loads(result.stdout)
    entries = data.get("entries") or []
    out = []
    for i, e in enumerate(entries, start=1):
        title = (e or {}).get("title") or f"(untitled {i})"
        out.append({"index": i, "title": title})
    return out


def _cleanup_dir(d):
    for f in os.listdir(d):
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass
    try:
        os.rmdir(d)
    except OSError:
        pass


def process_youtube(url, output_dir, ffmpeg_path, yt_dlp_path, log_fn, done_fn,
                    split_mode="length", split_value=30,
                    playlist_items=None, is_playlist=False,
                    cancel_event=None, set_proc=None, per_song_folders=True,
                    result_fn=None):
    os.makedirs(output_dir, exist_ok=True)
    download_dir = os.path.join(output_dir, "_downloads")
    os.makedirs(download_dir, exist_ok=True)

    def cancelled():
        return cancel_event is not None and cancel_event.is_set()

    # Build yt-dlp command
    if yt_dlp_path:
        base_cmd = [yt_dlp_path]
    else:
        base_cmd = ["python", "-m", "yt_dlp"]

    output_template = os.path.join(download_dir, "%(playlist_index|0)s %(title)s.%(ext)s")

    dl_cmd = base_cmd + [
        "--yes-playlist" if is_playlist else "--no-playlist",
        "-x",
        "--audio-format", "best",
        "--audio-quality", "0",
        # Fall back to a muxed format if no audio-only stream is offered (e.g.
        # when YouTube serves SABR-only / JS-runtime-gated formats).
        "-f", "bestaudio/best",
        "--ffmpeg-location", os.path.dirname(ffmpeg_path) if os.path.dirname(ffmpeg_path) else ffmpeg_path,
        "-o", output_template,
        "--no-overwrites",
    ]

    # Restrict to the user's chosen subset of a playlist, if any.
    if playlist_items:
        dl_cmd += ["--playlist-items", playlist_items]

    # YouTube now gates many formats behind a JS challenge; hand yt-dlp a deno
    # runtime explicitly if one is installed so extraction stays reliable.
    deno_path = get_deno_path()
    if deno_path:
        dl_cmd += ["--js-runtimes", f"deno:{deno_path}"]

    dl_cmd.append(url)

    log_fn("Downloading audio from YouTube...\n")
    log_fn(f"URL: {url}\n")
    if deno_path:
        log_fn(f"JS runtime: deno ({deno_path})\n")
    else:
        log_fn("JS runtime: none found (some formats may be unavailable)\n")

    # Run yt-dlp and stream output. Cancelling terminates the process, which
    # ends this read loop when the pipe closes.
    proc = subprocess.Popen(
        dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, **_SUBPROCESS_KWARGS,
    )
    if set_proc:
        set_proc(proc)
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log_fn(line)
        if cancelled():
            try:
                proc.terminate()
            except Exception:
                pass
            break
    proc.wait()

    if cancelled():
        log_fn("\nDownload cancelled. Cleaning up...")
        _cleanup_dir(download_dir)
        log_fn("--- Cancelled. ---")
        done_fn()
        return

    if proc.returncode != 0:
        log_fn(f"\nyt-dlp exited with code {proc.returncode} (some tracks may have failed).")
        log_fn("If this keeps happening, YouTube has probably changed again. "
               "Restart the app to pick up the latest yt-dlp.")

    log_fn("\nDownload complete. Converting to SL format...\n")

    # Collect downloaded audio files and sort by name (which starts with track number)
    audio_files = sorted([
        f for f in os.listdir(download_dir)
        if f.lower().endswith((".mp3", ".m4a", ".webm", ".opus", ".ogg", ".wav"))
    ])

    if not audio_files:
        log_fn("ERROR: No audio files found after download.")
        _cleanup_dir(download_dir)
        done_fn()
        return

    log_fn(f"Found {len(audio_files)} track(s) to convert.\n")

    for i, filename in enumerate(audio_files, start=1):
        if cancelled():
            log_fn("\n--- Cancelled. ---")
            break
        filepath = os.path.join(download_dir, filename)
        name_no_ext = os.path.splitext(filename)[0]

        # The download template prefixes a playlist index ("3 Song Title");
        # "0 " means a single video. Split the index off the title.
        m = re.match(r"^(\d+)\s+(.*)$", name_no_ext)
        if m:
            idx, title = m.group(1), m.group(2)
        else:
            idx, title = "", name_no_ext
        title = sanitize_filename(title) or "track"

        # Playlist tracks keep a zero-padded index prefix so they stay ordered
        # (as a folder name, or as a filename prefix in flat mode).
        if is_playlist and idx and idx != "0":
            ordered_name = f"{int(idx):02d} {title}"
        else:
            ordered_name = title
        ordered_name = (sanitize_filename(ordered_name)[:120].rstrip()) or "track"

        if per_song_folders:
            # Each song gets its own folder; the WAVs inside are just the title.
            song_dir = os.path.join(output_dir, ordered_name)
            os.makedirs(song_dir, exist_ok=True)
            track_label = title
        else:
            # Everything flat in the output folder; keep the ordered prefix on
            # the WAV names so tracks don't collide and stay in order.
            song_dir = output_dir
            track_label = ordered_name

        log_fn(f"[{i}/{len(audio_files)}] {title}")
        convert_and_split(filepath, track_label, song_dir, ffmpeg_path, log_fn,
                          split_mode, split_value, result_fn=result_fn)

    _cleanup_dir(download_dir)

    if not cancelled():
        log_fn("\n--- All tracks processed! ---")
    done_fn()


# ── GUI ───────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f"SL Audio Converter v{APP_VERSION}")
        self.root.geometry("700x740")
        self.root.resizable(True, True)
        self.ffmpeg_path = get_ffmpeg_path()
        self.yt_dlp_path = None       # resolved by the background setup thread
        self.config = load_config()
        self.cancel_event = None      # set per-run; lets the worker bail out
        self.current_proc = None      # the live yt-dlp process, for termination
        self._results = []            # accumulated (track, length, segments, dir)
        self._results_dir = ""        # top output folder for the summary file
        self.yt_dlp_ready = threading.Event()
        self._yt_dlp_progress = (0, 0)   # (bytes done, bytes total)
        self.build_ui()

        # Default the YouTube output to the saved download folder.
        if self.config.get("download_folder"):
            self.yt_output.set(self.config["download_folder"])

        # Ask for a download folder on first launch (once the window exists).
        self.root.after(300, self.first_launch_check)

        # Install / refresh yt-dlp in the background so startup never blocks.
        threading.Thread(target=self._yt_dlp_setup_worker, daemon=True).start()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # Title
        ttk.Label(
            main, text="Second Life Audio Converter",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(0, 2))
        ttk.Label(
            main, text="WAV  |  44100 Hz  |  16-bit PCM",
        ).pack(pady=(0, 10))

        # Tabs
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.X, pady=(0, 8))

        # ── Tab 1: Local files ──
        local_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(local_tab, text="  Local MP3s  ")

        folder_frame = ttk.Frame(local_tab)
        folder_frame.pack(fill=tk.X)
        ttk.Label(folder_frame, text="Album folder:").pack(side=tk.LEFT)
        self.folder_path = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_path, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ttk.Button(folder_frame, text="Browse...", command=self.browse_input).pack(side=tk.LEFT)

        # ── Tab 2: YouTube ──
        yt_tab = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(yt_tab, text="  YouTube  ")

        url_frame = ttk.Frame(yt_tab)
        url_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(url_frame, text="YouTube URL:").pack(side=tk.LEFT)
        self.yt_url = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.yt_url).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )

        out_frame = ttk.Frame(yt_tab)
        out_frame.pack(fill=tk.X)
        ttk.Label(out_frame, text="Output folder:").pack(side=tk.LEFT)
        self.yt_output = tk.StringVar()
        ttk.Entry(out_frame, textvariable=self.yt_output, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=6
        )
        ttk.Button(out_frame, text="Browse...", command=self.browse_output).pack(side=tk.LEFT)

        # When checked, each song goes into its own subfolder; when unchecked,
        # everything is dumped flat into the output folder.
        self.separate_folders = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            yt_tab, text="Put each song in its own folder",
            variable=self.separate_folders,
        ).pack(anchor="w", pady=(8, 0))

        # ── Split settings ──
        split_frame = ttk.LabelFrame(main, text="Split Settings", padding=8)
        split_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(split_frame, text="Split mode:").pack(side=tk.LEFT)
        self.split_mode = tk.StringVar(value="Automatic")
        split_combo = ttk.Combobox(
            split_frame, textvariable=self.split_mode,
            values=["Automatic", "By Clip Length", "By Number of Clips"],
            state="readonly", width=20,
        )
        split_combo.pack(side=tk.LEFT, padx=(6, 12))
        split_combo.bind("<<ComboboxSelected>>", self.on_split_mode_change)

        self.split_label = ttk.Label(split_frame, text="Clip length (sec):")
        self.split_label.pack(side=tk.LEFT)
        self.split_value = tk.StringVar(value="30")
        self.split_entry = ttk.Entry(split_frame, textvariable=self.split_value, width=8)
        self.split_entry.pack(side=tk.LEFT, padx=6)

        self.split_hint = ttk.Label(split_frame, text="(max 30)", foreground="gray")
        self.split_hint.pack(side=tk.LEFT)

        # Convert / Cancel buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(pady=8)
        self.convert_btn = ttk.Button(btn_frame, text="Convert", command=self.convert)
        self.convert_btn.pack(side=tk.LEFT, padx=4)
        self.cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self.cancel,
                                     state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=4)

        # ── Results: per-track SL clip length (persists; doesn't scroll away) ──
        res_frame = ttk.LabelFrame(
            main, text="Clip lengths: use these in Second Life", padding=6)
        res_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 6))

        cols = ("track", "len", "clips")
        self.results_tree = ttk.Treeview(
            res_frame, columns=cols, show="headings", height=6)
        self.results_tree.heading("track", text="Track")
        self.results_tree.heading("len", text="Clip length (sec)")
        self.results_tree.heading("clips", text="Clips")
        self.results_tree.column("track", width=400, anchor="w")
        self.results_tree.column("len", width=110, anchor="center")
        self.results_tree.column("clips", width=60, anchor="center")
        tree_sb = ttk.Scrollbar(res_frame, orient="vertical",
                                command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=tree_sb.set)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_tree.bind("<Double-1>", self._copy_clip_length)

        ttk.Label(
            main, text="Tip: double-click a row to copy its clip length. "
                       "A \"SL clip lengths.txt\" is also saved with your files.",
            foreground="gray",
        ).pack(anchor="w", pady=(0, 6))

        # Log output
        self.log = tk.Text(main, height=9, wrap=tk.WORD, font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
        scrollbar = ttk.Scrollbar(self.log, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.config(yscrollcommand=scrollbar.set, state=tk.DISABLED)

        # Apply the default mode's widget state (default is "Automatic").
        self.on_split_mode_change()

    def on_split_mode_change(self, event=None):
        mode = self.split_mode.get()
        if mode == "Automatic":
            self.split_label.config(text="Clip length:")
            self.split_value.set("")
            self.split_entry.config(state="disabled")
            self.split_hint.config(text="(auto: fewest equal clips ≤ 30s)")
        elif mode == "By Clip Length":
            self.split_label.config(text="Clip length (sec):")
            self.split_value.set("30")
            self.split_entry.config(state="normal")
            self.split_hint.config(text="(max 30)")
        else:
            self.split_label.config(text="Number of clips:")
            self.split_value.set("")
            self.split_entry.config(state="normal")
            self.split_hint.config(text="(each clip max 30s)")

    def browse_input(self):
        path = filedialog.askdirectory(title="Select album folder containing MP3 files")
        if path:
            self.folder_path.set(path)

    def browse_output(self):
        path = filedialog.askdirectory(title="Select output folder for converted files")
        if path:
            self.yt_output.set(path)

    def log_msg(self, text):
        def _update():
            self.log.config(state=tk.NORMAL)
            self.log.insert(tk.END, text + "\n")
            self.log.see(tk.END)
            self.log.config(state=tk.DISABLED)
        self.root.after(0, _update)

    def on_done(self):
        self.root.after(0, self._on_job_finished)

    def _on_job_finished(self):
        self._write_clip_files()
        self._reset_buttons()

    def _reset_buttons(self):
        self.convert_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)

    def add_result(self, track, clip_length, segments, track_dir):
        """Worker-thread callback: record a finished track's SL clip length and
        show it in the results table."""
        def _update():
            self._results.append({
                "track": track, "clip_length": clip_length,
                "segments": segments, "dir": track_dir,
            })
            row = self.results_tree.insert(
                "", tk.END, values=(track, f"{clip_length:.1f}", segments))
            self.results_tree.see(row)
        self.root.after(0, _update)

    def _copy_clip_length(self, event=None):
        sel = self.results_tree.selection()
        if not sel:
            return
        values = self.results_tree.item(sel[0], "values")
        if len(values) >= 2:
            self.root.clipboard_clear()
            self.root.clipboard_append(values[1])
            self.log_msg(f"Copied clip length {values[1]} to clipboard.")

    def _write_clip_files(self):
        """Persist clip lengths next to the output so the numbers survive after
        the window closes. One summary in the top folder, plus a note in each
        per-song subfolder."""
        if not self._results or not self._results_dir:
            return
        top = self._results_dir
        try:
            lines = ["Second Life clip lengths", "=" * 24, ""]
            for r in self._results:
                lines.append(
                    f"{r['track']}: {r['clip_length']:.1f} s  "
                    f"({r['segments']} clip(s))")
            with open(os.path.join(top, "SL clip lengths.txt"), "w",
                      encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError:
            pass

        for r in self._results:
            if os.path.normpath(r["dir"]) == os.path.normpath(top):
                continue  # flat output; covered by the summary above
            try:
                with open(os.path.join(r["dir"], "SL clip length.txt"), "w",
                          encoding="utf-8") as f:
                    f.write(
                        f"{r['track']}\n"
                        f"Clip length for Second Life: {r['clip_length']:.1f} seconds\n"
                        f"Number of clips: {r['segments']}\n")
            except OSError:
                pass

    def cancel(self):
        """Request cancellation of the running job and kill yt-dlp if active."""
        if self.cancel_event is not None:
            self.cancel_event.set()
        proc = self.current_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self.log_msg("\nCancelling... (finishing the current step)")
        self.cancel_btn.config(state=tk.DISABLED)

    def first_launch_check(self):
        """On first run, ask where YouTube downloads should go by default."""
        if self.config.get("download_folder"):
            return
        messagebox.showinfo(
            "Welcome",
            "Choose a default folder for your YouTube downloads.\n\n"
            "You can still override it per-download with the Browse button.",
        )
        path = filedialog.askdirectory(title="Choose your default download folder")
        if path:
            self.config["download_folder"] = path
            save_config(self.config)
            self.yt_output.set(path)

    # ── yt-dlp setup ─────────────────────────────────────────────────────

    def _yt_dlp_setup_worker(self):
        """Background: make sure a current yt-dlp is available."""
        def progress(done, total):
            self._yt_dlp_progress = (done, total)

        try:
            self.yt_dlp_path = ensure_yt_dlp(
                self.config, log_fn=self.log_msg, progress_fn=progress)
        except Exception as e:
            self.yt_dlp_path = None
            self.log_msg(f"yt-dlp setup failed: {e}")
        finally:
            self.yt_dlp_ready.set()

    def _with_yt_dlp(self, continue_fn):
        """Run continue_fn once yt-dlp is usable.

        Almost always immediate; the wait dialog only shows up if someone
        starts a YouTube job while the very first download is still running.
        """
        if self.yt_dlp_ready.is_set():
            if self.yt_dlp_path:
                continue_fn()
            else:
                self._yt_dlp_unavailable()
            return
        self._yt_dlp_wait_dialog(continue_fn)

    def _yt_dlp_unavailable(self):
        messagebox.showerror(
            "yt-dlp not available",
            "The app couldn't download yt-dlp, which it needs for YouTube.\n\n"
            "Check your internet connection and restart the app. If you're "
            "behind a firewall, you can also grab yt-dlp.exe yourself from\n"
            "https://github.com/yt-dlp/yt-dlp/releases/latest\n"
            f"and drop it in:\n{get_data_dir()}",
        )
        self.log_msg("--- Cancelled. ---")
        self._reset_buttons()

    def _yt_dlp_wait_dialog(self, continue_fn):
        dlg = tk.Toplevel(self.root)
        dlg.title("Setting up")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text="Getting yt-dlp, the YouTube downloader.\n"
                 "This happens once and takes a moment.",
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        bar = ttk.Progressbar(frame, mode="indeterminate", length=340)
        bar.pack(fill=tk.X)
        bar.start(12)
        status = ttk.Label(frame, text="Starting...", foreground="gray")
        status.pack(anchor="w", pady=(6, 10))

        cancelled = {"flag": False}

        def cancel():
            cancelled["flag"] = True
            dlg.destroy()
            self.log_msg("--- Cancelled. ---")
            self._reset_buttons()

        ttk.Button(frame, text="Cancel", command=cancel).pack(anchor="e")
        dlg.protocol("WM_DELETE_WINDOW", cancel)

        def poll():
            if cancelled["flag"]:
                return
            if self.yt_dlp_ready.is_set():
                dlg.destroy()
                if self.yt_dlp_path:
                    continue_fn()
                else:
                    self._yt_dlp_unavailable()
                return
            done, total = self._yt_dlp_progress
            if total:
                if bar["mode"] != "determinate":
                    bar.stop()
                    bar.config(mode="determinate", maximum=total)
                bar["value"] = done
                status.config(text=f"{done / 1e6:.1f} / {total / 1e6:.1f} MB")
            self.root.after(150, poll)

        poll()

    def get_split_params(self):
        """Parse and validate split settings. Returns (mode, value) or None on error."""
        if self.split_mode.get() == "Automatic":
            # Clip length is derived per-track from its duration; no input needed.
            return ("auto", 0)

        raw = self.split_value.get().strip()
        if not raw:
            messagebox.showwarning("Missing value", "Please enter a split value.")
            return None

        if self.split_mode.get() == "By Clip Length":
            try:
                val = float(raw)
            except ValueError:
                messagebox.showwarning("Invalid value", "Clip length must be a number.")
                return None
            if val <= 0 or val > 30:
                messagebox.showwarning("Invalid value", "Clip length must be between 0.1 and 30 seconds.")
                return None
            return ("length", val)
        else:
            try:
                val = int(raw)
            except ValueError:
                messagebox.showwarning("Invalid value", "Number of clips must be a whole number.")
                return None
            if val <= 0:
                messagebox.showwarning("Invalid value", "Number of clips must be at least 1.")
                return None
            return ("count", val)

    def _clear_log(self):
        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.config(state=tk.DISABLED)

    def _clear_results(self):
        self._results = []
        for iid in self.results_tree.get_children():
            self.results_tree.delete(iid)

    def convert(self):
        active_tab = self.notebook.index(self.notebook.select())

        # Validate split settings first
        split_params = self.get_split_params()
        if split_params is None:
            return
        split_mode, split_value = split_params

        self.convert_btn.config(state=tk.DISABLED)
        self._clear_log()
        self._clear_results()

        if active_tab == 0:
            # Local mode
            folder = self.folder_path.get()
            if not folder or not os.path.isdir(folder):
                messagebox.showwarning("No folder", "Please select a folder first.")
                self._reset_buttons()
                return
            output_dir = os.path.join(folder, "SL_Output")
            self._results_dir = output_dir
            self.cancel_event = threading.Event()
            self.current_proc = None
            self.cancel_btn.config(state=tk.NORMAL)
            threading.Thread(
                target=process_local,
                args=(folder, output_dir, self.ffmpeg_path, self.log_msg, self.on_done,
                      split_mode, split_value, self.cancel_event, self.add_result),
                daemon=True,
            ).start()
            return

        # YouTube mode
        url = self.yt_url.get().strip()
        output_dir = self.yt_output.get()
        if not url:
            messagebox.showwarning("No URL", "Please paste a YouTube URL.")
            self._reset_buttons()
            return
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showwarning("No output folder", "Please select an output folder.")
            self._reset_buttons()
            return
        self._results_dir = output_dir

        def go():
            if is_playlist_url(url):
                # Fetch the listing first so we can confirm / let the user pick.
                self.log_msg("Fetching playlist contents...")
                def worker():
                    try:
                        entries = fetch_playlist_entries(url, self.yt_dlp_path)
                    except Exception:
                        entries = None
                    self.root.after(
                        0, lambda: self._on_playlist_fetched(
                            entries, url, output_dir, split_mode, split_value))
                threading.Thread(target=worker, daemon=True).start()
                return

            # Single video.
            self._start_youtube(url, output_dir, split_mode, split_value,
                                playlist_items=None, is_playlist=False)

        # Blocks only on the very first launch, while yt-dlp is downloading.
        self._with_yt_dlp(go)

    def _on_playlist_fetched(self, entries, url, output_dir, split_mode, split_value):
        if not entries:
            messagebox.showerror(
                "Playlist",
                "Could not read the playlist (it may be private, empty, or "
                "unavailable).",
            )
            self.log_msg("--- Cancelled. ---")
            self._reset_buttons()
            return

        def proceed():
            self._start_youtube(url, output_dir, split_mode, split_value,
                                playlist_items=None, is_playlist=True)

        def view():
            def on_download(indices):
                items = ",".join(str(i) for i in indices)
                self._start_youtube(url, output_dir, split_mode, split_value,
                                    playlist_items=items, is_playlist=True)

            def on_cancel():
                self.log_msg("--- Cancelled. ---")
                self._reset_buttons()

            self._view_playlist_dialog(entries, on_download, on_cancel)

        def cancel():
            self.log_msg("--- Cancelled. ---")
            self._reset_buttons()

        self._confirm_playlist_dialog(entries, proceed, view, cancel)

    def _start_youtube(self, url, output_dir, split_mode, split_value,
                       playlist_items, is_playlist):
        self.cancel_event = threading.Event()
        self.current_proc = None
        self.convert_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)

        def set_proc(p):
            self.current_proc = p

        per_song_folders = self.separate_folders.get()
        threading.Thread(
            target=process_youtube,
            args=(url, output_dir, self.ffmpeg_path, self.yt_dlp_path,
                  self.log_msg, self.on_done, split_mode, split_value,
                  playlist_items, is_playlist, self.cancel_event, set_proc,
                  per_song_folders, self.add_result),
            daemon=True,
        ).start()

    # ── Dialogs ──────────────────────────────────────────────────────────

    def _confirm_playlist_dialog(self, entries, on_proceed, on_view, on_cancel):
        win = tk.Toplevel(self.root)
        win.title("Playlist detected")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        ttk.Label(
            win, text=f"This is a playlist with {len(entries)} track(s).",
            font=("Segoe UI", 11, "bold"),
        ).pack(padx=20, pady=(18, 4))
        ttk.Label(
            win, text="Downloading them all could take a while. Proceed?",
        ).pack(padx=20, pady=(0, 14))

        btns = ttk.Frame(win)
        btns.pack(padx=20, pady=(0, 18))

        def choose(cb):
            win.grab_release()
            win.destroy()
            cb()

        ttk.Button(btns, text="Proceed", command=lambda: choose(on_proceed)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="View playlist", command=lambda: choose(on_view)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Cancel", command=lambda: choose(on_cancel)).pack(side=tk.LEFT, padx=4)
        win.protocol("WM_DELETE_WINDOW", lambda: choose(on_cancel))

    def _view_playlist_dialog(self, entries, on_download, on_cancel):
        win = tk.Toplevel(self.root)
        win.title("Select tracks to download")
        win.geometry("560x520")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(
            win, text=f"{len(entries)} tracks. Check the ones you want:",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        # Scrollable list of checkboxes.
        container = ttk.Frame(win)
        container.pack(fill=tk.BOTH, expand=True, padx=12)
        canvas = tk.Canvas(container, highlightthickness=0)
        sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def _wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", _wheel)

        track_vars = []
        for e in entries:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(
                inner, text=f"{e['index']:>3}.  {e['title']}", variable=var,
            ).pack(anchor="w", pady=1)
            track_vars.append((e["index"], var))

        def set_all(value):
            for _, var in track_vars:
                var.set(value)

        selbar = ttk.Frame(win)
        selbar.pack(fill=tk.X, padx=12, pady=(6, 0))
        ttk.Button(selbar, text="Select all", command=lambda: set_all(True)).pack(side=tk.LEFT)
        ttk.Button(selbar, text="Select none", command=lambda: set_all(False)).pack(side=tk.LEFT, padx=4)

        def close_with(cb, *args):
            canvas.unbind_all("<MouseWheel>")
            win.grab_release()
            win.destroy()
            cb(*args)

        def download():
            chosen = [idx for idx, var in track_vars if var.get()]
            if not chosen:
                messagebox.showinfo("Nothing selected",
                                    "Select at least one track, or press Cancel.")
                return
            close_with(on_download, chosen)

        act = ttk.Frame(win)
        act.pack(fill=tk.X, padx=12, pady=10)
        ttk.Button(act, text="Download selected", command=download).pack(side=tk.RIGHT)
        ttk.Button(act, text="Cancel", command=lambda: close_with(on_cancel)).pack(side=tk.RIGHT, padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: close_with(on_cancel))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
