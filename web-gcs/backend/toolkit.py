#Everything you get ready-made for workshop.py, in one place. Read it, use it, but don't change it.
#The cheat sheet says which part of the workshop needs what; the part is noted next to each one here too.
#
#  1. Numbers about the plane, the camera and the game
#  2. Directions and distances: maths that works anywhere, also for a real drone
#  3. Landmarks, lining up and photos
#  4. Other planes, the round and your score
#  5. Buttons and the waypoints you click
#  6. Landing
#
#Landmarks, photos, other planes and buttons only exist in this workshop's GCS: those functions hand over
#to game.py, where the GCS does the work (talking to the game server, running your buttons). You never need to read it.
import collections
import collections.abc
collections.MutableMapping = collections.abc.MutableMapping # Fix for newer Python versions with dronekit
import math
import time

from dronekit import VehicleMode, LocationGlobalRelative, Command
from pymavlink import mavutil

__all__ = ['CRUISE_SPEED', 'TURN_RADIUS', 'SWING_METERS', 'FIELD_OF_VIEW', 'FLYING_ALTITUDE', 'PHOTO_COOLDOWN', 'GAME_AREA',
           'get_distance_meters', 'get_direction_degrees', 'get_location_from', 'get_angle_between', 'get_turn_meters',
           'Landmark', 'is_lined_up', 'get_approach_points', 'approach', 'get_eta', 'get_known_landmarks', 'take_photo',
           'get_other_drones', 'OtherPlane', 'get_seconds_left', 'get_score', 'button', 'get_clicked_waypoints', 'land_at'] # What workshop.py gets from "from toolkit import *"


#---------- 1. Numbers ----------

CRUISE_SPEED = 20 # m/s, how fast the plane flies in GUIDED mode (part 7)
TURN_RADIUS = 35 # m, roughly how tightly the plane turns (used by get_turn_meters)
SWING_METERS = 55 # m, how far a turn swings the plane sideways: a U-turn swings it 2 * 55 m (part 5)
FIELD_OF_VIEW = 60 # degrees, the camera sees 30 degrees either side of the nose (part 4)
FLYING_ALTITUDE = 30 # m, landmarks and clicked waypoints are at this altitude
PHOTO_COOLDOWN = 3 # s the camera needs after a photo that didn't count (part 6)
GAME_AREA = (39.355, 22.922, 39.378, 22.968) # South, west, north, east: landmarks only appear over Volos

METERS_PER_DEGREE = 111319.5 # One degree of latitude, in metres (used by the maths below)


#---------- 2. Directions and distances ----------
#A direction is a compass direction in degrees, clockwise from north: 0 north, 90 east, 180 south, 270 west.
#my_vehicle.heading (where the nose points) uses the same scale.

def get_distance_meters(location1, location2):
    """
    Metres between two locations (part 2).
        get_distance_meters(my_vehicle.location.global_relative_frame, landmark.loc)   # how far to the landmark
    """
    if location1 is None or location2 is None or None in (location1.lat, location1.lon, location2.lat, location2.lon):
        return float('inf') # No position yet (no GPS fix): infinitely far
    # Flat-earth approximation, fine for a few km: a degree of longitude shrinks with cos(latitude)
    north = (location2.lat - location1.lat) * METERS_PER_DEGREE
    east = (location2.lon - location1.lon) * METERS_PER_DEGREE * math.cos(math.radians(location1.lat))
    return math.hypot(north, east)


def get_direction_degrees(location1, location2):
    """
    Compass direction from location1 to location2, 0 to 360 (part 4).
        get_direction_degrees(here, landmark.loc)   # which way to point the plane to face the landmark
        get_direction_degrees(landmark.loc, here)   # which side of the landmark we are on
    """
    north = (location2.lat - location1.lat) * METERS_PER_DEGREE
    east = (location2.lon - location1.lon) * METERS_PER_DEGREE * math.cos(math.radians(location1.lat))
    return math.degrees(math.atan2(east, north)) % 360


def get_angle_between(direction1, direction2):
    """
    How far apart two directions are, 0 to 180 degrees (part 4). Don't subtract directions yourself:
    350 and 10 are 20 apart, not 340.
        get_angle_between(my_vehicle.heading, get_direction_degrees(here, landmark.loc))   # 0 = facing it
    """
    return abs((direction1 - direction2 + 180) % 360 - 180)


def get_location_from(location, distance, direction):
    """
    The location distance metres away from location, in the compass direction direction (part 5).
        get_location_from(landmark.loc, 300, 90)   # 300 m east of the landmark
    """
    d = math.radians(direction)
    return LocationGlobalRelative(
        location.lat + distance * math.cos(d) / METERS_PER_DEGREE,
        location.lon + distance * math.sin(d) / (METERS_PER_DEGREE * math.cos(math.radians(location.lat))),
        location.alt)


def get_turn_meters(heading, direction):
    """
    Extra metres the plane flies to turn from heading onto direction, on top of the straight line (part 7).
    Flying time for one leg = (get_turn_meters(...) + distance) / CRUISE_SPEED; the real time is about 0.8 of that.
    """
    return math.radians(get_angle_between(heading, direction)) * TURN_RADIUS


#---------- 3. Landmarks, lining up and photos ----------

class Landmark:
    """
    A landmark to photograph (part 4). What get_known_landmarks() gives you a list of.
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


def is_lined_up(landmark, position, heading):
    """
    True if the plane can fly straight in for a photo from here (part 5): on the landmark's photo side
    (with 10 degrees to spare), outside the photo zone or just inside it, and already pointing about at it.
    """
    distance = get_distance_meters(landmark.loc, position)
    side = get_angle_between(get_direction_degrees(landmark.loc, position), landmark.approach_from)
    nose = get_angle_between(get_direction_degrees(position, landmark.loc), heading)
    return distance > landmark.inner + 40 and side <= landmark.view_width / 2 - 10 and nose <= 20


def get_approach_points(landmark, position, heading, turning_circle=False):
    """
    Where to fly before going straight at a landmark, so that the plane arrives lined up (part 5):
    a list of 0, 1 or 2 locations. After the last one, fly straight at landmark.loc.
      - Already lined up: no points, straight in.
      - Otherwise one point on the approach line (the line out from the landmark in the direction
        approach_from), further out the more the plane has to turn there: turning swings it sideways,
        and it must be straight again before the photo zone. Too close to turn round for it? Further out still.
      - turning_circle=True: when the plane has to turn round (145 degrees or more) and is at least 400 m away,
        two points on a turning circle the size of the plane's own turn, touching the approach line, like a
        pilot's procedure turn: join the circle at point 1, follow it round to point 2 on the line, fly straight in.
        Measured in SITL: about 6 s quicker from 135 degrees and 9 s from straight behind, but from straight
        behind it missed the photo 1 time in 4 (the one point never did). Your call.
    """
    if is_lined_up(landmark, position, heading):
        return []
    guess = get_location_from(landmark.loc, 300, landmark.approach_from)
    turn = get_angle_between(get_direction_degrees(position, guess), get_direction_degrees(guess, landmark.loc))
    if turning_circle and turn >= 145 and get_distance_meters(position, landmark.loc) >= 400:
        points = _turning_circle(landmark, position, heading) # Only from far out: close in it missed more
        if points:
            return points
    return [_lead_in_point(landmark, position, heading, turn)]


def _room_needed(turn):
    """Straight metres a plane needs to finish turning by turn degrees towards a point before reaching it."""
    return 60 + 2 * SWING_METERS * (1 - math.cos(math.radians(turn)))


def _lead_in_point(landmark, position, heading, turn):
    """One point on the approach line: far enough out to straighten up after turning in, and to turn round for."""
    swing = SWING_METERS * (1 - math.cos(math.radians(turn)))
    distance = max(landmark.outer + 50, swing / math.tan(math.radians(landmark.view_width / 2 - 10)) + 60)
    while distance < landmark.outer + 400:
        point = get_location_from(landmark.loc, distance, landmark.approach_from)
        first_turn = get_angle_between(heading, get_direction_degrees(position, point))
        if get_distance_meters(position, point) >= _room_needed(first_turn):
            break
        distance += 50
    return get_location_from(landmark.loc, distance, landmark.approach_from)


def _turning_circle(landmark, position, heading):
    """Points 1 and 2 on the shortest turning circle with room to join it, or None if there is none."""
    r = SWING_METERS # The circle's radius: the plane's own turn
    # Flat x/y in metres (x east, y north) around the landmark makes the circle maths simpler
    px, py = _xy(landmark.loc, position)
    ux, uy = math.sin(math.radians(landmark.approach_from)), math.cos(math.radians(landmark.approach_from))
    best = None
    for out in (landmark.outer + 50, landmark.outer + 150, landmark.outer + 250):
        p2 = (ux * out, uy * out)
        for side in (1, -1): # The circle on one side of the approach line, then the other
            cx, cy = p2[0] + uy * side * r, p2[1] - ux * side * r
            # Which way round the circle: the plane must leave it at point 2 heading in, towards the landmark
            sense = 1 if (p2[0] - cx) * -uy - (p2[1] - cy) * -ux > 0 else -1 # 1 = anticlockwise
            to_plane = math.hypot(px - cx, py - cy)
            if to_plane <= r * 1.05:
                continue # The plane is on this circle already: it can't join it with a straight line
            spread = math.acos(r / to_plane)
            for s in (1, -1): # The two points where a straight line from the plane touches the circle
                angle = math.atan2(py - cy, px - cx) + s * spread
                tx, ty = cx + r * math.cos(angle), cy + r * math.sin(angle)
                # That straight line must run the same way the plane goes round the circle
                if (tx - px) * -(ty - cy) * sense + (ty - py) * (tx - cx) * sense <= 0:
                    continue
                arc = ((math.atan2(p2[1] - cy, p2[0] - cx) - angle) * sense) % (2 * math.pi)
                if math.degrees(arc) > 200:
                    continue # Nearly a full loop: the plane loses its way on those
                leg = math.hypot(tx - px, ty - py)
                first_turn = get_angle_between(heading, math.degrees(math.atan2(tx - px, ty - py)) % 360)
                if leg < _room_needed(first_turn):
                    continue # It would overshoot point 1
                length = math.radians(first_turn) * r + leg + arc * r + out
                if best is None or length < best[0]:
                    best = (length, (tx, ty), p2)
    if best is None:
        return None
    _, point1, point2 = best
    return [_location(landmark.loc, *point1), _location(landmark.loc, *point2)]


def approach(my_vehicle, landmark, turning_circle=False):
    """
    Lines the plane up for a photo of landmark (part 5): flies through get_approach_points, then returns.
    Point the plane at landmark.loc straight after it (my_vehicle.simple_goto(landmark.loc)) and watch for the photo.
    Returns straight away if the plane is already lined up. turning_circle: see get_approach_points.
    """
    position, heading = my_vehicle.location.global_relative_frame, my_vehicle.heading
    points = get_approach_points(landmark, position, heading, turning_circle)
    for point in points:
        # One point: turning in 60 m early, as fly_to does, cuts the corner and saves time.
        # Two (the turning circle): they are close together, so each one has to be reached or passed first.
        _fly_until_reached(my_vehicle, point, 60 if len(points) == 1 else 30)


def _fly_until_reached(my_vehicle, point, close_enough):
    """Flies to point until it is within close_enough metres, or passed (it was getting closer, now it isn't). At most 2 minutes."""
    my_vehicle.simple_goto(point)
    closest = float('inf')
    start = time.time()
    while time.time() - start < 120:
        distance = get_distance_meters(my_vehicle.location.global_relative_frame, point)
        if distance < close_enough or (closest < 100 and distance > closest + 15):
            return
        closest = min(closest, distance)
        time.sleep(0.2)


def _xy(origin, location):
    """location as x (east) and y (north) metres from origin."""
    return ((location.lon - origin.lon) * METERS_PER_DEGREE * math.cos(math.radians(origin.lat)),
            (location.lat - origin.lat) * METERS_PER_DEGREE)


def _location(origin, x, y):
    """The location x metres east and y metres north of origin, at its altitude."""
    return LocationGlobalRelative(origin.lat + y / METERS_PER_DEGREE,
                                  origin.lon + x / (METERS_PER_DEGREE * math.cos(math.radians(origin.lat))), origin.alt)


def get_eta(position, heading, landmark, turning_circle=False):
    """
    Seconds until a plane at position, pointing heading, could take its photo of landmark, if it flies
    approach()'s route (part 7). The same for any plane, so you can compare yourself with the others:
        get_eta(my_vehicle.location.global_relative_frame, my_vehicle.heading, landmark)   # you
        get_eta(plane.loc, plane.heading, landmark)                                        # someone else
    Measured in SITL: usually within 3 s. From close in and badly placed (lots of turning near the
    landmark) the real time can be 10-15 s longer. Others may not fly the best route, so it's what a
    good pilot would need, not a promise.
    """
    metres, here, direction_now = 0.0, position, heading
    for target in get_approach_points(landmark, position, heading, turning_circle) + [landmark.loc]:
        distance = get_distance_meters(here, target)
        direction = get_direction_degrees(here, target)
        if target is landmark.loc:
            distance = max(0, distance - landmark.outer) # The photo can be taken once inside the photo zone
        metres += get_turn_meters(direction_now, direction) + distance
        here, direction_now = target, direction
    # Fitted to 34 SITL approaches: the plane cuts corners, so it's quicker than the metres say
    return 0.81 * metres / CRUISE_SPEED + 1.4


def get_known_landmarks():
    """
    The landmarks you can photograph right now, as a list of Landmark (part 6). Outside a round you practise on
    landmarks of your own around where you took off; one you photograph moves somewhere new.
    After you sell a photo of a landmark, it's no longer in your list.
    """
    return game.get_known_landmarks()


def take_photo():
    """
    Takes a photo from where the plane is now (part 6). Returns True if it sold, False if it didn't count
    (and prints why). The game checks the plane's own position and heading, not what your code thinks,
    so check can_photograph first. A photo that doesn't count costs you: the camera needs PHOTO_COOLDOWN
    seconds before the next one.
    """
    return game.take_photo()


#---------- 4. Other planes, the round and your score ----------

class OtherPlane:
    """
    Someone else's plane, as get_other_drones() gives it (part 7).
    name      their PILOT_NAME
    loc       where it is (at 30 m)
    heading   where its nose points, in degrees
    """

    def __init__(self, name, loc, heading):
        self.name = name
        self.loc = loc
        self.heading = heading

    def __repr__(self):
        return f"OtherPlane({self.name!r}, heading {self.heading})"


def get_other_drones():
    """
    Everyone else's planes, as a list of OtherPlane (part 7). Empty without a game server.
        for plane in get_other_drones():
            print(plane.name, get_eta(plane.loc, plane.heading, landmark))
    """
    return [OtherPlane(o.get("name", ""), LocationGlobalRelative(o["lat"], o["lon"], FLYING_ALTITUDE), o.get("heading") or 0)
            for o in game.other_drones_for_map()]


def get_seconds_left():
    """Seconds left in the round that is running (part 7), or None outside one (practising, countdown, over)."""
    info = game.round_info()
    return info.get("seconds_left") if info and info.get("state") == "running" else None


def get_score():
    """
    Your score (part 7), as a dictionary. Always "money"; in a round also "rank" (1 = first),
    "players", "leader" ({"name": ..., "money": ...}) and "ahead" (the one just ahead of you, same form).
    """
    return dict(game.score() or {})


#---------- 5. Buttons and the waypoints you click ----------

def button(text):
    """
    Put this line above a function in workshop.py to get a button for it in the GCS (part 3):

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
    return game.button(text)


def get_clicked_waypoints():
    """The points you added with right-click -> "Add waypoint", in order, at 30 m altitude (part 3)."""
    return game.get_clicked_waypoints()


#---------- 6. Landing ----------

def land_at(my_vehicle, lat, lon):
    """
    Lands the plane at (lat, lon) (any time). It glides there in a straight line from wherever it is
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


# The GCS's side of landmarks, photos and buttons. Imported last because game.py uses the maths above.
import game # noqa: E402
