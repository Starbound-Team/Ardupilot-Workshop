"""
Sets up whatever is still missing for the ArduPilot workshop, then starts the GCS.
Safe to run again at any time: every step checks first and skips what is already done,
and code that is already there is never touched (your workshop.py stays as it is).

Normally started by start.sh (Linux) or start.ps1 / start.bat (Windows), which get uv first.
Runs on any Python 3.8+ without uv too, using venv and pip instead.
"""
import argparse
import io
import json
import os
import shutil
import socket
import subprocess
import platform
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile

PYTHON_VERSION = "3.12" # The Python the GCS runs on, downloaded by uv (every package has ready-made builds for it)
CODE_ZIP = "https://github.com/starbound-team/ardupilot-workshop/archive/refs/heads/main.zip"
GCS_URL = f"http://localhost:{os.environ.get('GCS_PORT', 5000)}" # GCS_PORT: the same setting as app.py's
# The fallback plane for this laptop: ArduPilot's own SITL build of ArduPlane 4.7.2 (static, runs on any 64-bit Linux)
# and its defaults, laid out like an ArduPilot folder so the backend's local_sitl.py finds it in <workshop>/sitl
SITL_FILES = {
    os.path.join("build", "sitl", "bin", "arduplane"):
        "https://firmware.ardupilot.org/Plane/stable-4.7.2/SITL_x86_64_linux_gnu/arduplane",
    os.path.join("Tools", "autotest", "models", "plane.parm"):
        "https://raw.githubusercontent.com/ArduPilot/ardupilot/Plane-4.7.2/Tools/autotest/models/plane.parm",
}
WINDOWS = os.name == "nt"

parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
parser.add_argument("--dir", default=os.path.join(os.path.expanduser("~"), "ardupilot-workshop"),
                    help="Where the workshop code goes (default: ardupilot-workshop in your home folder)")
parser.add_argument("--source", default=os.environ.get("WORKSHOP_SOURCE") or CODE_ZIP,
                    help="Where to get the code: a .zip URL or a local .zip file")
parser.add_argument("--sitl-source", default=os.environ.get("WORKSHOP_SITL"),
                    help="A local .tar.gz with the fallback SITL laid out like an ArduPilot folder, for setting up "
                         "without internet (default: download it from ArduPilot)")
parser.add_argument("--no-browser", action="store_true", help="Don't open the browser")
args = parser.parse_args()

workshop = os.path.abspath(args.dir)
backend = os.path.join(workshop, "web-gcs", "backend")
venv = os.path.join(backend, "venv")
venv_python = os.path.join(venv, "Scripts", "python.exe") if WINDOWS else os.path.join(venv, "bin", "python")
sitl = os.path.join(workshop, "sitl")
sitl_binary = os.path.join(sitl, "build", "sitl", "bin", "arduplane")


def done(message):
    print(f"[ok] {message}", flush=True)


def skipped(message):
    print(f"[--] {message}", flush=True)


def doing(message):
    print(f"[..] {message}", flush=True)


def fail(message):
    print(f"\n[!!] {message}", flush=True)
    sys.exit(1)


def find_uv():
    """uv, if we have it: uv run tells us where it is in UV, otherwise look for it."""
    for candidate in (os.environ.get("UV"), shutil.which("uv"),
                      os.path.join(os.path.expanduser("~"), ".local", "bin", "uv.exe" if WINDOWS else "uv")):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def run(command, what):
    """Runs a command, showing its output; stops with a message if it fails."""
    if subprocess.call(command) != 0:
        fail(f"{what} failed (see above). Ask an organiser, or run this again.")


# --- 1. The code ---
def get_code():
    if os.path.isfile(os.path.join(backend, "app.py")):
        done(f"Code: in {workshop}")
        return
    if os.path.exists(workshop) and os.listdir(workshop):
        fail(f"{workshop} already exists but has no workshop code in it. Move it away, or pick another folder with --dir.")

    doing(f"Getting the code from {args.source}")
    try:
        if os.path.isfile(args.source):
            with open(args.source, "rb") as f:
                data = f.read()
        else:
            with urllib.request.urlopen(args.source, timeout=60) as response:
                data = response.read()
    except Exception as e:
        fail(f"Could not get the code ({e}). Check the internet connection and run this again.")

    # GitHub's zips have everything inside one top folder (ardupilot-workshop-main/): unpack it, then move that
    with tempfile.TemporaryDirectory() as unpacked:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            archive.extractall(unpacked)
        top = os.listdir(unpacked)
        root = os.path.join(unpacked, top[0]) if len(top) == 1 else unpacked
        os.makedirs(os.path.dirname(workshop), exist_ok=True)
        if os.path.exists(workshop):
            os.rmdir(workshop) # Empty, checked above
        shutil.move(root, workshop)
    done(f"Code: in {workshop}")


# --- 2. Python and the packages ---
def packages_ok():
    if not os.path.isfile(venv_python):
        return False
    # dronekit needs app.py's fix for newer Pythons before it imports
    check = ("import collections, collections.abc; collections.MutableMapping = collections.abc.MutableMapping; "
             "import flask, flask_cors, dronekit, pymavlink, lxml")
    return subprocess.call([venv_python, "-c", check], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def get_python_and_packages():
    if packages_ok():
        done("Python and packages: ready")
        return
    uv = find_uv()
    requirements = os.path.join(backend, "requirements.txt")
    if not os.path.isfile(venv_python):
        doing(f"Making a Python {PYTHON_VERSION} environment for the GCS")
        if uv:
            run([uv, "venv", "--python", PYTHON_VERSION, venv], "Making the Python environment")
        else:
            run([sys.executable, "-m", "venv", venv], "Making the Python environment")
    doing("Installing the packages the GCS needs")
    if uv:
        run([uv, "pip", "install", "--python", venv_python, "-r", requirements], "Installing the packages")
    else:
        run([venv_python, "-m", "pip", "install", "-r", requirements], "Installing the packages")
    if not packages_ok():
        fail("The packages installed, but the GCS still can't import them. Ask an organiser.")
    done("Python and packages: ready")


# --- 3. A plane on this laptop, in case the organisers' planes can't be reached ---
def sitl_runs():
    if not os.path.isfile(sitl_binary):
        return False
    try:
        result = subprocess.run([sitl_binary, "--help"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return b"--model" in result.stdout


def get_local_sitl():
    """Optional: everything works without it as long as the organisers' planes can be reached, so it never stops the setup."""
    if WINDOWS or sys.platform != "linux" or platform.machine() not in ("x86_64", "AMD64"):
        skipped("Local SITL: not available on this system yet (you fly the organisers' planes)")
        return
    if sitl_runs():
        done("Local SITL: ready")
        return
    try:
        if args.sitl_source:
            doing(f"Unpacking a SITL plane for this laptop from {args.sitl_source}")
            with tarfile.open(args.sitl_source) as archive:
                for member in archive.getmembers():
                    if member.name.startswith("/") or ".." in member.name.split("/"):
                        raise ValueError(f"unexpected path in the archive: {member.name}")
                if hasattr(tarfile, "data_filter"): # Python 3.12+: the safe way, and no warning
                    archive.extractall(sitl, filter="data")
                else:
                    archive.extractall(sitl)
        else:
            doing("Getting a SITL plane for this laptop from ArduPilot (ArduPlane 4.7.2, about 7 MB)")
            for path, url in SITL_FILES.items():
                target = os.path.join(sitl, path)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read()
                with open(target + ".part", "wb") as f: # Only a complete download gets the real name
                    f.write(data)
                os.replace(target + ".part", target)
        os.chmod(sitl_binary, 0o755)
    except Exception as e:
        skipped(f"Local SITL: could not get it ({e}). Not needed while the organisers' planes work; run this again later")
        return
    if sitl_runs():
        done("Local SITL: ready")
    else:
        skipped("Local SITL: downloaded, but it doesn't run on this laptop. Not needed while the organisers' planes work")


# --- 4. The GCS ---
def gcs_running():
    """Whether our GCS answers on its port (not just any program that happens to use it)."""
    try:
        with urllib.request.urlopen(GCS_URL + "/api/status", timeout=2) as response:
            return "backend_start" in json.load(response).get("data", {})
    except Exception:
        return False


def open_browser_when_ready():
    for _ in range(120):
        if gcs_running():
            webbrowser.open(GCS_URL)
            return
        time.sleep(0.5)


def start_gcs():
    print(f"\nYour code: {os.path.join(backend, 'workshop.py')}", flush=True)
    if gcs_running():
        done(f"GCS: already running, at {GCS_URL}")
        if not args.no_browser:
            webbrowser.open(GCS_URL)
        return

    port = int(GCS_URL.rsplit(":", 1)[1])
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            fail(f"Another program is using port {port}, so the GCS can't start. Close it (or another GCS window) and run this again.")
    print(f"Starting the GCS at {GCS_URL}. Leave this window open: the GCS stops when it closes (or with Ctrl+C).\n", flush=True)
    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready, daemon=True).start()
    try:
        subprocess.call([venv_python, "app.py"], cwd=backend)
    except KeyboardInterrupt:
        pass
    print("\nThe GCS stopped. Run this again to start it.")


get_code()
get_python_and_packages()
get_local_sitl()
start_gcs()
