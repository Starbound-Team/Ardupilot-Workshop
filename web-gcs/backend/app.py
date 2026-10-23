import time
import collections
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping # Fix for newer Python versions with dronekit

from flask import Flask, jsonify, request
from flask_cors import CORS # Import CORS
# Make sure all necessary DroneKit classes are imported
from dronekit import connect, VehicleMode, APIException, LocationGlobalRelative, Command
from pymavlink import mavutil
import logging
import math
import json
import socket
import threading
import urllib.request
import uuid
import os
import traceback

WORKSHOP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workshop.py')


def describe_workshop_error(e):
    """Where the mistake in workshop.py is, in one line for the page: "line 12: invalid syntax"."""
    if isinstance(e, SyntaxError):
        return f"line {e.lineno}: {e.msg}"
    lines = [frame.lineno for frame in traceback.extract_tb(e.__traceback__) if frame.filename == WORKSHOP_FILE]
    where = f"line {lines[-1]}: " if lines else ""
    return f"{where}{type(e).__name__}: {e}"


#workshop
# A mistake in workshop.py mustn't stop the backend: it keeps running without the plane,
# and the next save of workshop.py restarts it as usual
try:
    from workshop import *
    WORKSHOP_ERROR = None
except Exception as e:
    traceback.print_exc()
    WORKSHOP_ERROR = describe_workshop_error(e)
    PILOT_NAME = GAME_SERVER_URL = SITL_ADDRESS = ""
import game
import local_sitl

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Variables ---
vehicle = None
connection_string = None # Where the plane is, decided on Connect (see plane_address)
plane_movable = False # True if the plane can be moved to its corner before a round (see local_sitl.py)
moving = False # True while the plane is being moved to its corner: it reboots and we reconnect
connect_progress = None # What Connect is waiting for, for the page to show
OWN_SITL = 'udp:127.0.0.1:14550' # SITL on this laptop started with sim_vehicle.py (its MAVProxy output)
SITL_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sitl') # The plane we start ourselves
PLANE_WAIT = 90 # Seconds to wait for the game server to start our plane
live_map_thread = None
LIVE_MAP_INTERVAL = 0.5 # Seconds between telemetry updates sent to the game server


def gcs_id():
    """A random id for this GCS, kept in a file, so the game server knows it's the same player
    after a restart or a new Wi-Fi address."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.gcs_id')
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        new_id = uuid.uuid4().hex
        with open(path, 'w') as f:
            f.write(new_id)
        return new_id


GCS_ID = gcs_id()
# New on every start, so the page can tell the backend restarted (workshop.py saved) and reconnect by itself
BACKEND_START = uuid.uuid4().hex


class NoPlane(Exception):
    """Why Connect can't find a plane, said so the page can show it."""


def plane_address(source):
    """
    Which plane to fly, like a real GCS: an address in SITL_ADDRESS always wins; otherwise the one chosen
    with the arrow next to Connect, "server" (the game server's plane for us) or "local" (a SITL on this
    laptop). It never switches by itself: connection trouble often clears up on its own, so a server that
    doesn't answer is asked again until PLANE_WAIT runs out.
    Returns (address, True if the plane can be moved to its corner before a round).
    """
    if SITL_ADDRESS.strip():
        return SITL_ADDRESS.strip(), False
    if source == "local":
        return local_plane()
    return server_plane()


def server_plane():
    """Our plane on the game server: it starts one the first time we ask, then it stays ours."""
    global connect_progress
    if not GAME_SERVER_URL.strip():
        raise NoPlane("GAME_SERVER_URL is empty in workshop.py: set it, or choose Local SITL with the arrow next to Connect")
    url = GAME_SERVER_URL.strip().rstrip('/') + '/api/sitl'
    deadline = time.time() + PLANE_WAIT
    problem = None
    while time.time() < deadline:
        try:
            request_plane = urllib.request.Request(url, data=json.dumps({"id": GCS_ID}).encode(),
                                                   headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request_plane, timeout=3) as response:
                answer = json.load(response)
        except Exception as e:
            if problem is None or not problem.startswith("the game server"):
                logging.warning(f"Game server doesn't answer ({e}): asking again until it does")
            problem = f"the game server at {GAME_SERVER_URL} doesn't answer ({e})"
            connect_progress = f"Game server not answering, still trying... (or ▾ for a local SITL)"
            time.sleep(2)
            continue
        if answer.get("state") == "ready":
            logging.info(f"Our plane on the server: {answer['address']}")
            return answer["address"], True
        if answer.get("state") == "none":
            raise NoPlane(f"No plane from the game server ({answer.get('reason')}). "
                          "Choose Local SITL with the arrow next to Connect to fly one on this laptop")
        logging.info("Waiting for the game server to start our plane...")
        problem = "the game server's plane is still starting"
        connect_progress = "The game server is starting your plane..."
        time.sleep(1)
    raise NoPlane(f"No plane after {PLANE_WAIT} s: {problem}. Check GAME_SERVER_URL in workshop.py, "
                  "or choose Local SITL with the arrow next to Connect")


def sim_vehicle_running():
    """True if a SITL started with sim_vehicle.py sends to OWN_SITL (its heartbeat comes every second)."""
    listener = None
    try:
        listener = mavutil.mavlink_connection(OWN_SITL.replace('udp:', 'udpin:'))
        return listener.wait_heartbeat(timeout=3) is not None
    except OSError:
        return False
    finally:
        if listener:
            listener.close()


def own_sitl_running():
    """True if the plane we started earlier still runs (it outlives backend restarts)."""
    try:
        with open(os.path.join(SITL_FOLDER, 'pid')) as f:
            pid = int(f.read())
    except (OSError, ValueError):
        return False
    return local_sitl.is_running(pid)


def local_plane():
    """A SITL on this laptop: one started with sim_vehicle.py if it runs (it can't be moved), else our own."""
    global connect_progress
    if sim_vehicle_running():
        return OWN_SITL, False
    log_path = os.path.join(SITL_FOLDER, 'sitl.log')
    if not own_sitl_running():
        ardupilot, problem = local_sitl.find_ardupilot()
        if not ardupilot:
            raise NoPlane(f"No SITL running on this laptop, and none to start: {problem}. "
                          "Start one with sim_vehicle.py -v plane, or choose Server plane with the arrow next to Connect")
        connect_progress = "Starting a SITL plane on this laptop..."
        os.makedirs(SITL_FOLDER, exist_ok=True)
        with open(log_path, 'w') as log:
            process = local_sitl.start_plane(ardupilot, 0, SITL_FOLDER, log)
        with open(os.path.join(SITL_FOLDER, 'pid'), 'w') as f:
            f.write(str(process.pid))
        logging.info(f"Started our own SITL from {ardupilot} (log: {log_path})")
        deadline = time.time() + 30
        while not local_sitl.listening(log_path) and time.time() < deadline:
            time.sleep(0.5)
    return f'tcp:127.0.0.1:{local_sitl.BASE_PORT}', True


# --- Flask App Setup ---
# The backend also serves the GCS page itself, so the browser opens http://localhost:5000
PORT = int(os.environ.get('GCS_PORT', 5000)) # Another port only for running two GCSes on one laptop
FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend')
app = Flask(__name__, static_folder=FRONTEND, static_url_path='')
CORS(app) # Enable CORS for all routes, allowing requests from your frontend


# --- Game server (and the live map on the projector) ---
def live_map_loop():
    """
    Runs in a background thread and sends the vehicle's telemetry to the game server every
    LIVE_MAP_INTERVAL seconds; the answer is this player's view of the game, kept in game.py.
    Does nothing if GAME_SERVER_URL is empty. A failed send is logged once and retried,
    so the GCS keeps working without the server.
    """
    name = PILOT_NAME.strip() or socket.gethostname()
    url = GAME_SERVER_URL.rstrip('/') + '/api/telemetry'
    map_reachable = True

    while True:
        time.sleep(LIVE_MAP_INTERVAL)
        current_vehicle = vehicle # Read once, the global can become None at any time
        if not current_vehicle:
            continue

        try:
            location = current_vehicle.location.global_relative_frame
            if location is None or location.lat is None or location.lon is None:
                continue # No GPS position yet

            payload = {
                "id": GCS_ID,
                "name": name,
                "lat": location.lat,
                "lon": location.lon,
                "alt": location.alt,
                "heading": current_vehicle.heading,
                "groundspeed": current_vehicle.groundspeed,
                "mode": current_vehicle.mode.name,
                "armed": current_vehicle.armed,
                "have": game.landmarks_have(), # Which landmark changes we have, so the server only sends newer ones
            }
            request_to_map = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request_to_map, timeout=1) as response:
                game.set_server_state(json.load(response).get("game"))

            if not map_reachable:
                logging.info("Game server reachable again.")
                map_reachable = True
        except Exception as e:
            if map_reachable:
                logging.warning(f"Could not reach the game server at {url}: {e}")
                map_reachable = False


def start_live_map():
    """Starts the game server thread once, if a game server address is set."""
    global live_map_thread
    if not GAME_SERVER_URL.strip() or live_map_thread:
        return
    game.use_server(GAME_SERVER_URL.rstrip('/'), GCS_ID)
    live_map_thread = threading.Thread(target=live_map_loop, daemon=True)
    live_map_thread.start()
    logging.info(f"Playing on the game server at {GAME_SERVER_URL}")


# --- API Endpoints ---
@app.route('/')
def index():
    """The GCS page."""
    return app.send_static_file('index.html')

@app.route('/api/connect/options')
def connect_options():
    """What the page needs to pick the default plane: Server plane if there's a game server, else Local SITL."""
    return jsonify({"status": "success", "server": bool(GAME_SERVER_URL.strip()), "sitl_address": SITL_ADDRESS.strip()})


def use_connected(new_vehicle):
    """Everything a freshly connected plane needs, on Connect and after moving it to its corner."""
    global vehicle
    # A plane circles this far from a GUIDED target. The SITL default (80 m) keeps it too far
    # from the workshop's waypoints, so every plane gets the same tighter circle.
    try:
        new_vehicle.parameters['WP_LOITER_RAD'] = 30
    except Exception as e:
        logging.warning(f"Could not set WP_LOITER_RAD: {e}")
    vehicle = new_vehicle
    start_live_map()
    game.use_vehicle(vehicle, move_plane if plane_movable else None)


def reboot(current):
    """Restarts the simulator with a forced reboot over MAVLink and closes our connection to it."""
    # MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN: param1 = 1 reboots; param6 = 20190226 forces it even while armed
    current.send_mavlink(current.message_factory.command_long_encode(
        0, 0, mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0, 1, 0, 0, 0, 0, 20190226, 0))
    logging.info("SITL reset: reboot sent")
    time.sleep(1)
    current.close()


def set_start_position(current, lat, lon, heading):
    """Where the simulator puts the plane down when it next starts (only for a plane local_sitl.py started)."""
    for name, value in (('SIM_OPOS_LAT', lat), ('SIM_OPOS_LNG', lon), ('SIM_OPOS_HDG', heading)):
        current.parameters[name] = value


def move_plane(lat, lon, heading):
    """
    Before a round: puts our plane down at its start position (lat, lon), facing heading, by setting where
    the simulator starts and rebooting it, then reconnects. Runs in its own thread (game.py starts it).
    """
    global vehicle, moving
    current = vehicle
    if not current or moving:
        return
    moving = True
    try:
        game.stop_all()
        game.take_control()
        set_start_position(current, lat, lon, heading)
        vehicle = None
        game.use_vehicle(None)
        reboot(current)
        time.sleep(8) # Connecting during the reboot only gets errors
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                use_connected(connect(connection_string, wait_ready=True, timeout=30, heartbeat_timeout=15))
                logging.info("Plane at its start position, reconnected")
                return
            except Exception as e:
                logging.info(f"Plane not back yet ({e})")
                time.sleep(2)
        logging.error("The plane didn't come back after moving it: click Connect")
    finally:
        moving = False


@app.route('/api/connect', methods=['POST'])
def connect_drone():
    """Attempts to connect to the drone via DroneKit. Body: {"source": "server" or "local"}, see plane_address."""
    global vehicle
    global connection_string, plane_movable, connect_progress

    if WORKSHOP_ERROR:
        return jsonify({"status": "error", "message": f"workshop.py has a mistake, {WORKSHOP_ERROR}. Fix it and save"}), 500

    # Prevent reconnecting if already connected
    if vehicle:
         logging.info("Already connected.")
         return jsonify({"status": "success", "message": "Already connected"})

    source = (request.get_json(silent=True) or {}).get('source')
    try:
        connection_string, plane_movable = plane_address(source)
    except NoPlane as e:
        logging.warning(f"No plane: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        connect_progress = None
    logging.info(f"Attempting connection to {connection_string}...")
    try:
        # Connect to the Vehicle
        # wait_ready=True waits for parameters, mode, armed status, etc.
        # heartbeat_timeout checks for MAVLink heartbeat
        vehicle = connect(connection_string, wait_ready=True, timeout=60, heartbeat_timeout=30)

        # Check if connection object was successfully created
        if not vehicle:
             # This case might be rare if connect raises exceptions on failure
            logging.error("Connection attempt returned None without raising an exception.")
            vehicle = None
            return jsonify({"status": "error", "message": "Failed to connect (vehicle object is None)"}), 500

        logging.info("Connection Successful!")
        # Log some details after connection
        try:
            logging.info(f"  Mode: {vehicle.mode.name}")
            logging.info(f"  Armed: {vehicle.armed}")
            # wait_for_location might be useful if GPS takes time after connection
            # vehicle.wait_for_location(timeout=10)
            alt = vehicle.location.global_relative_frame.alt if vehicle.location.global_relative_frame else 'N/A'
            lat = vehicle.location.global_relative_frame.lat if vehicle.location.global_relative_frame else 'N/A'
            lon = vehicle.location.global_relative_frame.lon if vehicle.location.global_relative_frame else 'N/A'
            logging.info(f"  Location: Lat={lat}, Lon={lon}, Alt={alt}")
            logging.info(f"  System status: {vehicle.system_status.state}")
            logging.info(f"  Is Armable: {vehicle.is_armable}")
        except Exception as e:
             logging.warning(f"Could not retrieve all vehicle details immediately after connection: {e}")

        use_connected(vehicle)

        return jsonify({"status": "success", "message": "Connected to Vehicle"})

    # Specific DroneKit exceptions
    except APIException as e:
        logging.error(f"DroneKit API Connection Exception: {e}", exc_info=True)
        vehicle = None
        return jsonify({"status": "error", "message": f"DroneKit API Error: {e}"}), 500
    # Timeout specific to the connect() call
    except TimeoutError: # This specifically catches connect(timeout=...)
         logging.error(f"Connection timed out after specified duration.")
         vehicle = None
         return jsonify({"status": "error", "message": f"Connection timed out."}), 500
    # Catch other potential exceptions during connection
    except Exception as e:
        logging.error(f"An unexpected error occurred during connection: {e}", exc_info=True)
        vehicle = None
        return jsonify({"status": "error", "message": f"Unexpected Error connecting: {e}"}), 500


@app.route('/api/disconnect', methods=['POST'])
def disconnect_drone():
    """Disconnects the DroneKit vehicle object."""
    global vehicle
    game.stop_all()
    game.use_vehicle(None)
    if vehicle:
        logging.info("Closing vehicle connection...")
        try:
            vehicle.close()
            vehicle = None # Set to None after closing
            logging.info("Vehicle connection closed.")
            return jsonify({"status": "success", "message": "Disconnected"})
        except Exception as e:
            logging.error(f"Error during vehicle.close(): {e}", exc_info=True)
            # Ensure vehicle is set to None even if close() fails
            vehicle = None
            return jsonify({"status": "error", "message": f"Error closing connection: {e}"}), 500
    else:
        logging.info("No active vehicle connection to disconnect.")
        return jsonify({"status": "success", "message": "Already disconnected"})


@app.route('/api/status')
def get_status():
    """Gets basic vehicle status if connected."""
    # Check if vehicle object exists and is connected
    if vehicle:
         try:
             # Safely access location attributes
             lat, lon, alt = None, None, None
             if vehicle.location.global_relative_frame:
                 lat = vehicle.location.global_relative_frame.lat
                 lon = vehicle.location.global_relative_frame.lon
                 alt = vehicle.location.global_relative_frame.alt

             # Safely access battery attributes
             batt_voltage, batt_level = None, None
             if vehicle.battery:
                batt_voltage = vehicle.battery.voltage
                batt_level = vehicle.battery.level # Battery level percentage

             status = {
                 "is_connected": True,
                 "backend_start": BACKEND_START,
                 "mode": vehicle.mode.name,
                 "armed": vehicle.armed,
                 "is_armable": vehicle.is_armable, # Important for user feedback
                 "lat": lat,
                 "lon": lon,
                 "alt": alt,
                 "airspeed": vehicle.airspeed if hasattr(vehicle, 'airspeed') else None,
                 "groundspeed": vehicle.groundspeed if hasattr(vehicle, 'groundspeed') else None,
                 "heading": vehicle.heading if hasattr(vehicle, 'heading') else None,
                 "battery_voltage": batt_voltage,
                 "battery_level": batt_level,
                 "system_status": vehicle.system_status.state,
                 "ekf_ok": vehicle.ekf_ok if hasattr(vehicle, 'ekf_ok') else None, # EKF status
                 "running_buttons": game.running_buttons(),
                 "camera_ready": game.camera_ready(),
                 "target": game.current_target(vehicle),
                 "score": game.score(),
                 "round": game.round_info(),
                 "others": game.other_drones_for_map(),
                 "photo_log": game.photo_log(),
                 "button_error": game.last_error(),
             }
             return jsonify({"status": "success", "data": status})
         except APIException as e:
             # Handle potential API errors during status fetching
             logging.error(f"DroneKit API Error fetching status: {e}", exc_info=True)
             return jsonify({"status": "error", "message": f"API Error fetching status: {e}"}), 500
         except Exception as e:
             logging.error(f"Error fetching status: {e}", exc_info=True)
             return jsonify({"status": "error", "message": f"Error fetching status: {e}"}), 500
    else:
        # Explicitly handle case where vehicle exists but is not connected
        if vehicle:
            logging.warning("Status requested, but vehicle object exists but is not connected.")
        return jsonify({"status": "success", "data": {"is_connected": False, "backend_start": BACKEND_START,
                                                      "workshop_error": WORKSHOP_ERROR, "moving": moving,
                                                      "connect_progress": connect_progress}})


@app.route('/api/takeoff', methods=['POST'])
def takeoff():
    """
    Commands the vehicle to take off to a specified altitude.
    Handles mode setting (GUIDED), arming, and takeoff command.
    """
    global vehicle
    # 1. Check connection
    if not vehicle:
        logging.warning("Takeoff request failed: Vehicle not connected.")
        # 400 Bad Request is suitable as the client made a request that cannot be fulfilled due to state
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 400

    try:
        # 2. Receive and validate altitude from JSON body
        data = request.get_json()
        if not data or 'altitude' not in data:
            logging.warning("Takeoff request failed: Missing 'altitude' in request.")
            return jsonify({"status": "error", "message": "Missing 'altitude' in request body"}), 400

        target_altitude = float(data['altitude'])
        logging.info(f"Commanding takeoff to {target_altitude}m...")
        game.take_control()
        take_off(vehicle, target_altitude)

        logging.info("Takeoff completed.")
        return jsonify({
            "status": "success", 
            "message": f"Takeoff to {target_altitude}m initiated",
            "details": {
                "altitude": target_altitude
            }
        })

    except APIException as e:
        # Catch specific DroneKit errors during the process
        logging.error(f"DroneKit API Exception during takeoff sequence: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"DroneKit API Error during takeoff: {e}"}), 500
    except Exception as e:
        # Catch any other unexpected errors
        logging.error(f"An unexpected error occurred during takeoff: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Unexpected Error during takeoff: {e}"}), 500

@app.route('/api/rtl', methods=['POST'])
def rtl():
    """Return to Launch (RTL) command."""
    global vehicle
    if vehicle:
        game.take_control() # Manual commands take the plane over from a running button
        logging.info("Returning to Launch...")
        vehicle.mode = VehicleMode("RTL")
        return jsonify({"status": "success", "message": "Returning to Launch"})
    else:
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 500

@app.route('/api/land', methods=['POST'])
def land():
    """Lands the plane at a lat/lon coordinate (a plane's RTL only circles above home)."""
    global vehicle
    if not vehicle:
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 400

    try:
        data = request.get_json()
        if not data or 'lat' not in data or 'lng' not in data:
            return jsonify({"status": "error", "message": "Missing required parameters (lat, lng)"}), 400

        target_lat = float(data['lat'])
        target_lng = float(data['lng'])
        game.take_control()
        logging.info(f"Landing at: lat={target_lat}, lon={target_lng}")
        land_at(vehicle, target_lat, target_lng)
        return jsonify({"status": "success", "message": "Landing"})
    except ValueError as e:
        logging.error(f"Invalid coordinates: {e}")
        return jsonify({"status": "error", "message": f"Invalid coordinates: {e}"}), 400
    except Exception as e:
        logging.error(f"Error during land command: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Error: {e}"}), 500

@app.route('/api/goto', methods=['POST'])
def goto_point():
    """Commands the vehicle to go to a specific lat/lon coordinate."""
    global vehicle
    if not vehicle:
        logging.warning("Goto request failed: Vehicle not connected.")
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 400

    try:
        # Get coordinates from the request
        data = request.get_json()
        if not data or 'lat' not in data or 'lng' not in data:
            return jsonify({"status": "error", 
                           "message": "Missing required parameters (lat, lng)"}), 400

        # Get altitude from request or use current altitude
        target_lat = float(data['lat'])
        target_lng = float(data['lng'])
        
        # Use provided altitude or default to current altitude + 5m
        if 'altitude' in data and data['altitude'] is not None:
            target_alt = float(data['altitude'])
        elif vehicle.location.global_relative_frame and \
             vehicle.location.global_relative_frame.alt is not None:
            # Use current altitude if available
            target_alt = vehicle.location.global_relative_frame.alt
        else:
            # Default altitude if current altitude unknown
            target_alt = 20.0
            
        logging.info(f"Going to: lat={target_lat}, lon={target_lng}, alt={target_alt}m")
        
        game.take_control()

        # Ensure vehicle is in GUIDED mode
        if vehicle.mode.name != "GUIDED":
            logging.info("Changing to GUIDED mode for goto command")
            vehicle.mode = VehicleMode("GUIDED")
            # Wait briefly for mode change
            time.sleep(1)
            
        # Command the vehicle to move to the location
        target_location = LocationGlobalRelative(target_lat, target_lng, target_alt)
        vehicle.simple_goto(target_location)
        game.set_target(target_location)
        
        return jsonify({
            "status": "success", 
            "message": "Vehicle moving to target",
            "details": {
                "lat": target_lat,
                "lng": target_lng,
                "alt": target_alt
            }
        })
        
    except ValueError as e:
        logging.error(f"Invalid coordinates: {e}")
        return jsonify({"status": "error", "message": f"Invalid coordinates: {e}"}), 400
    except Exception as e:
        logging.error(f"Error during goto command: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Error: {e}"}), 500

@app.route('/api/reset_sitl', methods=['POST'])
def reset_sitl():
    """
    Restarts the simulator with a forced reboot over MAVLink: the plane is back on its runway (the launch
    point, also if a round moved it), disarmed. The connection is closed so that Connect sets everything up
    again (the GCS reconnects by itself after a few seconds).
    """
    global vehicle
    if not vehicle:
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 400
    game.stop_all()
    game.take_control()
    current = vehicle
    try:
        if plane_movable:
            set_start_position(current, *local_sitl.LAUNCH[:2], local_sitl.LAUNCH[3])
        reboot(current)
    finally:
        vehicle = None
        game.use_vehicle(None)
    return jsonify({"status": "success", "message": "Restarting the simulator"})

# --- Buttons from workshop.py ---
@app.route('/api/buttons')
def list_buttons():
    """The @button functions in workshop.py, in order. Those that take a location go in the right-click menu."""
    return jsonify({"status": "success", "buttons": [
        {"name": name, "location": game.takes_location(function)} for name, function in game.buttons.items()]})

@app.route('/api/buttons/run', methods=['POST'])
def run_button():
    """Runs a @button function in the background, or stops it if it is running."""
    if not vehicle:
        return jsonify({"status": "error", "message": "Vehicle not connected"}), 400
    data = request.get_json() or {}
    name = data.get('name')
    if name not in game.buttons:
        return jsonify({"status": "error", "message": f"No button called {name!r} in workshop.py"}), 400
    waypoints = [(float(lat), float(lng)) for lat, lng in data.get('waypoints', [])]
    location = data.get('location')
    if game.takes_location(game.buttons[name]) and not location:
        return jsonify({"status": "error", "message": f"{name} needs a point: use it from the right-click menu"}), 400
    started = game.run_button(name, vehicle, waypoints, location and (float(location[0]), float(location[1])))
    return jsonify({"status": "success", "message": f"{name} {'started' if started else 'stopped'}"})

@app.route('/api/landmarks')
def landmarks():
    """The landmarks this plane knows about, for the map."""
    if not vehicle:
        return jsonify({"status": "success", "landmarks": [], "area": game.game_area()})
    return jsonify({"status": "success", "area": game.game_area(), "landmarks": [
        {"name": lm.name, "lat": lm.loc.lat, "lon": lm.loc.lon, "approach_from": lm.approach_from,
         "view_width": lm.view_width, "inner": lm.inner, "outer": lm.outer, "price": lm.price, "public": lm.public,
         "sales": lm.sales, "head_start": lm.head_start, "age": lm.age}
        for lm in game.get_known_landmarks()]})

# --- Main Execution ---
if __name__ == '__main__':
    # Run on 0.0.0.0 to be accessible from other devices on the network if needed,
    # otherwise use 127.0.0.1 for local access only.
    # Debug=True auto-reloads on code changes, but disable for production.
    # extra_files: a workshop.py that failed to import isn't watched by itself, but its fix must restart us
    app.run(host='127.0.0.1', port=PORT, debug=True, extra_files=[WORKSHOP_FILE])