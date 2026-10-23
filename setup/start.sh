#!/bin/sh
# Sets up whatever is missing for the ArduPilot workshop and starts the GCS. Safe to run again.
#   curl -LsSf https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.sh | sh
#   (no curl: wget -qO- https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.sh | sh)
# From the organisers' laptop, without internet: the same with http://<their laptop>:8080/setup/start.sh
# Options go to start.py, e.g. ... | sh -s -- --dir ~/somewhere-else
# Everything is in a function that runs on the last line, so a download cut short runs nothing.

main() {
    set -e
    START_PY_URL="https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.py"
    PYTHON_VERSION="3.12"
    # Set when this script came from the organisers' laptop: everything from there first, the internet if not there
    WORKSHOP_MIRROR="${WORKSHOP_MIRROR:-}"
    export WORKSHOP_MIRROR

    # Prints what's at a web address, with curl or wget, whichever this laptop has (fresh Ubuntu often has no curl)
    fetch() {
        if command -v curl >/dev/null 2>&1; then curl -LsSf "$1"; else wget -qO- "$1"; fi
    }

    # 1. uv: installs Python and the packages without needing admin rights or any Python already installed
    UV="$(command -v uv || true)"
    if [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ]; then
        UV="$HOME/.local/bin/uv"
    fi
    if [ -z "$UV" ] && [ -n "$WORKSHOP_MIRROR" ]; then
        echo "[..] Installing uv from the organisers' laptop"
        mkdir -p "$HOME/.local/bin"
        if fetch "$WORKSHOP_MIRROR/uv/uv-x86_64-unknown-linux-gnu.tar.gz" | tar xz --strip-components=1 -C "$HOME/.local/bin"; then
            UV="$HOME/.local/bin/uv"
        fi
    fi
    if [ -z "$UV" ]; then
        echo "[..] Installing uv (it gets Python for the GCS)"
        fetch https://astral.sh/uv/install.sh | sh
        UV="$HOME/.local/bin/uv"
    fi
    echo "[ok] uv: $UV"

    # 2. Python for the GCS: from the organisers' laptop if this laptop has none (otherwise uv gets it from the internet)
    if [ -n "$WORKSHOP_MIRROR" ] && ! "$UV" python find "$PYTHON_VERSION" >/dev/null 2>&1; then
        echo "[..] Python $PYTHON_VERSION from the organisers' laptop"
        UV_PYTHON_INSTALL_MIRROR="$WORKSHOP_MIRROR/python" "$UV" python install "$PYTHON_VERSION" || true
    fi

    # 3. start.py does the rest: next to this script, or in the workshop code, or downloaded
    START_PY=""
    if [ -f "$0" ] && [ -f "$(dirname "$0")/start.py" ]; then
        START_PY="$(dirname "$0")/start.py"
    elif [ -f "$HOME/ardupilot-workshop/setup/start.py" ]; then
        START_PY="$HOME/ardupilot-workshop/setup/start.py"
    else
        START_PY="$(mktemp -d)/start.py"
        if [ -z "$WORKSHOP_MIRROR" ] || ! fetch "$WORKSHOP_MIRROR/start.py" > "$START_PY"; then
            fetch "$START_PY_URL" > "$START_PY"
        fi
    fi
    exec "$UV" run --no-project --python "$PYTHON_VERSION" "$START_PY" "$@"
}

main "$@"
