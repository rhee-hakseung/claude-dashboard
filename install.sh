#!/bin/bash
# Install Claude dashboard on macOS: venv + packages + projects folder + "Claude dashboard.app".
# Run from the cloned folder:  ./install.sh            (or: bash install.sh ~/dev)
# Safe to run again: it reuses a working .venv, updates packages, and rewrites the app bundle.
# On Linux it does the same except the app bundle (start with: .venv/bin/python app.py).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
dev_root="${1:-}"

echo "== Claude dashboard install ==  ($here)"

# 1) Python 3.10+
py=""
for c in python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
        py="$(command -v "$c")"
        break
    fi
done
if [ -z "$py" ]; then
    echo "Python 3.10+ was not found. Install it, then run this again:"
    echo "  brew install python@3.13      (or the installer from https://www.python.org/downloads/)"
    exit 1
fi
echo "Python: $py"

# 2) venv (recreate if it was copied from another machine and no longer runs)
if ! "$here/.venv/bin/python" -c 'import sys' >/dev/null 2>&1; then
    rm -rf "$here/.venv"
    echo "Creating .venv ..."
    "$py" -m venv "$here/.venv"
fi
echo "Installing packages ..."
"$here/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$here/requirements.txt"

# 3) Projects folder (each direct subfolder = one project)
if [ -z "$dev_root" ]; then
    read -r -p "Projects folder (each direct subfolder = one project) [$HOME/dev]: " dev_root || true
    dev_root="${dev_root:-$HOME/dev}"
fi
dev_root="${dev_root/#\~/$HOME}"
if [ ! -d "$dev_root" ]; then
    echo "Folder does not exist: $dev_root"
    exit 1
fi
dev_root="$(cd "$dev_root" && pwd)"
(cd "$here/dashboard" && ../.venv/bin/python -B -c 'import sys, prefs; prefs.save_state(dev_root=sys.argv[1])' "$dev_root")
echo "Projects folder: $dev_root"

# 4) App bundle (macOS only): ~/Applications/Claude dashboard.app — open it from Launchpad/Spotlight/Dock
if [ "$(uname -s)" = "Darwin" ]; then
    app="$HOME/Applications/Claude dashboard.app"
    rm -rf "$app"
    mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
    cat > "$app/Contents/MacOS/launcher" <<EOF
#!/bin/bash
# Finder starts apps with a minimal PATH; add the usual places for git.
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
export PYTHONDONTWRITEBYTECODE=1
cd "$here"
exec "$here/.venv/bin/python" -B "$here/app.py"
EOF
    chmod +x "$app/Contents/MacOS/launcher"
    sips -s format icns "$here/dashboard.ico" --out "$app/Contents/Resources/dashboard.icns" >/dev/null 2>&1 || true
    cat > "$app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Claude dashboard</string>
  <key>CFBundleDisplayName</key><string>Claude dashboard</string>
  <key>CFBundleIdentifier</key><string>local.claude-dashboard</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>dashboard</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
EOF
    echo "App: $app"
    echo ""
    echo "Done. Open 'Claude dashboard' from Spotlight or ~/Applications (drag it to the Dock to keep it)."
    echo "The first [jump] asks to let it control Terminal (System Settings > Privacy & Security > Automation)."
else
    echo ""
    echo "Done. Start it with:  $here/.venv/bin/python $here/app.py"
fi
echo "To change the projects folder later: run ./install.sh again."
