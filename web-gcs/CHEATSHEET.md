# ✈️ Cheat Sheet

Everything you need for `backend/workshop.py`, part by part. Each part lists what's **new** in it; everything from the parts before still applies. In the workshop functions the plane is called `my_vehicle`.

Everything that's already written for you is in `backend/toolkit.py`, grouped by topic, with the part that needs it next to each one. You can read it, but don't change it.

> Saving `workshop.py` restarts the backend, and the GCS reconnects by itself. A mistake in the file shows up as a message with its line number: fix it and save.

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
get_distance_meters(location1, location2)   # metres between two locations (in toolkit.py)
```

### 🧩 Python: leaving a loop early

```python
while True:
    if close_enough:
        break
    time.sleep(1)
```

### Trying it out

Right-click the map → **Fly here** runs your `fly_to` on the point you clicked. It shows **● Fly here** in the right-click menu until the plane arrives (click it again to stop it early).

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

If the function also takes a `location`, the button goes in the **right-click menu** instead and gets the point you clicked (that's how **Fly here** works):

```python
@button("Fly here")
def fly_here(my_vehicle, location):
    ...
```

- A running button is green with a white dot. **Click it again to stop it.**
- **A button that flies the plane takes over from the one that was flying it.** Buttons that don't move the plane (like **Take photo**) run alongside. Right-click "Go to this point", "Land here" and "Return to home" take over too.
- When a button's function stops, the plane keeps circling wherever it was last sent.
- If your function crashes, the GCS says so; the details are in the backend terminal.
- Too many buttons for the top bar? The rest are under **More ▾**, in the order they are in `workshop.py`.

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

Like a real inspection job, each landmark comes with a brief: *photograph its east side from 30 to 150 m away.* The camera is fixed to the plane and looks straight ahead, so to aim the camera you aim the whole plane.

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
landmark.head_start      # seconds until everyone else knows about it too (0 once it's public)
landmark.age             # seconds since it appeared
landmark.sales           # how many photos of it have been sold, by anyone
```

`approach_from = 90` means: photograph it from its **east** side, so you fly **west** towards it. On the GCS map each landmark has a shaded slice: that's where photos count.

### When does a photo count?

All three at once:

1. **Distance:** between `landmark.inner` and `landmark.outer` from the landmark.
2. **Side:** the direction from the landmark to you is at most `landmark.view_width / 2` from `landmark.approach_from`.
3. **Facing:** the direction from you to the landmark is at most `FIELD_OF_VIEW / 2` (30°) from your heading.

---

## Part 5: Lining up (ready-made)

**New:** `approach()`, why a plane needs room to turn. Nothing to write in this part.
**From earlier:** directions and landmarks (4).

A plane can't stop or turn on the spot. To photograph a landmark from the right side, it has to **line up** first: get onto the photo side, pointing at the landmark, far enough out to be flying straight again by the time it gets there.

```python
approach(my_vehicle, landmark)          # flies the plane until it's lined up for landmark, then returns
my_vehicle.simple_goto(landmark.loc)    # then point it at the landmark and watch for the photo
```

Try it: right-click near a landmark → **Line up for this landmark**.

### What `approach()` does

```
                 approach line (out from the landmark, in the direction approach_from)
   point ●───────────────────────────────────── ★ landmark
         ↑ the plane turns in here, far enough out to be straight before the photo zone
```

- **Already lined up?** It doesn't add anything: the plane flies straight in.
- Otherwise it sends the plane to **one point on the approach line**. The more the plane has to turn there, the further out the point is: a turn swings the plane sideways (about `SWING_METERS`, 55 m, for 90°, twice that for a U-turn), and it has to be straight again before the photo zone.
- **Too close to turn round?** The point moves further out, so the plane has room.
- `approach(my_vehicle, landmark, turning_circle=True)`: when the plane has to turn round, it follows a circle the size of its own turn instead, like a pilot's procedure turn. Measured: about 6–9 s quicker when turning round, but from straight behind it sometimes misses. Your call.
- `get_approach_points(landmark, position, heading)` gives you the points without flying them, e.g. to draw or time a route. `is_lined_up(landmark, position, heading)` tells you if the plane can go straight in.

All of it is in `toolkit.py`, written to be read.

### A point some distance away in some direction

Handy for your own strategies (part 7), e.g. to wait somewhere near where landmarks appear:

```python
get_location_from(location, distance, direction)   # 300 m east of a landmark: (landmark.loc, 300, 90)
```

---

## Part 6: Photographing landmarks

**New:** `get_known_landmarks()`, `take_photo()`, picking from a list. Buttons already there: **Take photo** (top bar) and **Capture this landmark** (right-click near one, once `capture` is written).
**From earlier:** `fly_to` (2), `@button` (3), `can_photograph` (4), `approach` (5).

```python
landmarks = get_known_landmarks()   # list of Landmark you can photograph now
take_photo()                        # True if it sold; if not, it prints why
```

- The game checks where your plane **really** is and where it **really** points, so check `can_photograph` first and only then `take_photo()`.
- The **Take photo** button is yours too (`### if ...` in `workshop.py`): let it shoot only when `can_photograph` says yes, and a click can never waste the camera. The whole GCS is yours to tailor like that.
- ⚠️ **A photo that doesn't count costs you:** the camera needs 3 seconds before the next one (the cone on the map turns grey). The photo zone only lasts about 6 seconds as you fly through it, so a wasted shot can cost you the pass.
- Check often while you fly in: the plane covers 20 m every second, so `time.sleep(0.2)` rather than `time.sleep(1)`.
- After a sale, the landmark disappears from your list.
- Flown past it without a photo? Call `approach()` again: it works out a new way in from wherever the plane is.

### 🧩 Python: the nearest one

```python
here = my_vehicle.location.global_relative_frame
nearest = min(landmarks, key=lambda landmark: get_distance_meters(here, landmark.loc))
```

---

## Rounds

Put the address from the board in `GAME_SERVER_URL` at the top of `workshop.py` (and your name in `PILOT_NAME`), save, and click **Connect**. The server gives you a plane; the first time it can take a few seconds to start.

- Outside a round you practise on landmarks of your own, as before.
- **Countdown:** when we start a round, your plane is put down at its start position, near a corner of the map, on the ground: take off again. (A plane on your own laptop started with `sim_vehicle.py` can't be moved, so it flies there once it's in the air.) Any button that was running stops.
- **Go:** landmarks appear on everyone's map. Press your strategy button.
- Photographing a landmark **first** can make a new one appear nearby. For a few seconds only you know about it (`head_start` counts down), then everyone does. Sometimes two appear, the second shown to everyone straight away.
- A landmark nobody has photographed yet slowly **gains value**. Each photo of it pays less than the one before, down to a minimum, so even a much-photographed one is worth a small detour.
- The area where new landmarks appear (the dashed rectangle) **shrinks** towards the middle during the round. Landmarks already outside it stay.
- A landmark nobody has photographed yet slowly gains value.
- The **Score** panel shows the round, your place, the leader and whoever is just ahead of you. Other planes are the grey arrows.

---

## Part 7: Your strategies

**New:** how long a plane needs, other planes, time left, your score.
**From earlier:** everything.

### How long will it take?

```python
here = my_vehicle.location.global_relative_frame
get_eta(here, my_vehicle.heading, landmark)   # seconds until you could take the photo, lining up included
```

It follows the same route as `approach()`, turns included, so you never do the turn maths yourself. Measured: usually within 3 s; when the plane starts close to the landmark and badly placed, it can take 10–15 s longer.

### Other planes

```python
for plane in get_other_drones():                 # everyone else's plane
    plane.name, plane.loc, plane.heading
    get_eta(plane.loc, plane.heading, landmark)  # how long they'd need for the same landmark
```

Will someone beat you to it? Compare their `get_eta` with yours. (It's what a good pilot would need: they may not fly the best route.)

### The round and your score

```python
get_seconds_left()   # seconds left in the round, None outside one
get_score()          # {"money": ..., "rank": ..., "players": ..., "leader": {...}, "ahead": {...}} in a round
```

What you know about each landmark: where, which side, `price`, `public`, `head_start`. What you know about the others: who, where, which way, and how long they'd need. The rest is up to you.

---

## Anytime: landing and coming home

```python
land_at(my_vehicle, lat, lon)   # glides to (lat, lon) and lands there (in toolkit.py)
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
- **It worked, then stopped after I saved.** Saving restarts the backend, which stops a running button. Click the button again.
- **Something went badly wrong** (crashed, stuck in a strange mode)? Right-click the map → **Reset SITL**. The simulator restarts with your plane back on the runway, and the GCS reconnects by itself after a few seconds.
- **My button doesn't show up.** Did you save? Is `@button("...")` right above the `def`?
- **The photo never counts.** Print what `can_photograph` checks, one condition at a time. Most often the plane is on the wrong side or turned in too late.
