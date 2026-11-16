#!/usr/bin/env bash
# Install the local Japanese Goemon native executable in the Linux app launcher.
# This installs only a desktop entry, the preexisting icon and a wrapper.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
binary="${GOEMON_JP_BINARY:-$repo_root/build-generated/japan-native-game/Goemon64RecompiledJP}"
if [[ ! -x "$binary" && -z "${GOEMON_JP_BINARY:-}" && -x "$repo_root/Goemon64RecompiledJP" ]]; then
    binary="$repo_root/Goemon64RecompiledJP"
fi
if [[ ! -x "$binary" ]]; then
    echo "Japanese executable missing or not executable: $binary" >&2
    exit 2
fi
if [[ ! -f "$repo_root/icons/512.png" ]]; then
    echo "Game icon missing: $repo_root/icons/512.png" >&2
    exit 2
fi

data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
icon_dir="$data_home/icons/hicolor/512x512/apps"
apps_dir="$data_home/applications"
bin_dir="$HOME/.local/bin"
launcher="$bin_dir/goemon64jp-launch"
desktop_file="$apps_dir/Goemon64RecompiledJP.desktop"

install -d "$icon_dir" "$apps_dir" "$bin_dir"
install -m 644 "$repo_root/icons/512.png" "$icon_dir/Goemon64RecompiledJP.png"

# Use printf %q so both repository and executable paths can contain spaces.
printf '#!/usr/bin/env bash\nset -euo pipefail\ncd %q\nexec %q "$@"\n' \
    "$repo_root" "$binary" > "$launcher"
chmod 755 "$launcher"

# Desktop Exec fields do not expand shell variables. The wrapper is absolute.
cat > "$desktop_file" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Goemon 64: Recompiled (Japanese)
GenericName=Nintendo 64 native recompilation
Comment=Ganbare Goemon: Neo Momoyama Bakufu no Odori
Exec=$launcher
Path=$repo_root
Icon=Goemon64RecompiledJP
StartupWMClass=Goemon64RecompiledJP
StartupNotify=true
Terminal=false
Categories=Game;
EOF
chmod 644 "$desktop_file"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" || true
fi
if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$desktop_file"
fi

printf 'Installed Japanese launcher: %s\n' "$desktop_file"
printf 'Installed game icon: %s\n' "$icon_dir/Goemon64RecompiledJP.png"
printf 'Start with: %s\n' "$launcher"
printf 'The icon will also appear in the GNOME app grid. Pin it to the dock from there.\n'