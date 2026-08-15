"""
Build a portable package of the SL Audio Converter.

Produces:  package/SL Audio Converter (Portable).zip

The zip contains one folder:
    SL Audio Converter.exe   (the app; Python is baked in by PyInstaller)
    ffmpeg.exe               (audio conversion + duration reading)
    deno.exe                 (JS runtime for YouTube extraction)
    README.txt

yt-dlp is deliberately NOT bundled. The app downloads it on first launch and
keeps it updated after that -- a copy frozen into the zip goes stale within
weeks of YouTube's next change, and this way the only thing we redistribute is
our own code.

Run this on YOUR machine (where ffmpeg + deno are installed):  build_package.bat

Copyright (C) 2026 Squeedledorf. Licensed under the GNU General Public License
version 3 or later. See the LICENSE file for details.
"""

import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_SCRIPT = os.path.join(HERE, "sl_audio_converter.pyw")
APP_NAME = "SL Audio Converter"
STAGING_PARENT = os.path.join(HERE, "package")
STAGING = os.path.join(STAGING_PARENT, APP_NAME)
ZIP_PATH = os.path.join(STAGING_PARENT, f"{APP_NAME} (Portable)")  # .zip appended


def fail(msg):
    print(f"\n[ERROR] {msg}")
    sys.exit(1)


def find_ffmpeg():
    local = os.path.join(HERE, "ffmpeg.exe")
    if os.path.isfile(local):
        return local
    found = shutil.which("ffmpeg")
    if found:
        # Resolve WinGet shims/symlinks to the real binary so we copy content.
        return os.path.realpath(found)
    return None


def find_deno():
    """Same search order the app uses at runtime."""
    local = os.path.join(HERE, "deno.exe")
    if os.path.isfile(local):
        return local
    found = shutil.which("deno")
    if found:
        return os.path.realpath(found)
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        links = os.path.join(appdata, "Microsoft", "WinGet", "Links", "deno.exe")
        if os.path.isfile(links):
            return links
        pattern = os.path.join(
            appdata, "Microsoft", "WinGet", "Packages", "DenoLand.Deno*", "deno.exe"
        )
        hits = glob.glob(pattern)
        if hits:
            return hits[0]
    return None


README = """\
SL Audio Converter (Portable)
=============================

Converts MP3s / YouTube audio into Second Life-ready WAV clips
(WAV, 44100 Hz, 16-bit PCM), split into uploadable segments.

See CHANGELOG.txt for what's new in this version.

HOW TO USE
----------
1. Keep ALL files in this folder together. Do not separate the .exe
   from the other .exe files next to it.
2. Double-click "SL Audio Converter.exe".
3. First launch: you'll be asked to pick a default download folder.
   YouTube downloads go there unless you override it with Browse.
   The app also downloads yt-dlp (about 18 MB) the first time it
   runs, and keeps it up to date after that. You need an internet
   connection for that first launch.
4. Pick a tab:
     - "Local MP3s": choose a folder of MP3s.
     - "YouTube":    paste a URL (output folder is pre-filled).
5. Split mode:
     - Automatic: the app picks the fewest equal clips that are each
       30 seconds or less, and tells you the exact clip length to use
       in Second Life (rounded to a tenth of a second).
     - By Clip Length / By Number of Clips: set it yourself.
6. Click Convert.
     - "Put each song in its own folder" (checkbox, on by default):
         ON  -> each song gets its own subfolder with numbered WAVs.
         OFF -> all WAVs dumped flat into the output folder.
     - You can press Cancel at any time during a download.

PLAYLISTS
---------
Paste a playlist URL (or any URL with "&list=") and the app warns you
before downloading. You can Proceed (download everything), Cancel, or
View Playlist to tick exactly which tracks you want.

YOUTUBE STOPPED WORKING?
------------------------
YouTube changes how it serves audio every few months, which breaks
the downloader until it catches up. The app checks for a new yt-dlp
once a day on startup, so the fix is usually just: close it and
open it again.

That's it. Nothing to install. No Python or ffmpeg needs to be on
your computer; it's all in this folder.

If Windows SmartScreen warns about the unsigned .exe, click
"More info" then "Run anyway" (it's just because the app isn't
code-signed).

LICENSE
-------
GPL-3.0. See LICENSE. Source: https://github.com/Squeedledorf/SL-Audio-Converter
Bundled ffmpeg and deno are separate projects under their own licenses.
"""


def main():
    print("=" * 50)
    print(f" Packaging {APP_NAME} (portable)")
    print("=" * 50)

    if not os.path.isfile(APP_SCRIPT):
        fail(f"Cannot find {APP_SCRIPT}")

    # 1. Resolve the bundled binaries up front so we fail fast.
    print("\nLocating dependencies...")
    ffmpeg = find_ffmpeg()
    deno = find_deno()

    for name, path in [("ffmpeg.exe", ffmpeg), ("deno.exe", deno)]:
        if not path:
            fail(
                f"Could not find {name}. Install it first "
                f"(winget install Gyan.FFmpeg / DenoLand.Deno), "
                f"or drop {name} next to this script."
            )
        print(f"  {name:12} -> {path}  ({os.path.getsize(path) / 1e6:.0f} MB)")

    # 2. Build the app exe with PyInstaller into a scratch dir.
    print("\nBuilding the app .exe with PyInstaller...")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("  PyInstaller not found; installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    scratch = os.path.join(STAGING_PARENT, "_pyinstaller")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--onefile", "--windowed",
            "--name", APP_NAME,
            "--distpath", os.path.join(scratch, "dist"),
            "--workpath", os.path.join(scratch, "build"),
            "--specpath", scratch,
            "--noconfirm",
            APP_SCRIPT,
        ],
        check=True,
    )
    built_exe = os.path.join(scratch, "dist", f"{APP_NAME}.exe")
    if not os.path.isfile(built_exe):
        fail("PyInstaller did not produce the .exe (see output above).")

    # 3. Assemble the staging folder.
    print("\nAssembling package folder...")
    if os.path.isdir(STAGING):
        shutil.rmtree(STAGING)
    os.makedirs(STAGING)

    shutil.copy2(built_exe, os.path.join(STAGING, f"{APP_NAME}.exe"))
    shutil.copy2(ffmpeg, os.path.join(STAGING, "ffmpeg.exe"))
    shutil.copy2(deno, os.path.join(STAGING, "deno.exe"))
    with open(os.path.join(STAGING, "README.txt"), "w", encoding="utf-8") as f:
        f.write(README)

    for name in ("CHANGELOG.txt", "LICENSE"):
        src = os.path.join(HERE, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(STAGING, name))
        else:
            print(f"  [warn] {name} not found; skipping.")

    # 4. Zip it.
    print("Zipping...")
    if os.path.isfile(ZIP_PATH + ".zip"):
        os.remove(ZIP_PATH + ".zip")
    shutil.make_archive(ZIP_PATH, "zip", root_dir=STAGING_PARENT, base_dir=APP_NAME)

    # 5. Clean up scratch (leave the staging folder + zip for inspection).
    shutil.rmtree(scratch, ignore_errors=True)

    size_mb = os.path.getsize(ZIP_PATH + ".zip") / 1e6
    print("\n" + "=" * 50)
    print(" Done!")
    print(f"  Zip:    {ZIP_PATH}.zip  ({size_mb:.0f} MB)")
    print(f"  Folder: {STAGING}")
    print("=" * 50)
    print("\nSend the .zip to your friends. They unzip it and run the .exe.")


if __name__ == "__main__":
    main()
