"""
SITL agent: hosts participants' planes on this laptop, started on demand by the game server.

Run it on every laptop that should host planes (the game server's laptop too). It checks in with the
server every second, starts the planes the server asks for, and starts a plane again if it stops.
Participants never see it: their GCS asks the server for a plane and gets this laptop's address.

Each plane is its own SITL process (instance 1, 2, ...) with its own folder and port, started directly
rather than with sim_vehicle.py, which would kill all the others.

Usage:  python sitl_agent.py http://192.168.1.50:8080 --key KEY --max 15
        (KEY is the organiser key the server prints; --max is how many planes this laptop may run)
Ctrl+C (or closing the terminal) stops its planes.
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

HOME = "39.360886,22.945749,0,0" # The workshop launch point: lat, lon, altitude, heading
BASE_PORT = 5760 # Instance N listens on BASE_PORT + 10 * N

parser = argparse.ArgumentParser()
parser.add_argument("server", help="Game server address, e.g. http://192.168.1.50:8080")
parser.add_argument("--key", required=True, help="The organiser key the server printed")
parser.add_argument("--max", type=int, default=10, help="How many planes this laptop may run")
parser.add_argument("--ip", help="This laptop's address as participants reach it (found by itself if left out)")
parser.add_argument("--ardupilot", default=os.path.expanduser("~/.ardupilot/ardupilot"),
                    help="ArduPilot folder with the plane built (build/sitl/bin/arduplane)")
args = parser.parse_args()

binary = os.path.join(args.ardupilot, "build", "sitl", "bin", "arduplane")
defaults = os.path.join(args.ardupilot, "Tools", "autotest", "models", "plane.parm")
if not os.path.exists(binary):
    sys.exit(f"No plane built at {binary}: build it with  ./waf configure --board sitl && ./waf plane")
folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "planes")
agent_id = uuid.uuid4().hex[:8]


def local_ip():
    """This laptop's address on the local network (no data is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


ip = args.ip or local_ip()
planes = {} # instance -> {"process", "log", "log_from"}


def start(instance):
    plane_folder = os.path.join(folder, str(instance))
    os.makedirs(plane_folder, exist_ok=True)
    log_path = os.path.join(plane_folder, "sitl.log")
    log_from = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    log = open(log_path, "a")
    # -w starts each plane with fresh parameters; Reset SITL reboots it in place
    process = subprocess.Popen([binary, "--model", "plane", "--speedup", "1", "-w", "--defaults", defaults,
                                f"-I{instance}", "--home", HOME],
                               cwd=plane_folder, stdout=log, stderr=subprocess.STDOUT)
    planes[instance] = {"process": process, "log": log_path, "log_from": log_from}
    print(f"Started a plane on port {BASE_PORT + 10 * instance}", flush=True)


def state(plane):
    """ready once SITL listens for its GCS (it says so in its log), starting before that."""
    with open(plane["log"], errors="replace") as f:
        f.seek(plane["log_from"])
        text = f.read()
    return "ready" if "Waiting for connection" in text or "Connection on serial port" in text else "starting"


def check_in():
    body = {"key": args.key, "agent": agent_id, "ip": ip, "max": args.max,
            "planes": {i: state(p) for i, p in planes.items()}}
    request = urllib.request.Request(args.server.rstrip("/") + "/api/agents/checkin", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.load(response)


def stop_on_signal(signum, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop_on_signal)
signal.signal(signal.SIGHUP, stop_on_signal)

print(f"Hosting up to {args.max} planes at {ip} for {args.server}. Ctrl+C stops them.", flush=True)
reachable = None
try:
    while True:
        for instance, plane in list(planes.items()):
            if plane["process"].poll() is not None:
                print(f"Plane on port {BASE_PORT + 10 * instance} stopped (exit {plane['process'].returncode}), "
                      "starting it again", flush=True)
                start(instance)
        try:
            answer = check_in()
            if answer.get("status") != "success":
                print(f"Server refused the check-in: {answer.get('message')}", flush=True)
            for instance in answer.get("start", []):
                if instance not in planes:
                    start(instance)
            if reachable is not True:
                print("Connected to the game server.", flush=True)
                reachable = True
        except Exception as e:
            if reachable is not False:
                print(f"Can't reach the game server ({e}); retrying, the planes keep running", flush=True)
                reachable = False
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping the planes...", flush=True)
finally:
    for plane in planes.values():
        plane["process"].terminate()
    for plane in planes.values():
        try:
            plane["process"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            plane["process"].kill()
