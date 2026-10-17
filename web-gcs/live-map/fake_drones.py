"""
Sends made-up drones to the live map, to test it without running SITL.
Each fake drone flies its own circle around the launch point.

Usage:  python fake_drones.py [number of drones] [live map address]
        python fake_drones.py 6 http://localhost:8080
"""
import json
import math
import sys
import time
import urllib.request

CENTER_LAT, CENTER_LON = 39.360886, 22.945749
INTERVAL = 0.5 # Seconds between updates, same as the GCS backend
SPEED = 8.0 # m/s

count = int(sys.argv[1]) if len(sys.argv) > 1 else 4
url = (sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8080").rstrip('/') + '/api/telemetry'
start = time.time()

print(f"Sending {count} fake drones to {url}, Ctrl+C to stop")
while True:
    elapsed = time.time() - start
    for i in range(count):
        radius = 60 + 40 * i
        angle = elapsed * SPEED / radius + i # Radians travelled, offset so they don't line up
        lat = CENTER_LAT + radius * math.cos(angle) / 111319.5
        lon = CENTER_LON + radius * math.sin(angle) / (111319.5 * math.cos(math.radians(CENTER_LAT)))
        heading = (math.degrees(angle) + 90) % 360 # Tangent to the circle, flying clockwise

        payload = {
            "name": f"Fake {i + 1}",
            "lat": lat, "lon": lon, "alt": 20 + i,
            "heading": heading, "groundspeed": SPEED,
            "mode": "GUIDED", "armed": True,
        }
        request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(request, timeout=1).close()
        except Exception as e:
            print(f"Send failed: {e}")
    time.sleep(INTERVAL)
