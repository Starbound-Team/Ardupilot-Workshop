#Everything in this file is already written for you: use it from workshop.py, but don't change it.
#The cheat sheet says which part of the workshop needs what.
import collections
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping # Fix for newer Python versions with dronekit
import ctypes
import inspect
import json
import logging
import math
import random
import threading
import time
import urllib.request

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
PHOTO_COOLDOWN = 3 # s the camera needs after a photo that didn't count
GAME_AREA = (39.355, 22.922, 39.378, 22.968) # South, west, north, east: landmarks only appear over Volos


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
    head_start     seconds until everyone else knows about it too (0 once it's public)
    age            seconds since it appeared
    sales          how many photos of it have been sold so far, by anyone
    """

    def __init__(self, name, loc, approach_from, view_width=60, inner=30, outer=150, price=100, public=True,
                 head_start=0, age=0, sales=0):
        self.name = name
        self.loc = loc
        self.approach_from = approach_from
        self.view_width = view_width
        self.inner = inner
        self.outer = outer
        self.price = price
        self.public = public
        self.head_start = head_start
        self.age = age
        self.sales = sales

    def __repr__(self):
        return f"Landmark({self.name!r}, price {self.price}, approach from {self.approach_from})"


# Outside a round you practise on landmarks of your own around where you took off.
# Photographing one moves it somewhere new, so there is always something to fly to.
_vehicle = None
_mover = None # Puts the plane down at a start position (lat, lon, heading), if it can be moved; see app.py
_practice = []
_practice_lock = threading.Lock()
_practice_rng = random.Random(1)
_practice_count = 0


def use_vehicle(vehicle, mover=None):
    """Called by the GCS backend when it connects. mover moves the plane to a start position, if it can."""
    global _vehicle, _mover
    _vehicle, _mover = vehicle, mover


# ---------- The game server ----------
# With GAME_SERVER_URL set, the GCS backend sends the plane's telemetry to the organisers' server twice a
# second and keeps its answer here. From a round's countdown until the organisers reset it, landmarks,
# photos and money come from the server; the rest of the time you practise on your own landmarks.
_server_url = None
_player_id = None
_server_state = None # The server's latest answer: round, landmarks, score, other planes
_server_state_time = 0
_flown_to_start = None # The start position the plane was already sent to in this countdown
_moved_to = None # The start position the plane was already put down at in this countdown
# The server sends landmarks as a numbered list of changes; this is our copy, put together from them
_landmarks = {} # Name -> the server's record of it (where, photo zone, value, when it went public, sales)
_landmarks_have = None # {"round": n, "upto": n}: which changes we have, sent back with every request
_sold_by_me = set() # Names we've sold in this round, so we can't sell them again
_clock_offset = 0 # The server's clock minus ours, for working out prices
_landmarks_lock = threading.Lock()


def use_server(url, player_id):
    """Called by the GCS backend when GAME_SERVER_URL is set."""
    global _server_url, _player_id
    _server_url, _player_id = url, player_id


def landmarks_have():
    """Which landmark changes we have, for the GCS backend to send with every request."""
    return _landmarks_have


def _merge_landmarks(info):
    """Applies the server's landmark changes, or replaces everything with a full list."""
    global _landmarks_have
    with _landmarks_lock:
        have = _landmarks_have
        if info.get("full"):
            if have and have["round"] == info["round"] and have["upto"] > info["upto"]:
                return # An older answer than what we have, arriving late
            _landmarks.clear()
            _landmarks.update({lm["name"]: lm for lm in info["landmarks"]})
            _sold_by_me.clear()
            _sold_by_me.update(info["sold_by_me"])
        elif have and have["round"] == info["round"]:
            for change in info["changes"]:
                if change["n"] <= have["upto"]:
                    continue # Already applied
                if "landmark" in change:
                    _landmarks[change["landmark"]["name"]] = change["landmark"]
                if "sold_by_me" in change:
                    _sold_by_me.add(change["sold_by_me"])
            if info["upto"] < have["upto"]:
                return
        else:
            return # Changes to something we don't have: the next request asks for a full list
        _landmarks_have = {"round": info["round"], "upto": info["upto"]}


def _price(lm, pricing, now):
    """What a photo of lm sells for at time now (the server's clock). The same formula as the server's."""
    value = lm["value"]
    if lm["public_since"] is not None:
        grew_until = min(t for t in (now, pricing["until"], lm["first_sale"]) if t is not None)
        value += pricing["growth_step"] * max(0, int((grew_until - lm["public_since"]) // pricing["growth_seconds"]))
    floor = pricing["price_floor"]
    return round(floor + max(0, value - floor) * pricing["sale_keep"] ** lm["sales"])


def set_server_state(state):
    """Called by the GCS backend with every answer from the server."""
    global _server_state, _server_state_time, _flown_to_start, _moved_to, _clock_offset
    if state and "landmarks" in state:
        _merge_landmarks(state["landmarks"])
    if state and "now" in state:
        _clock_offset = state["now"] - time.time()
    _server_state, _server_state_time = state, time.time()
    if state and state.get("round", {}).get("state") == "countdown" and state.get("start_position"):
        start = tuple(state["start_position"])
        if _mover is not None and _moved_to != start:
            _move_to_start(start, state.get("area") or GAME_AREA)
        else:
            _fly_to_start(start)
    else:
        _flown_to_start = _moved_to = None


def _move_to_start(start, area):
    """
    Before a round, a plane the GCS can move is put down at its start position, facing the middle of the area,
    on the ground: it reboots there and the GCS reconnects. Takeoff is up to you.
    """
    global _moved_to
    _moved_to = start
    south, west, north, east = area
    middle = LocationGlobalRelative((south + north) / 2, (west + east) / 2, 0)
    heading = get_direction_degrees(LocationGlobalRelative(start[0], start[1], 0), middle)
    logging.info("Round starting: moving the plane to its start position")
    threading.Thread(target=_mover, args=(start[0], start[1], heading), daemon=True).start()


def _server():
    """The server's latest answer, or None without a server or when it hasn't answered for a while."""
    if _server_state is None or time.time() - _server_state_time > 5:
        return None
    return _server_state


def _in_round():
    state = _server()
    return state is not None and state.get("round", {}).get("state") in ("countdown", "running", "over")


def _fly_to_start(start):
    """Before a round, the GCS sends the plane to its start position itself, taking over from any button.
    For a plane it moved there, this just keeps it circling there once it has taken off."""
    global _flown_to_start
    if _vehicle is None or _flown_to_start == start:
        return
    location = _vehicle.location.global_relative_frame
    if not _vehicle.armed or location.alt is None or location.alt < 10:
        return # Still on the ground: it goes as soon as it has taken off
    _flown_to_start = start
    take_control()
    target = LocationGlobalRelative(start[0], start[1], FLYING_ALTITUDE)
    _vehicle.mode = VehicleMode("GUIDED")
    _vehicle.simple_goto(target)
    set_target(target)
    logging.info("Round starting: flying to the start position")


def round_info():
    """The round for the GCS to show, or None while practising."""
    return _server()["round"] if _in_round() else None


def other_drones_for_map():
    """Everyone else's planes for the GCS map: name, lat, lon, heading."""
    state = _server()
    return state.get("others", []) if state else []


def game_area():
    """(south, west, north, east): the server's area if there is one (it shrinks during a round), or GAME_AREA."""
    state = _server()
    return tuple(state["area"]) if state and state.get("area") else GAME_AREA


def _in_game_area(loc):
    south, west, north, east = game_area()
    return south <= loc.lat <= north and west <= loc.lon <= east


def _new_practice_landmark(center):
    """400-900 m from center, inside GAME_AREA and 300 m from the others; anywhere in the area if that's
    impossible (center near its edge, or the plane started somewhere else entirely)."""
    global _practice_count
    _practice_count += 1
    south, west, north, east = game_area()
    for attempt in range(200):
        if attempt < 100:
            loc = get_location_from(center, _practice_rng.uniform(400, 900), _practice_rng.uniform(0, 360))
        else:
            loc = LocationGlobalRelative(_practice_rng.uniform(south, north), _practice_rng.uniform(west, east), 0)
        if _in_game_area(loc) and all(get_distance_meters(loc, other.loc) > 300 for other in _practice):
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
    if _in_round():
        state = _server()
        pricing = state.get("pricing")
        if not pricing: # Countdown: nothing to photograph yet
            return []
        now = time.time() + _clock_offset
        with _landmarks_lock:
            records = [lm for name, lm in _landmarks.items() if name not in _sold_by_me]
        return [Landmark(l["name"], LocationGlobalRelative(l["lat"], l["lon"], FLYING_ALTITUDE), l["approach_from"],
                         l["view_width"], l["inner"], l["outer"], _price(l, pricing, now), l["public_since"] is not None,
                         head_start=max(0, round(l["head_start_until"] - now, 1)) if l["head_start_until"] else 0,
                         age=round(now - l["born"], 1), sales=l["sales"])
                for l in records]
    return _practice_landmarks()


def get_other_drones():
    """Everyone else's planes, as a list of (location, heading). Empty without a game server."""
    return [(LocationGlobalRelative(o["lat"], o["lon"], FLYING_ALTITUDE), o["heading"]) for o in other_drones_for_map()]


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


_camera_ready_at = 0 # time.time() when the camera can take the next photo
_money = 0
_photos_sold = 0
_last_sale = None # "Practice 1 +100"
_photo_log = [] # (number, sold, text) of recent photos, newest last, for the GCS to show as toasts


def _log_photo(sold, text):
    number = _photo_log[-1][0] + 1 if _photo_log else 1
    _photo_log.append((number, sold, text))
    del _photo_log[:-10]


def photo_log():
    return list(_photo_log)


def score():
    """Your score so far, for the GCS. In a round the server's, with your rank, the leader and who's ahead."""
    if _in_round():
        return _server().get("score")
    return {"money": _money, "photos": _photos_sold, "last_sale": _last_sale}


def camera_ready():
    return time.time() >= _camera_ready_at


def take_photo():
    """
    Takes a photo from where the plane is now. Returns True if it sold, False if it didn't count
    (and prints why). The game checks the plane's own position and heading, not what your code thinks.
    A photo that doesn't count costs you: the camera needs PHOTO_COOLDOWN seconds before the next one.
    """
    global _camera_ready_at, _money, _photos_sold, _last_sale
    if _vehicle is None:
        print("Photo: not connected")
        return False
    if not camera_ready():
        print(f"Photo: camera not ready for another {_camera_ready_at - time.time():.1f} s")
        return False
    position, heading = _vehicle.location.global_relative_frame, _vehicle.heading
    if _in_round():
        return _take_photo_on_server(position, heading)
    landmarks = _practice_landmarks()
    for landmark in landmarks:
        if _photo_problem(position, heading, landmark) is None:
            with _practice_lock:
                _practice[_practice.index(landmark)] = _new_practice_landmark(landmark.loc)
            print(f"Photo: sold {landmark.name} for {landmark.price}")
            _money += landmark.price
            _photos_sold += 1
            _last_sale = f"{landmark.name} +{landmark.price}"
            _log_photo(True, f"Sold {landmark.name} for {landmark.price}")
            return True
    _camera_ready_at = time.time() + PHOTO_COOLDOWN
    if not landmarks:
        print("Photo: nothing to photograph")
        _log_photo(False, "Photo: nothing to photograph")
        return False
    nearest = min(landmarks, key=lambda landmark: get_distance_meters(position, landmark.loc))
    print(f"Photo: {_photo_problem(position, heading, nearest)}, camera ready again in {PHOTO_COOLDOWN} s")
    _log_photo(False, f"Photo didn't count: {_photo_problem(position, heading, nearest)}")
    return False


def _take_photo_on_server(position, heading):
    """In a round the server judges the photo, from where the plane is now as the GCS sees it."""
    global _camera_ready_at
    if _server()["round"]["state"] != "running":
        print("Photo: no round running")
        return False
    body = json.dumps({"id": _player_id, "lat": position.lat, "lon": position.lon, "heading": heading,
                       "have": _landmarks_have}).encode()
    request = urllib.request.Request(_server_url + "/api/photo", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            answer = json.load(response)
    except Exception as e:
        print(f"Photo: couldn't reach the game server ({e})")
        return False
    sold, text = answer["sold"], answer["text"]
    print(f"Photo: {text}")
    if answer.get("game"):
        set_server_state(answer["game"]) # A sold landmark leaves get_known_landmarks() straight away
    if sold:
        _log_photo(True, text)
    elif text.startswith(("Photo didn't count", "Nothing to photograph")): # The server's camera needs a rest too
        _camera_ready_at = time.time() + PHOTO_COOLDOWN
        _log_photo(False, text)
    return sold


# ---------- Buttons ----------
buttons = {} # Button text -> function, in the order they appear in workshop.py


def button(text):
    """
    Put this line above a function in workshop.py to get a button for it in the GCS:

        @button("Simple mission")
        def simple_mission(my_vehicle):
            ...

    A function that also takes a location goes in the map's right-click menu instead,
    and gets the point you clicked:

        @button("Fly here")
        def fly_here(my_vehicle, location):
            ...

    Several buttons can run at once, but only one flies the plane: a button that moves the plane
    takes over from the one that was flying it. Click a running button again to stop it.
    """
    def add(function):
        buttons[text] = function
        return function
    return add


def takes_location(function):
    """True for a button function that goes in the right-click menu: (my_vehicle, location)."""
    return len(inspect.signature(function).parameters) >= 2


class Stopped(BaseException):
    """Raised inside a running button's function when it is stopped or another button takes over the plane.
    A BaseException, so an "except Exception" in workshop.py doesn't swallow it."""


_running = {} # Button text -> thread, for the buttons that are running
_flying = None # Thread that last moved the plane: a button's, or the GCS's for manual commands
_control_lock = threading.Lock()
_last_error = None # (number, message) of the latest button that crashed, for the GCS to show
_errors = 0
_target = None # Where the last simple_goto sent the plane, for the map; None after anything else moves it


def running_buttons():
    return [text for text, thread in list(_running.items()) if thread.is_alive()]


def last_error():
    return _last_error


def _raise_stopped(thread):
    """Makes Stopped happen inside thread, wherever it is (it finishes its current line first)."""
    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread.ident), ctypes.py_object(Stopped))


def stop_button(text):
    thread = _running.pop(text, None)
    if thread and thread.is_alive():
        _raise_stopped(thread)
        thread.join(timeout=3)
        if thread.is_alive():
            logging.warning(f"Button '{text}' didn't stop within 3 s")


def stop_all():
    for text in list(_running):
        stop_button(text)


def set_target(location):
    global _target
    _target = location


def current_target(vehicle):
    """(lat, lon) the plane is flying to, or None. Only GUIDED mode flies to a simple_goto target."""
    if _target is None or vehicle is None or vehicle.mode.name != "GUIDED":
        return None
    return (_target.lat, _target.lon)


def take_control():
    """
    Called whenever something moves the plane: whichever button was flying it before is stopped.
    Only button threads are ever stopped. When the GCS itself moves the plane (manual commands, flying
    to the start position) the button is stopped, but the GCS's own threads never are.
    """
    global _flying, _target
    me = threading.current_thread()
    _target = None # A simple_goto sets it again right after
    with _control_lock:
        previous = _flying
        _flying = me if me in _running.values() else None
    if previous is not None and previous is not me and previous.is_alive():
        _raise_stopped(previous)


class _Watched:
    """
    Stands in for my_vehicle in button functions. Everything passes straight through to the real object,
    but anything that moves the plane calls take_control() first. These are all the DroneKit calls that can
    command the plane; everything else (location, heading, parameters...) only reads.
    """

    def __init__(self, target, moves=(), settings=(), children=None):
        object.__setattr__(self, '_target', target)
        object.__setattr__(self, '_moves', set(moves))
        object.__setattr__(self, '_settings', set(settings))
        object.__setattr__(self, '_children', children or {})

    def __getattr__(self, name):
        value = getattr(self._target, name)
        if name in self._moves:
            def moving(*args, **kwargs):
                take_control()
                result = value(*args, **kwargs)
                if name == 'simple_goto' and args:
                    set_target(args[0])
                return result
            return moving
        if name in self._children:
            return _Watched(value, **self._children[name])
        return value

    def __setattr__(self, name, value):
        if name in self._settings:
            take_control()
        setattr(self._target, name, value)


def _watched_vehicle(vehicle):
    return _Watched(vehicle,
                    moves={'simple_goto', 'simple_takeoff', 'wait_simple_takeoff', 'arm', 'disarm',
                           'wait_for_mode', 'send_mavlink', 'reboot'},
                    settings={'mode', 'armed', 'groundspeed', 'airspeed'},
                    children={'commands': {'moves': {'upload'}, 'settings': {'next'}},
                              'channels': {'settings': {'overrides'}}})


def run_button(text, vehicle, waypoints=(), location=None):
    """
    Starts the function behind the button text in its own thread, or stops it if it is already running.
    Returns True if it started.
    """
    global _clicked_waypoints
    if text in running_buttons():
        stop_button(text)
        return False
    _clicked_waypoints = [LocationGlobalRelative(lat, lon, FLYING_ALTITUDE) for lat, lon in waypoints]
    function = buttons[text]
    args = [_watched_vehicle(vehicle)]
    if takes_location(function):
        args.append(LocationGlobalRelative(location[0], location[1], FLYING_ALTITUDE))

    def run():
        global _last_error, _errors
        try:
            logging.info(f"Button '{text}' started")
            function(*args)
            logging.info(f"Button '{text}' finished")
        except Stopped:
            logging.info(f"Button '{text}' stopped")
        except Exception as e:
            logging.error(f"Button '{text}' crashed: {e!r}", exc_info=True)
            _errors += 1
            _last_error = (_errors, f"{text}: {e!r}")

    thread = threading.Thread(target=run, daemon=True)
    _running[text] = thread
    thread.start()
    return True
