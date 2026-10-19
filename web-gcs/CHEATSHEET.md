# ✈️ Cheat Sheet

Everything you need for `backend/workshop.py`, part by part. Each part lists what's **new** in it; everything from the parts before still applies. In the workshop functions the plane is called `my_vehicle`.

Things that are already written for you live in `backend/game.py`. You can read it, but don't change it.

> Saving `workshop.py` restarts the backend, so click **Connect** again after every edit.

---

## Part 1: Takeoff

**New:** flight modes, arming, the takeoff altitude, where the plane is.

### Flight modes

| Mode | What the plane does |
|---|---|
| `TAKEOFF` | Speeds up, lifts off and climbs straight ahead. **You need this now.** |
| `GUIDED` | Follows your code's commands (part 2) |
| `RTL` | Flies back to where it took off and circles above it (it does *not* land) |
| `AUTO` | Flies a mission. `land_at()` uses it for you |

```python
my_vehicle.mode = VehicleMode("TAKEOFF")   # ask for a mode change
my_vehicle.mode.name                       # current mode, e.g. "TAKEOFF"
```

⚠️ A mode change is a *request*, not instant. Wait until `my_vehicle.mode.name` actually changes before carrying on.

### Arming

Motors must be armed before takeoff.

```python
my_vehicle.is_armable      # True when GPS and sensors are ready
my_vehicle.armed = True    # ask to arm
my_vehicle.armed           # True / False: is it armed right now?
```

⚠️ Just after SITL starts, the plane refuses to arm for about half a minute (the console says `Gyros inconsistent`). Wait a bit and try again.

### Takeoff

```python
my_vehicle.parameters['TKOFF_ALT'] = 30   # climb to 30 m
my_vehicle.mode = VehicleMode("TAKEOFF")
my_vehicle.armed = True                   # once armed, it goes by itself
```

There is no takeoff command: armed in `TAKEOFF` mode, the plane rolls down the runway and climbs **straight ahead**, in the direction it was facing on the ground.

### Where is the plane?

```python
loc = my_vehicle.location.global_relative_frame
loc.lat    # latitude
loc.lon    # longitude
loc.alt    # altitude in metres, above the takeoff point

my_vehicle.groundspeed       # m/s
my_vehicle.heading           # where the nose points, in degrees (0 = north, see part 4)
```

### 🧩 Python: waiting for something to happen

The pattern you'll use most:

```python
while not something_is_true:
    print("Waiting...")
    time.sleep(1)       # ⚠️ always sleep inside the loop!
```

---

## Part 2: Flying to a point

**New:** `GUIDED` mode, `simple_goto`, `get_distance_meters`, what "arrived" means for a plane.
**From earlier:** modes (1), where the plane is (1), waiting loops (1).

### Going somewhere

```python
target = LocationGlobalRelative(39.3595, 22.9302, 30)   # lat, lon, altitude (m)
my_vehicle.simple_goto(target)                           # only works in GUIDED mode
```

⚠️ This returns immediately. The plane flies there on its own, and **your code has to check when it has arrived.** (The GCS's right-click "Go to this point" is exactly this one line, without the checking.)

⚠️ A plane can't stop. It flies past the point 25 m away or more, and then **circles around it, about 50 m away,** until you give it somewhere else to go. So "arrived" means "within about 60 m".

### How far away is it?

```python
get_distance_meters(location1, location2)   # metres between two locations (in game.py)
```

### 🧩 Python: leaving a loop early

```python
while True:
    if close_enough:
        break
    time.sleep(1)
```

---

## Part 3: A mission from your clicks

**New:** `@button`, `get_clicked_waypoints()`, going through a list.
**From earlier:** `fly_to` (2).

### Your own buttons

Put `@button("Some text")` above a function and the GCS shows a button with that text. Pressing it runs the function with the plane as `my_vehicle`:

```python
@button("Simple mission")
def simple_mission(my_vehicle):
    ...
```

- **One button runs at a time.** Pressing another button, or **Stop**, stops the one that's running. So do right-click "Go to this point", "Land here" and "Return to home".
- When a button's function stops, the plane keeps circling wherever it was last sent.
- If your function crashes, the GCS says so; the details are in the backend terminal.

### Waypoints you clicked

Right-click the map → **Add waypoint** (numbered on the map; **Clear waypoints** removes them). In a button's function:

```python
waypoints = get_clicked_waypoints()   # list of LocationGlobalRelative, at 30 m, in click order
```

### 🧩 Python: going through a list

```python
for point in waypoints:
    ...

for i, point in enumerate(waypoints):   # i = 0, 1, 2, ...
    ...
```

### Waiting in place

A plane can't hover. After a `simple_goto` it circles the point, so to wait somewhere, send it there and wait:

```python
time.sleep(10)   # circle for 10 seconds
```

---

## Part 4: Can we take the photo?

**New:** directions, landmarks, `get_direction_degrees`, `get_angle_between`, `FIELD_OF_VIEW`.
**From earlier:** `get_distance_meters` (2), `my_vehicle.heading` (1).

### Directions

A direction is a compass direction in degrees, going clockwise from north. `my_vehicle.heading` uses the same scale for where the nose points.

```
               0  north
               |
 270  west ----+---- east  90
               |
              180  south
```

```python
get_direction_degrees(a, b)          # direction from a to b: b due east of a gives 90
get_angle_between(direction1, direction2)   # how far apart two directions are, 0 to 180
```

💡 Don't subtract directions yourself: 350 and 10 are 20 apart, not 340. That's what `get_angle_between` is for.

### Landmarks

```python
landmark.name            # e.g. "Practice 1"
landmark.loc             # where it is, at 30 m: you can simple_goto it directly
landmark.approach_from   # the side photos must be taken from, as a direction from the landmark
landmark.view_width      # how wide that side is: 60 means up to 30° either side of approach_from
landmark.inner, landmark.outer   # photos count between these distances from it (m)
landmark.price           # what a photo sells for right now
landmark.public          # True if everyone knows about it
```

`approach_from = 90` means: photograph it from its **east** side, so you fly **west** towards it. On the GCS map each landmark has a shaded slice: that's where photos count.

### When does a photo count?

All three at once:

1. **Distance:** between `landmark.inner` and `landmark.outer` from the landmark.
2. **Side:** the direction from the landmark to you is at most `landmark.view_width / 2` from `landmark.approach_from`.
3. **Facing:** the direction from you to the landmark is at most `FIELD_OF_VIEW / 2` (30°) from your heading.

---

## Part 5: Lining up

**New:** `get_location_from`, why a plane needs room to turn, `math.cos` / `math.tan`.
**From earlier:** directions and landmarks (4).

### A point some distance away in some direction

```python
get_location_from(location, distance, direction)   # 300 m east of a landmark: (landmark.loc, 300, 90)
```

### Why line up far out?

A plane turning towards something swings sideways while it turns: about `SWING_METERS` (55 m) for a 90° turn, twice that for a U-turn. If it turns in close to the landmark, it arrives at an angle, on the wrong side or not facing it. So turn in at a point **on the approach line, far enough out** to be straight again before the photo zone, and fly straight in from there.

```python
swing = SWING_METERS * (1 - math.cos(math.radians(turn)))          # sideways swing of a turn of `turn` degrees
distance = swing / math.tan(math.radians(landmark.view_width / 2 - 10)) + 60   # far enough out
```

### 🧩 Python: maths

```python
math.cos(math.radians(60))   # 0.5. Python's cos and tan want radians, so convert degrees first
max(a, b)                    # the bigger one: max(distance, 200) is at least 200
```

---

## Part 6: Photographing landmarks

**New:** `get_known_landmarks()`, `take_photo()`, picking from a list.
**From earlier:** `fly_to` (2), `@button` (3), `can_photograph` (4), `get_approach_point` (5).

```python
landmarks = get_known_landmarks()   # list of Landmark you can photograph now
take_photo()                        # True if it sold; if not, it prints why
```

- The game checks where your plane **really** is and where it **really** points, so check `can_photograph` first and only then `take_photo()`.
- Check often while you fly in: the plane covers 20 m every second, so `time.sleep(0.2)` rather than `time.sleep(1)`.
- After a sale, the landmark disappears from your list.
- Flown past it without a photo? Start over from the approach point. If you're very close to a landmark, fly away first.

### 🧩 Python: the nearest one

```python
here = my_vehicle.location.global_relative_frame
nearest = min(landmarks, key=lambda landmark: get_distance_meters(here, landmark.loc))
```

---

## Part 7: Your strategies

**New:** flying time, other planes.
**From earlier:** everything.

### How long will it take?

```python
get_turn_meters(heading, direction)   # extra metres for turning from heading onto direction
CRUISE_SPEED                          # 20 m/s
```

Flying time for one leg = (turn + straight distance) / `CRUISE_SPEED`. For a route with several points, add up the legs. The plane cuts corners, so the real time is about **0.8×** that.

### Other planes

```python
get_other_drones()   # list of (location, heading) of everyone else's plane
```

What you know about each landmark: where, which side, `price`, `public`. What you know about the others: where they are and where they point. The rest is up to you.

---

## Anytime: landing and coming home

```python
land_at(my_vehicle, lat, lon)   # glides to (lat, lon) and lands there (in game.py)
```

It flies in a straight line from wherever the plane is and comes down on the way, so the landing is short if you arrive **low and already pointing at the landing spot**. It touches down within about 100 m of the point and rolls a bit.

---

## 🧩 More Python

**Giving up with an error:**

```python
raise Exception("Vehicle is not armed")
```

**Measuring time:**

```python
start = time.time()
...
elapsed = time.time() - start   # seconds since start
```

---

## 🐞 Common mistakes

- **Nothing happens on takeoff.** Is the mode `TAKEOFF`? Is the plane actually armed? (Check `my_vehicle.armed`, don't assume.) Right after starting SITL it refuses to arm for about half a minute.
- **The GCS freezes.** You have a `while` loop with no `time.sleep()` in it, or one that never ends.
- **The plane flies off somewhere strange.** Latitude and longitude are swapped. In Volos, latitude ≈ **39.36** and longitude ≈ **22.94**.
- **It never "arrives", it just circles.** A plane never passes exactly over the point. Check the distance against a threshold of about `60` metres, not `< 3` and not `== 0`. Anything under 50 m can leave it circling forever.
- **It circles somewhere and won't come back.** That's what a plane does when it has nowhere else to go (RTL too). Send it a new point, or land it with `land_at()`.
- **It worked, then stopped after I saved.** The backend restarted. Click **Connect** again.
- **My button doesn't show up.** Did you save and click **Connect** again? Is `@button("...")` right above the `def`?
- **The photo never counts.** Print what `can_photograph` checks, one condition at a time. Most often the plane is on the wrong side or turned in too late.
