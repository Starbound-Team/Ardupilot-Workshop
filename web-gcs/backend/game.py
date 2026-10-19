#Everything in this file is already written for you: use it from workshop.py, but don't change it.
#The cheat sheet says which part of the workshop needs what.
import collections
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping # Fix for newer Python versions with dronekit
import ctypes
import logging
import math
import random
import threading
import time

from dronekit import VehicleMode, LocationGlobalRelative, Command
from pymavlink import mavutil

__all__ = ['get_distance_meters', 'get_direction_degrees', 'get_location_from', 'get_angle_between', 'get_turn_meters',
           'land_at', 'get_clicked_waypoints', 'Landmark', 'get_known_landmarks', 'get_other_drones', 'take_photo',
           'button', 'CRUISE_SPEED', 'SWING_METERS', 'FIELD_OF_VIEW'] # What workshop.py gets from "from game import *"

METERS_PER_DEGREE = 111319.5
CRUISE_SPEED = 20 # m/s, how fast the plane flies in GUIDED mode
TURN_RADIUS = 35 # m, roughly how tightly the plane turns
SWING_METERS = 55 # m, how far a turn swings the plane sideways (measured: a U-turn swings it 2 * 55 m)
FIELD_OF_VIEW = 60 # degrees, the camera sees 30 degrees either side of the nose
FLYING_ALTITUDE = 30 # m, landmarks and clicked waypoints are at this altitude


# ---------- Measuring ----------
def get_distance_meters(location1, location2):
    """Metres between two locations (flat-earth approximation, fine for a few km)."""
    if location1 is None or location2 is None or None in (location1.lat, location1.lon, location2.lat, location2.lon):
        logging.warning("Attempted to calculate distance with invalid location(s).")
        return float('inf') # Return infinite distance for invalid input
    north = (location2.lat - location1.lat) * METERS_PER_DEGREE
    east = (location2.lon - location1.lon) * METERS_PER_DEGREE * math.cos(math.radians(location1.lat))
    return math.hypot(north, east)


def get_direction_degrees(location1, location2):
    """Compass direction from location1 to location2: 0 = north, 90 = east, 180 = south, 270 = west."""
    north = (location2.lat - location1.lat) * METERS_PER_DEGREE
    east = (location2.lon - location1.lon) * METERS_PER_DEGREE * math.cos(math.radians(location1.lat))
    return math.degrees(math.atan2(east, north)) % 360


def get_location_from(location, distance, direction):
    """The location distance metres away from location, in the compass direction direction."""
    d = math.radians(direction)
    return LocationGlobalRelative(
        location.lat + distance * math.cos(d) / METERS_PER_DEGREE,
        location.lon + distance * math.sin(d) / (METERS_PER_DEGREE * math.cos(math.radians(location.lat))),
        location.alt)


def get_angle_between(direction1, direction2):
    """How far apart two compass directions are, 0 to 180 degrees (350 and 10 are 20 apart)."""
    return abs((direction1 - direction2 + 180) % 360 - 180)


def get_turn_meters(heading, direction):
    """Extra metres the plane flies to turn from heading onto direction (on top of the straight line)."""
    return math.radians(get_angle_between(heading, direction)) * TURN_RADIUS


# ---------- Landing ----------
def land_at(my_vehicle, lat, lon):
    """
    Lands the plane at (lat, lon). It glides there in a straight line from wherever it is
    and touches down near the point, so arrive low and already pointing at it for a short landing.
    Returns straight away; the landing runs in AUTO mode.
    """
    # A one-item mission with just the landing point
    cmds = my_vehicle.commands
    cmds.download()
    cmds.wait_ready()
    cmds.clear()
    cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                     mavutil.mavlink.MAV_CMD_NAV_LAND, 0, 0, 0, 0, 0, 0, lat, lon, 0))
    cmds.upload()
    cmds.next = 1 # Start from the landing point, not from where an older mission stopped
    my_vehicle.mode = VehicleMode("AUTO")


# ---------- Waypoints you clicked on the map ----------
_clicked_waypoints = []


def get_clicked_waypoints():
    """The points you added with right-click -> "Add waypoint", in order, at 30 m altitude."""
    return list(_clicked_waypoints)


# ---------- Landmarks and photos ----------
class Landmark:
    """
    A landmark to photograph.
    loc            where it is, at the altitude to fly at (30 m), so you can send the plane straight there
    approach_from  compass direction from the landmark to the side photos must be taken from
                   (90 = come in from its east side, flying west)
    view_width     how wide that side is, in degrees (60 = up to 30 degrees either side of approach_from)
    inner, outer   photos count between these distances from it, in metres
    price          what a photo of it sells for right now
    public         True if everyone knows about it, False if only you do
    """

    def __init__(self, name, loc, approach_from, view_width=60, inner=30, outer=150, price=100, public=True):
        self.name = name
        self.loc = loc
        self.approach_from = approach_from
        self.view_width = view_width
        self.inner = inner
        self.outer = outer
        self.price = price
        self.public = public

    def __repr__(self):
        return f"Landmark({self.name!r}, price {self.price}, approach from {self.approach_from})"


# Until the game server is running, you practise on landmarks of your own around where you took off.
# Photographing one moves it somewhere new, so there is always something to fly to.
_vehicle = None
_practice = []
_practice_lock = threading.Lock()
_practice_rng = random.Random(1)
_practice_count = 0


def use_vehicle(vehicle):
    """Called by the GCS backend when it connects."""
    global _vehicle
    _vehicle = vehicle


def _new_practice_landmark(center):
    global _practice_count
    _practice_count += 1
    for _ in range(100):
        loc = get_location_from(center, _practice_rng.uniform(400, 900), _practice_rng.uniform(0, 360))
        if all(get_distance_meters(loc, other.loc) > 300 for other in _practice):
            break
    return Landmark(f"Practice {_practice_count}", LocationGlobalRelative(loc.lat, loc.lon, FLYING_ALTITUDE),
                    approach_from=_practice_rng.randrange(0, 360, 5))


def _practice_landmarks():
    with _practice_lock:
        if not _practice and _vehicle is not None and _vehicle.gps_0.fix_type >= 3: # Not before a GPS fix (0, 0)
            home = _vehicle.location.global_relative_frame
            if home is not None and home.lat:
                for _ in range(3):
                    _practice.append(_new_practice_landmark(home))
        return list(_practice)


def get_known_landmarks():
    """The landmarks you can photograph right now, as a list of Landmark."""
    return _practice_landmarks()


def get_other_drones():
    """Everyone else's planes, as a list of (location, heading). Empty while you practise alone."""
    return []


def _photo_problem(position, heading, landmark):
    """Why a photo of landmark from here wouldn't count, or None if it would."""
    distance = get_distance_meters(landmark.loc, position)
    if distance > landmark.outer:
        return f"too far from {landmark.name} ({distance:.0f} m)"
    if distance < landmark.inner:
        return f"too close to {landmark.name} ({distance:.0f} m)"
    if get_angle_between(get_direction_degrees(landmark.loc, position), landmark.approach_from) > landmark.view_width / 2:
        return f"wrong side of {landmark.name}"
    if get_angle_between(get_direction_degrees(position, landmark.loc), heading) > FIELD_OF_VIEW / 2:
        return f"not facing {landmark.name}"
    return None


def take_photo():
    """
    Takes a photo from where the plane is now. Returns True if it sold, False if it didn't count
    (and prints why). The game checks the plane's own position and heading, not what your code thinks.
    """
    if _vehicle is None:
        print("Photo: not connected")
        return False
    position, heading = _vehicle.location.global_relative_frame, _vehicle.heading
    landmarks = _practice_landmarks()
    if not landmarks:
        print("Photo: nothing to photograph")
        return False
    for landmark in landmarks:
        if _photo_problem(position, heading, landmark) is None:
            with _practice_lock:
                _practice[_practice.index(landmark)] = _new_practice_landmark(landmark.loc)
            print(f"Photo: sold {landmark.name} for {landmark.price}")
            return True
    nearest = min(landmarks, key=lambda landmark: get_distance_meters(position, landmark.loc))
    print(f"Photo: {_photo_problem(position, heading, nearest)}")
    return False


# ---------- Buttons ----------
buttons = {} # Button text -> function, in the order they appear in workshop.py


def button(text):
    """
    Put this line above a function in workshop.py to get a button for it in the GCS:

        @button("Simple mission")
        def simple_mission(my_vehicle):
            ...

    One button runs at a time: pressing another one (or Stop) stops the one that is running.
    """
    def add(function):
        buttons[text] = function
        return function
    return add


class Stopped(BaseException):
    """Raised inside a running button's function when you press Stop or another button.
    A BaseException, so an "except Exception" in workshop.py doesn't swallow it."""


_running = None # (text, thread) of the button that is running
_last_error = None # (number, message) of the latest button that crashed, for the GCS to show
_errors = 0


def running_button():
    return _running[0] if _running and _running[1].is_alive() else None


def last_error():
    return _last_error


def stop_button():
    """Stops the running button's function, wherever it is (it finishes its current line first)."""
    global _running
    if not _running or not _running[1].is_alive():
        _running = None
        return
    text, thread = _running
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread.ident), ctypes.py_object(Stopped))
    thread.join(timeout=3)
    if thread.is_alive():
        logging.warning(f"Button '{text}' didn't stop within 3 s")
    _running = None


def run_button(text, vehicle, waypoints=()):
    """Stops whatever is running and starts the function behind the button text in its own thread."""
    global _running, _clicked_waypoints
    stop_button()
    _clicked_waypoints = [LocationGlobalRelative(lat, lon, FLYING_ALTITUDE) for lat, lon in waypoints]
    function = buttons[text]

    def run():
        global _last_error, _errors
        try:
            logging.info(f"Button '{text}' started")
            function(vehicle)
            logging.info(f"Button '{text}' finished")
        except Stopped:
            logging.info(f"Button '{text}' stopped")
        except Exception as e:
            logging.error(f"Button '{text}' crashed: {e!r}", exc_info=True)
            _errors += 1
            _last_error = (_errors, f"{text}: {e!r}")

    thread = threading.Thread(target=run, daemon=True)
    _running = (text, thread)
    thread.start()
