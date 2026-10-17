# 🛸 DroneKit Cheat Sheet

Everything you need for `backend/workshop.py`. In the workshop functions the drone is called `my_vehicle`.

> Saving `workshop.py` restarts the backend, so click **Connect** again after every edit.

---

## Flight modes

| Mode | What the drone does |
|---|---|
| `GUIDED` | Follows your code's commands. **You need this for takeoff and goto.** |
| `RTL` | Returns to where it took off and lands |
| `LAND` | Lands right where it is |

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

## Takeoff

```python
my_vehicle.simple_takeoff(20)   # climb to 20 m (must be GUIDED and armed)
```

⚠️ This returns immediately, while the drone is still climbing. If you send another command too early, the climb is cancelled.

## Where is the drone?

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
target = LocationGlobalRelative(39.3595, 22.9302, 20)   # lat, lon, altitude (m)
my_vehicle.simple_goto(target)
```

⚠️ This also returns immediately. The drone flies there on its own, and **your code has to check when it has arrived.**

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

## Hovering in place

In `GUIDED` mode the drone holds its position once it arrives. To hover, just wait:

```python
time.sleep(10)   # hover for 10 seconds
```

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

- **Nothing happens on takeoff.** Is the mode `GUIDED`? Is the drone actually armed? (Check `my_vehicle.armed`, don't assume.)
- **The drone stops climbing halfway.** You sent the next command before the takeoff finished. Wait until `alt` is close to the target (around 95% of it).
- **The GCS freezes.** You have a `while` loop with no `time.sleep()` in it, or one that never ends.
- **The drone flies off somewhere strange.** Latitude and longitude are swapped. In Volos, latitude ≈ **39.36** and longitude ≈ **22.94**.
- **It never "arrives".** No drone stops exactly on the point. Check the distance against a threshold (e.g. `< 3` metres), not `== 0`.
- **It worked, then stopped after I saved.** The backend restarted. Click **Connect** again.
