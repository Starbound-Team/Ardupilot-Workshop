"""
Starting SITL planes ourselves, without sim_vehicle.py: used by the GCS backend (a plane on this laptop) and by
live-map/sitl_agent.py (the planes the organisers host).

A plane started here can be moved: its start position is in its SIM_OPOS_* parameters instead of on the command
line (--home), so setting them and rebooting puts it down somewhere else. That's how the GCS moves its plane to
its corner before a round. sim_vehicle.py always passes --home, so a plane started that way can't be moved.
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

LAUNCH = (39.360886, 22.945749, 0, 0) # The workshop launch point: lat, lon, altitude, heading
WINDOWS = os.name == "nt"
BASE_PORT = 5760 # Instance N listens on BASE_PORT + 10 * N
RELAY_OFFSET = 5 # Windows: the plane connects to its relay on its port + 5 (+1 to +3 are its other serial ports)


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
        # ArduPilot's Windows build quits whenever its GCS disconnects (every save of workshop.py restarts the
        # backend), so it doesn't talk to the GCS itself: it connects out to a relay (below), which never hangs up
        # on it, and the GCS connects to the relay on the usual port. Both run without a console of their own,
        # so Ctrl+C in the GCS window doesn't reach them, and they outlive the backend.
        port = BASE_PORT + 10 * instance
        detached = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        with open(os.path.join(folder, "relay.log"), "a") as relay_log:
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "relay", str(port), str(port + RELAY_OFFSET)],
                             cwd=folder, stdout=relay_log, stderr=subprocess.STDOUT, creationflags=detached)
        for _ in range(50): # Until the relay listens for the plane (or one from before already does)
            with socket.socket() as probe: # Without connecting, which the relay would take for the plane
                try:
                    probe.bind(("127.0.0.1", port + RELAY_OFFSET))
                except OSError:
                    break # Taken: the relay is there
            time.sleep(0.1)
        command += ["--serial0", f"tcpclient:127.0.0.1:{port + RELAY_OFFSET}"]
        return subprocess.Popen(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT, creationflags=detached)
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
    """True once a plane started with start_plane waits for its GCS (it says so in its log, or on Windows its relay does)."""
    if WINDOWS:
        log_path, log_from = os.path.join(os.path.dirname(log_path), "relay.log"), 0
    try:
        with open(log_path, errors="replace") as f:
            f.seek(log_from)
            text = f.read()
    except FileNotFoundError:
        return False
    return "Waiting for connection" in text or "Connection on serial port" in text or "plane connected" in text


def relay(gcs_port, plane_port):
    """
    Windows: passes MAVLink between a plane (connecting in on plane_port) and its GCS (connecting in on gcs_port).
    When the GCS goes away (the backend restarts), the plane's connection stays open, so the plane keeps flying;
    the next GCS picks up where the last one left off. When the plane reboots (moved to its corner), it connects
    again. Runs until the plane has been gone for a minute.
    """
    ends = {"plane": None, "gcs": None}
    lock = threading.Lock()

    def listen(port, host):
        server = socket.socket() # No SO_REUSEADDR: on Windows it would let a second relay take the same port
        try:
            server.bind((host, port))
        except OSError:
            print(f"relay: port {port} is taken, a relay must be running already", flush=True)
            sys.exit(0)
        server.listen(1)
        return server

    def forward(name, other):
        """Reads from one end and writes to the other until this end closes; the other end stays open."""
        conn = ends[name]
        while True:
            try:
                data = conn.recv(65536)
            except OSError:
                data = b""
            if not data:
                break
            with lock:
                target = ends[other]
            if target is not None:
                try:
                    target.sendall(data)
                except OSError:
                    pass # The other end is gone: its own reader tidies up
        with lock:
            if ends[name] is conn:
                ends[name] = None
        conn.close()
        print(f"relay: {name} disconnected", flush=True)

    def accept(server, name, other):
        while True:
            conn, _ = server.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with lock:
                old, ends[name] = ends[name], conn
            if old is not None:
                old.close() # A newer one replaces it
            print(f"relay: {name} connected", flush=True)
            threading.Thread(target=forward, args=(name, other), daemon=True).start()

    gcs_server = listen(gcs_port, "0.0.0.0") # The GCS may be on another laptop (planes the organisers host)
    plane_server = listen(plane_port, "127.0.0.1")
    print(f"relay: GCS on port {gcs_port}, plane on port {plane_port}", flush=True)
    threading.Thread(target=accept, args=(plane_server, "plane", "gcs"), daemon=True).start()
    threading.Thread(target=accept, args=(gcs_server, "gcs", "plane"), daemon=True).start()
    gone_since = time.time()
    while True:
        time.sleep(1)
        with lock:
            if ends["plane"] is not None:
                gone_since = time.time()
        if time.time() - gone_since > 60:
            print("relay: no plane for a minute, stopping", flush=True)
            return


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "relay":
    relay(int(sys.argv[2]), int(sys.argv[3]))
