# SL Audio Converter

Turns MP3s and YouTube audio into Second Life-ready WAV clips: 44100 Hz, 16-bit
PCM, cut into segments you can actually upload.

Second Life caps uploaded sounds at 30 seconds, so anything longer has to be
chopped up and reassembled in-world with a script. The annoying part isn't the
chopping, it's that every clip has to be *exactly* the same length or the
playback drifts, and SL wants that length to a tenth of a second. This works out
the number for you and hands it over.

![Windows](https://img.shields.io/badge/platform-Windows-blue)
![Linux](https://img.shields.io/badge/platform-Linux-blue)
![License](https://img.shields.io/badge/license-GPLv3-green)

## What it does

- **Local MP3s**: point it at a folder, get back numbered WAV clips.
- **YouTube**: paste a URL, it downloads, converts and splits in one go.
  Playlists prompt first, with a checkbox list if you only want some tracks.
- **Automatic split mode**: picks the fewest equal clips that all come in at
  30 seconds or under, then tells you the exact clip length to use in SL.
- **Name handling**: SL truncates long inventory names from the end, which
  eats the clip numbering and leaves you unable to order them. Titles get
  trimmed up front so the numbers always survive.
- Clip lengths land in an on-screen table (double-click to copy) *and* in a
  `SL clip lengths.txt` next to the output, so the number you need doesn't
  scroll away in a log.

## Getting it

Grab the portable zip from
[Releases](https://github.com/Squeedledorf/SL-Audio-Converter/releases),
unzip it anywhere, run `SL Audio Converter.exe`. Nothing to install.

First launch asks where you want downloads to go, then offers to fetch yt-dlp
(about 18 MB). Say yes and you're done. Say no and the Local MP3s tab still
works fine; it'll ask again the first time you actually use YouTube.

Windows SmartScreen will complain because the exe isn't code-signed. **More
info** → **Run anyway**.

## About yt-dlp

The app fetches yt-dlp itself instead of shipping a copy. It asks before the
first download, then keeps it current on its own, re-checking for a newer build
at most once a day on startup.

This isn't just tidiness. YouTube reworks how it serves audio every few months,
and each time it does, every frozen copy of yt-dlp in the wild stops working
until someone ships a new build. Bundling one meant re-releasing the whole app
every time that happened. Now the fix arrives on its own and the worst case is
"close it and open it again".

It lives in `%LOCALAPPDATA%\SL Audio Converter\` (`~/.local/share/SL Audio Converter/` on Linux) so updates work even if the app
itself is somewhere unwritable. If the download fails, the app falls back to any
yt-dlp sitting next to the exe or on your PATH.

## Running from source

Needs Python 3.8+ and ffmpeg on PATH. [deno](https://deno.com) is strongly
recommended: YouTube gates a lot of formats behind a JS challenge that yt-dlp
needs a JS runtime to solve.

```
winget install Gyan.FFmpeg
winget install DenoLand.Deno
python sl_audio_converter.pyw
```

It's tkinter and the standard library.

`setup.bat` does all of the above for you if you'd rather not.

## Linux

There's no packaged build; it runs straight from source. You need Python 3.8+
with tkinter, and ffmpeg. deno is recommended for the same reason as on
Windows. On Arch:

```
sudo pacman -S python tk ffmpeg deno
```

Debian and Ubuntu call tkinter `python3-tk`; Fedora calls it `python3-tkinter`.

Clone or unzip the source somewhere you'll keep it, then:

```
./install_linux.sh
```

That puts **SL Audio Converter** in your application launcher. It points at the
folder you ran it from, so run it again if you move the folder, and
`./install_linux.sh --remove` takes it out. You can also skip the launcher and
run `python3 sl_audio_converter.pyw`.

If yt-dlp is already installed from your package manager, the app uses that
one and leaves updating it to your package manager. Otherwise it offers to
download its own copy, the same as on Windows. Settings go in
`~/.config/SL Audio Converter/`.

## Building

```
build_exe.bat          :: just the exe
build_package.bat      :: portable zip with ffmpeg + deno bundled
```

`build_package.py` pulls ffmpeg and deno from wherever they're installed on the
build machine and stages everything into `package/`.

## License

GNU General Public License, version 3. Full text in [LICENSE](LICENSE).

Do what you like with it. If you distribute a modified version, it stays open
under the same license and your users get the source too.

Third-party components are separate projects under their own terms and are not
covered by this license:

| | |
|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense. Downloaded at runtime, not redistributed here. |
| [ffmpeg](https://ffmpeg.org) | GPL/LGPL depending on build. Bundled in the portable zip. |
| [deno](https://deno.com) | MIT. Bundled in the portable zip. |
