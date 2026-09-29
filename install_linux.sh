#!/bin/sh
# Adds SL Audio Converter to your application launcher.
#
# Writes a .desktop entry pointing at the script in this folder, so run it
# again if you move the folder. Remove the app with: ./install_linux.sh --remove
set -e

APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP="$APPS/sl-audio-converter.desktop"

if [ "$1" = "--remove" ]; then
    rm -f "$DESKTOP"
    echo "Removed $DESKTOP"
    exit 0
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$DIR/sl_audio_converter.pyw"

for dep in python3 ffmpeg; do
    command -v "$dep" >/dev/null || echo "Warning: $dep not found on PATH. Install it with your package manager."
done
python3 -c "import tkinter" 2>/dev/null ||
    echo "Warning: Python can't load tkinter. Install your distro's tk package (Arch: tk, Debian/Ubuntu: python3-tk, Fedora: python3-tkinter)."
command -v deno >/dev/null ||
    echo "Note: deno not found. Recommended for YouTube, see https://deno.com"

mkdir -p "$APPS"
cat > "$DESKTOP" <<DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=SL Audio Converter
Comment=Turn MP3s and YouTube audio into Second Life-ready WAV clips
Exec=python3 "$SCRIPT"
Path=$DIR
Icon=audio-x-generic
Terminal=false
Categories=AudioVideo;Audio;
DESKTOP_EOF

command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
echo "Installed $DESKTOP"
