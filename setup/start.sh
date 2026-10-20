#!/bin/sh
# Sets up whatever is missing for the ArduPilot workshop and starts the GCS. Safe to run again.
#   curl -LsSf https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.sh | sh
# Options go to start.py, e.g. ... | sh -s -- --dir ~/somewhere-else
# Everything is in a function that runs on the last line, so a download cut short runs nothing.

main() {
    set -e
    START_PY_URL="https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.py"
    PYTHON_VERSION="3.12"

    # 1. uv: installs Python and the packages without needing admin rights or any Python already installed
    UV="$(command -v uv || true)"
    if [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ]; then
        UV="$HOME/.local/bin/uv"
    fi
    if [ -z "$UV" ]; then
        echo "[..] Installing uv (it gets Python for the GCS)"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        UV="$HOME/.local/bin/uv"
    fi
    echo "[ok] uv: $UV"

    # 2. start.py does the rest: next to this script, or in the workshop code, or downloaded
    START_PY=""
    if [ -f "$0" ] && [ -f "$(dirname "$0")/start.py" ]; then
        START_PY="$(dirname "$0")/start.py"
    elif [ -f "$HOME/ardupilot-workshop/setup/start.py" ]; then
        START_PY="$HOME/ardupilot-workshop/setup/start.py"
    else
        START_PY="$(mktemp -d)/start.py"
        curl -LsSf "$START_PY_URL" -o "$START_PY"
    fi
    exec "$UV" run --no-project --python "$PYTHON_VERSION" "$START_PY" "$@"
}

main "$@"
