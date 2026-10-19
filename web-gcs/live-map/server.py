"""
Game server and live map, for the laptop at the front.

Every participant's GCS backend sends its plane's telemetry here twice a second and gets back what it
needs for the game (round, landmarks, score, other planes). The full screen map (index.html) shows all
the planes, public landmarks and the leaderboard on the projector; the organisers start and stop rounds
from /organiser. The game itself is in contest.py.

Run:  python server.py   then open http://localhost:8080 on the projector.
"""
import logging
import math
import os
import secrets
import socket
import threading
import time
from collections import deque

from flask import Flask, jsonify, request, send_from_directory

from contest import Contest

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('werkzeug').setLevel(logging.WARNING) # Hide the log line for every telemetry update

PORT = 8080
MAX_NAME_LENGTH = 24
TRAIL_LENGTH = 240 # Trail points kept per drone (about 2 minutes at 2 updates per second)
# Distinct colours that stay readable on the OSM map, given out in order of arrival
COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#00a3a3",
    "#f032e6", "#9a6324", "#808000", "#000075", "#e6a800", "#800000",
]

# Needed for the organiser page, so participants on the same network can't start rounds
ORGANISER_KEY = os.environ.get("ORGANISER_KEY") or secrets.token_hex(3)

app = Flask(__name__)
contest = Contest()
drones = {} # GCS id (or name, for senders without one) -> latest state of that drone
drones_lock = threading.Lock() # Flask serves every request in its own thread
next_color = 0


def to_float(value):
    """Returns value as a float, or None if it is missing or not a finite number."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


@app.route('/')
def index():
    return send_from_directory(app.root_path, 'index.html')


@app.route('/planner')
def planner():
    """Map for planning the challenge: landmarks, the angles they must be seen from, and a test drone."""
    return send_from_directory(app.root_path, 'planner.html')


@app.route('/organiser')
def organiser():
    """Round controls for the organisers: /organiser?key=... (the key is printed when the server starts)."""
    if request.args.get('key') != ORGANISER_KEY:
        return "Wrong or missing key: use the organiser address printed when the server started.", 403
    return send_from_directory(app.root_path, 'organiser.html')


@app.route('/api/telemetry', methods=['POST'])
def receive_telemetry():
    """Stores the latest telemetry of one drone, and answers with that player's view of the game."""
    global next_color
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Expected a JSON object"}), 400

    name = str(data.get("name", "")).strip()[:MAX_NAME_LENGTH]
    lat = to_float(data.get("lat"))
    lon = to_float(data.get("lon"))
    if not name or lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
        return jsonify({"status": "error", "message": "Missing or invalid name, lat or lon"}), 400

    # The GCS sends a random id it keeps in a file, so a player stays the same player after a reconnect
    player_id = str(data.get("id") or f"name:{name}")[:64]
    with drones_lock:
        drone = drones.get(player_id)
        if drone is None:
            drone = {"name": name, "color": COLORS[next_color % len(COLORS)], "trail": deque(maxlen=TRAIL_LENGTH)}
            next_color += 1
            drones[player_id] = drone
            logging.info(f"New drone on the map: {name}")

        drone.update({
            "name": name,
            "lat": lat,
            "lon": lon,
            "alt": to_float(data.get("alt")),
            "heading": to_float(data.get("heading")),
            "groundspeed": to_float(data.get("groundspeed")),
            "mode": str(data.get("mode", ""))[:16],
            "armed": bool(data.get("armed")),
            "last_seen": time.time(),
        })
        # Only add trail points when the drone moved, so hovering doesn't fill the trail
        if not drone["trail"] or drone["trail"][-1] != (lat, lon):
            drone["trail"].append((lat, lon))

    game = contest.update_player(player_id, name, {"lat": lat, "lon": lon, "heading": to_float(data.get("heading"))},
                                 time.time())
    return jsonify({"status": "success", "game": game})


@app.route('/api/photo', methods=['POST'])
def take_photo():
    """A photo from a player's plane: {id, lat, lon, heading} as their GCS saw it at that moment."""
    data = request.get_json(silent=True) or {}
    reported = (to_float(data.get("lat")), to_float(data.get("lon")), to_float(data.get("heading")))
    player_id = str(data.get("id", ""))
    sold, text = contest.photo(player_id, reported, time.time())
    logging.info(f"Photo from {drones.get(player_id, {}).get('name', '?')}: {text}")
    # The new state too, so a sold landmark is gone from the player's list straight away
    return jsonify({"status": "success", "sold": sold, "text": text, "game": contest.state_for(player_id, time.time())})


@app.route('/api/game')
def game_view():
    """What the projector shows: round, public landmarks, leaderboard, latest sales."""
    return jsonify(contest.public_view(time.time()))


def organiser_only():
    data = request.get_json(silent=True) or {}
    if (data.get("key") or request.args.get("key")) != ORGANISER_KEY:
        return None, (jsonify({"status": "error", "message": "Wrong organiser key"}), 403)
    return data, None


@app.route('/api/organiser')
def organiser_view():
    _, error = organiser_only()
    return error or jsonify(contest.organiser_view(time.time()))


@app.route('/api/organiser/start', methods=['POST'])
def start_round():
    """{key, name: "test" or "real", minutes, seed, countdown}"""
    data, error = organiser_only()
    if error:
        return error
    name = str(data.get("name") or "test")[:20]
    minutes = to_float(data.get("minutes")) or 6
    countdown = to_float(data.get("countdown"))
    seed = int(to_float(data.get("seed")) or 1)
    contest.start(name, minutes, time.time(), seed=seed, countdown=countdown)
    logging.info(f"Round '{name}' starting: {minutes} min, seed {seed}")
    return jsonify({"status": "success"})


@app.route('/api/organiser/stop', methods=['POST'])
def stop_round():
    _, error = organiser_only()
    if error:
        return error
    contest.stop(time.time())
    logging.info("Round stopped.")
    return jsonify({"status": "success"})


@app.route('/api/organiser/reset', methods=['POST'])
def reset_round():
    """Back to no round: clears landmarks and money."""
    _, error = organiser_only()
    if error:
        return error
    contest.reset()
    logging.info("Round reset.")
    return jsonify({"status": "success"})


@app.route('/api/drones')
def get_drones():
    """Returns every drone the map has seen, with how many seconds ago it last reported."""
    now = time.time()
    with drones_lock:
        result = [
            {**drone, "key": key, "trail": list(drone["trail"]), "age": now - drone["last_seen"]}
            for key, drone in drones.items()
        ]
    for drone in result:
        del drone["last_seen"]
    return jsonify(result)


@app.route('/api/reset', methods=['POST'])
def reset():
    """Removes every drone from the map, e.g. between rounds:  curl -X POST http://localhost:8080/api/reset"""
    global next_color
    with drones_lock:
        drones.clear()
        next_color = 0
    logging.info("Map reset.")
    return jsonify({"status": "success"})


def local_ip():
    """This laptop's address on the local network (no data is actually sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


if __name__ == '__main__':
    logging.info(f"Map for the projector: http://localhost:{PORT}")
    logging.info(f"Organiser page: http://localhost:{PORT}/organiser?key={ORGANISER_KEY}")
    logging.info(f"GAME_SERVER_URL for the participants: http://{local_ip()}:{PORT}")
    # 0.0.0.0 so the participants' laptops on the same network can reach it
    app.run(host='0.0.0.0', port=PORT, threaded=True)
