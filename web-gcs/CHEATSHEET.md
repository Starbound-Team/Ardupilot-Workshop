# ✈️ DroneKit Cheat Sheet

Everything you need for `backend/workshop.py`. In the workshop functions the plane is called `my_vehicle`.

> Saving `workshop.py` restarts the backend, so click **Connect** again after every edit.

---

## Flight modes

| Mode | What the plane does |
|---|---|
| `TAKEOFF` | Speeds up, lifts off and climbs straight ahead. **You need this for takeoff.** |
| `GUIDED` | Follows your code's commands. **You need this for goto.** |
| `RTL` | Flies back to where it took off and circles above it (it does *not* land) |
| `AUTO` | Flies a mission. `land_at()` uses it for you |

```python
my_vehicle.mode = VehicleMode("GUIDED")   # ask for a mode change
my_vehicle.mode.name                      # current mode, e.g. "GUIDED"
```

⚠️ A mode change is a *request*, not instant. Wait until `my_vehicle.mode.name` actually changes before carrying on.

## Arming

Motors must be armed before takeoff.

```python
my_vehicle.is_armable      # True when GPS and sensors are ready
my_vehicle.armed = True    # ask to arm
my_vehicle.armed           # True / False: is it armed right now?
```

⚠️ Just after SITL starts, the plane refuses to arm for about half a minute (the console says `Gyros inconsistent`). Wait a bit and try again.

## Takeoff

```python
my_vehicle.parameters['TKOFF_ALT'] = 30   # climb to 30 m
my_vehicle.mode = VehicleMode("TAKEOFF")
my_vehicle.armed = True                   # once armed, it goes by itself
```

There is no takeoff command: armed in `TAKEOFF` mode, the plane rolls down the runway and climbs **straight ahead**, in the direction it was facing on the ground.

## Where is the plane?

```python
loc = my_vehicle.location.global_relative_frame
loc.lat    # latitude
loc.lon    # longitude
loc.alt    # altitude in metres, above the takeoff point
```

Other useful readings:

```python
my_vehicle.groundspeed       # m/s
my_vehicle.heading           # degrees, 0 = north
my_vehicle.battery.voltage   # volts
```

## Going somewhere

```python
target = LocationGlobalRelative(39.3595, 22.9302, 30)   # lat, lon, altitude (m)
my_vehicle.simple_goto(target)
```

⚠️ This returns immediately. The plane flies there on its own, and **your code has to check when it has arrived.**

⚠️ A plane can't stop. It flies past the point 25 m away or more, and then **circles around it, about 50 m away,** until you give it somewhere else to go. So "arrived" means "within about 60 m".

💡 To get coordinates, right-click the map in the GCS, or use Google Maps (right-click → click the numbers to copy them).

## How far away is it?

Already written for you in `workshop.py`:

```python
get_distance_meters(location1, location2)   # metres between two locations
```

## Points in a circle

Also already written for you:

```python
points = generate_circle_waypoints(center_lat, center_lon, altitude, radius, num_points)
# returns a list of LocationGlobalRelative points around the centre
```

A plane can't turn tightly: keep the radius at 150 m or more.

## Waiting in place

A plane can't hover. After a `simple_goto` it circles the point, so to wait somewhere, send it there and wait:

```python
time.sleep(10)   # circle for 10 seconds
```

## Landing

Already written for you:

```python
land_at(my_vehicle, lat, lon)   # glides to (lat, lon) and lands there
```

It flies in a straight line from wherever the plane is and comes down on the way, so the landing is short if you arrive **low and already pointing at the landing spot**. It touches down within about 100 m of the point and rolls a bit.

---

## 🧩 Python you'll need

**Waiting for something to happen.** This is the pattern you'll use most:

```python
while not something_is_true:
    print("Waiting...")
    time.sleep(1)       # ⚠️ always sleep inside the loop!
```

**Leaving a loop early:**

```python
while True:
    if close_enough:
        break
    time.sleep(1)
```

**Going through a list:**

```python
for point in points:
    ...

for i, point in enumerate(points):   # i = 0, 1, 2, ...
    ...
```

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
