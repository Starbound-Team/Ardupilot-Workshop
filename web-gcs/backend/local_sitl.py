"""
Starting SITL planes ourselves, without sim_vehicle.py: used by the GCS backend (a plane on this laptop) and by
live-map/sitl_agent.py (the planes the organisers host).

A plane started here can be moved: its start position is in its SIM_OPOS_* parameters instead of on the command
line (--home), so setting them and rebooting puts it down somewhere else. That's how the GCS moves its plane to
its corner before a round. sim_vehicle.py always passes --home, so a plane started that way can't be moved.
"""
import os
import shutil
import subprocess

LAUNCH = (39.360886, 22.945749, 0, 0) # The workshop launch point: lat, lon, altitude, heading
WINDOWS = os.name == "nt"
BASE_PORT = 5760 # Instance N listens on BASE_PORT + 10 * N


def ardupilot_folders():
    """Where ArduPilot might be, most likely first."""
    folders = []
    if os.environ.get("ARDUPILOT_DIR"):
        folders.append(os.environ["ARDUPILOT_DIR"])
    # What the workshop's setup script installs: just build/sitl/bin/arduplane and Tools/autotest/models/plane.parm
    folders.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sitl"))
    sim_vehicle = shutil.which("sim_vehicle.py") # ArduPilot's setup puts Tools/autotest on the PATH
    if sim_vehicle:
        folders.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(sim_vehicle)))))
    folders += [os.path.expanduser("~/.ardupilot/ardupilot"), os.path.expanduser("~/ardupilot")]
    return [os.path.abspath(folder) for folder in folders]


def binary(ardupilot):
    """The plane program in an ArduPilot folder. ArduPilot's Windows build is ArduPlane.elf, with its cyg*.dll files next to it."""
    return os.path.join(ardupilot, "build", "sitl", "bin", "ArduPlane.elf" if WINDOWS else "arduplane")


def find_ardupilot():
    """(ArduPilot folder with the plane built, None) or (None, why not)."""
    folders = ardupilot_folders()
    for folder in folders:
        if os.path.exists(binary(folder)):
            return folder, None
    found = [folder for folder in folders if os.path.isdir(os.path.join(folder, "Tools", "autotest"))]
    if found:
        return None, (f"ArduPilot is in {found[0]} but the plane isn't built: there, run "
                      "./waf configure --board sitl && ./waf plane")
    return None, f"no ArduPilot found (looked in {', '.join(dict.fromkeys(folders))})"


def start_plane(ardupilot, instance, folder, log):
    """
    Starts a plane on port BASE_PORT + 10 * instance, with fresh parameters, at the launch point. Its files
    (parameters, logs) go in folder. Returns the process; it keeps running if whoever started it stops.
    """
    os.makedirs(folder, exist_ok=True)
    # Only a default: parameters set later (moving the plane) are saved and win over it after a reboot
    with open(os.path.join(folder, "start.parm"), "w") as f:
        f.write("SIM_OPOS_LAT {}\nSIM_OPOS_LNG {}\nSIM_OPOS_ALT {}\nSIM_OPOS_HDG {}\n".format(*LAUNCH))
    defaults = os.path.join(ardupilot, "Tools", "autotest", "models", "plane.parm") + ",start.parm"
    command = [binary(ardupilot), "--model", "plane", "--speedup", "1", "-w", "--defaults", defaults, f"-I{instance}"]
    if WINDOWS:
        # Its own process group without a console: Ctrl+C in the GCS window doesn't reach it. (Tested under Wine
        # only: there it quits when its GCS disconnects, and the next Connect starts a new one.)
        return subprocess.Popen(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
    # SITL quits as soon as the process that started it is gone, so a small shell stays in between as its parent:
    # the plane then keeps running when the GCS backend restarts (every save of workshop.py restarts it)
    return subprocess.Popen(["sh", "-c", '"$@"; exit $?', "sh"] + command, cwd=folder, stdout=log,
                            stderr=subprocess.STDOUT, start_new_session=True)


def is_running(pid):
    """True if the plane started with process id pid still runs."""
    if WINDOWS:
        # Not os.kill(pid, 0): on Windows that ends the process instead of checking it
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid) # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        alive = kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259 # STILL_ACTIVE
        kernel32.CloseHandle(handle)
        return bool(alive)
    try:
        os.kill(pid, 0)
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"arduplane" in f.read()
    except OSError:
        return False


def listening(log_path, log_from=0):
    """True once a plane started with start_plane waits for its GCS (it says so in its log)."""
    try:
        with open(log_path, errors="replace") as f:
            f.seek(log_from)
            text = f.read()
    except FileNotFoundError:
        return False
    return "Waiting for connection" in text or "Connection on serial port" in text
