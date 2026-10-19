"""
Runs SITL planes on this laptop for participants who fly without installing anything.

Each plane is its own SITL process (instance 1, 2, ...) with its own folder and port, started directly
rather than with sim_vehicle.py, which would kill all the others. A plane that stops is started again.
Participants put the printed address in SITL_ADDRESS at the top of their workshop.py.

Usage:  python host_planes.py 6                    six planes
        python host_planes.py 6 --ardupilot ~/ardupilot
Ctrl+C stops them all.
"""
import argparse
import os
import signal
import socket
import subprocess
import sys
import time

HOME = "39.360886,22.945749,0,0" # The workshop launch point: lat, lon, altitude, heading

parser = argparse.ArgumentParser()
parser.add_argument("planes", type=int)
parser.add_argument("--ardupilot", default=os.path.expanduser("~/.ardupilot/ardupilot"),
                    help="ArduPilot folder with the plane built (build/sitl/bin/arduplane)")
parser.add_argument("--first", type=int, default=1, help="First instance number (0 is usually your own SITL)")
args = parser.parse_args()

binary = os.path.join(args.ardupilot, "build", "sitl", "bin", "arduplane")
defaults = os.path.join(args.ardupilot, "Tools", "autotest", "models", "plane.parm")
if not os.path.exists(binary):
    sys.exit(f"No plane built at {binary}: build it with  ./waf configure --board sitl && ./waf plane")
folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "planes")


def local_ip():
    """This laptop's address on the local network (no data is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def start(instance):
    plane_folder = os.path.join(folder, str(instance))
    os.makedirs(plane_folder, exist_ok=True)
    log = open(os.path.join(plane_folder, "sitl.log"), "a")
    # -w starts each plane with fresh parameters; a Reset SITL reboot keeps these arguments
    return subprocess.Popen([binary, "--model", "plane", "--speedup", "1", "-w", "--defaults", defaults,
                             f"-I{instance}", "--home", HOME],
                            cwd=plane_folder, stdout=log, stderr=subprocess.STDOUT)


def stop_on_signal(signum, frame):
    raise KeyboardInterrupt


# Closing the terminal or killing this script stops the planes too, like Ctrl+C
signal.signal(signal.SIGTERM, stop_on_signal)
signal.signal(signal.SIGHUP, stop_on_signal)

instances = range(args.first, args.first + args.planes)
planes = {instance: start(instance) for instance in instances}
ip = local_ip()
print(f"{args.planes} planes running. Give each participant one address for SITL_ADDRESS:")
for number, instance in enumerate(instances, 1):
    print(f"  Plane {number}:  tcp:{ip}:{5760 + 10 * instance}")
print("Each plane takes one connection at a time. Logs in", folder)
print("Ctrl+C stops them all.")

try:
    while True:
        time.sleep(2)
        for instance, process in planes.items():
            if process.poll() is not None:
                print(f"Plane on port {5760 + 10 * instance} stopped (exit {process.returncode}), starting it again")
                planes[instance] = start(instance)
except KeyboardInterrupt:
    print("Stopping the planes...")
finally:
    for process in planes.values():
        process.terminate()
    for process in planes.values():
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
