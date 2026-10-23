"""
Prepares an offline copy of everything the setup downloads, for the organisers' laptop: the game server then serves
it at http://<server>:8080/setup/, and the one-liners pointed there work without internet (and fall back to the
internet for anything missing). Run it once, with internet, before the workshop:

    python3 setup/prepare_offline.py            (needs uv: the setup script installed it in ~/.local/bin)

It fills offline/ (next to setup/, not in git, about 150 MB):
    uv/       uv for Linux and Windows (the same version as here, so it asks for the Python builds below)
    python/   Python 3.12 builds for Linux and Windows, laid out as uv's UV_PYTHON_INSTALL_MIRROR expects
    wheels/   every package the GCS needs, for Linux and Windows (Python 3.12)
    code/     the workshop code, as GitHub's main.zip (what the setup would download)
    sitl/     the fallback plane for Linux and Windows (the workshop's GitHub release)
    start.sh, start.ps1, start.py
"""
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "offline")
REQUIREMENTS = os.path.join(ROOT, "web-gcs", "backend", "requirements.txt")
CODE_ZIP = "https://github.com/starbound-team/ardupilot-workshop/archive/refs/heads/main.zip"
SITL_RELEASE = "https://github.com/starbound-team/ardupilot-workshop/releases/download/sitl-2026-10/"
SITL_FILES = ["arduplane", "plane.parm", "ArduPlane.elf", "cygwin1.dll", "cygatomic-1.dll", "cyggcc_s-1.dll",
              "cyggcc_s-seh-1.dll", "cyggomp-1.dll", "cygiconv-2.dll", "cygintl-8.dll", "cygquadmath-0.dll",
              "cygssp-0.dll", "cygstdc++-6.dll"]
UV_TARGETS = {"uv-x86_64-unknown-linux-gnu.tar.gz", "uv-x86_64-pc-windows-msvc.zip"}
PYTHON_KEYS = ("linux-x86_64-gnu", "windows-x86_64-none")


def say(message):
    print(message, flush=True)


def download(url, target):
    """Downloads url to target, unless it's there already; a part file until complete."""
    if os.path.exists(target):
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    say(f"  {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ardupilot-workshop-prepare-offline"}) # Some servers refuse Python's own
    with urllib.request.urlopen(request, timeout=120) as response, open(target + ".part", "wb") as f:
        shutil.copyfileobj(response, f)
    os.replace(target + ".part", target)


def find_uv():
    for candidate in (shutil.which("uv"), os.path.expanduser("~/.local/bin/uv")):
        if candidate and os.path.isfile(candidate):
            return candidate
    sys.exit("No uv found: run the setup script once first (it installs uv), or install uv")


uv = find_uv()
version = subprocess.run([uv, "--version"], capture_output=True, text=True, check=True).stdout.split()[1]
say(f"uv {version}")
for name in UV_TARGETS:
    download(f"https://github.com/astral-sh/uv/releases/download/{version}/{name}", os.path.join(OUT, "uv", name))

say("Python 3.12 builds")
listing = subprocess.run([uv, "python", "list", "3.12", "--all-platforms", "--only-downloads", "--show-urls"],
                         capture_output=True, text=True, check=True).stdout
for key in PYTHON_KEYS:
    url = next(line.split()[1] for line in listing.splitlines() if line.startswith("cpython-") and key in line.split()[0])
    # UV_PYTHON_INSTALL_MIRROR replaces everything before <release tag>/<file>
    tag, name = url.rsplit("/", 2)[-2:]
    download(url, os.path.join(OUT, "python", tag, urllib.parse.unquote(name)))

say("Package wheels")
wheels = os.path.join(OUT, "wheels")
for platform in ("manylinux2014_x86_64", "win_amd64"):
    extra = ["colorama"] if platform == "win_amd64" else [] # click needs it on Windows only
    subprocess.run([uv, "tool", "run", "--from", "pip", "pip", "download", "-q", "-r", REQUIREMENTS, *extra,
                    "--only-binary=:all:", "--platform", platform, "--python-version", "3.12", "-d", wheels], check=True)
say(f"  {len(os.listdir(wheels))} wheels")

say("Code and plane")
code = os.path.join(OUT, "code", "main.zip")
if os.path.exists(code):
    os.remove(code) # Always the current code
download(CODE_ZIP, code)
for name in SITL_FILES:
    download(SITL_RELEASE + name, os.path.join(OUT, "sitl", name))
for name in ("start.sh", "start.ps1", "start.py"):
    shutil.copy(os.path.join(ROOT, "setup", name), os.path.join(OUT, name))

size = sum(os.path.getsize(os.path.join(d, f)) for d, _, files in os.walk(OUT) for f in files)
say(f"Done: {OUT}, {size / 1e6:.0f} MB. The game server serves it at http://<server>:8080/setup/")
