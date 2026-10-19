"""
The photo game, as the organisers' server runs it: rounds, landmarks, photos, money.

Pure logic with no web server, so it can be tested on its own: every method takes the time (`now`,
seconds) from the caller. server.py holds one Contest and calls it from its routes.

The rules below are the best set from the SITL trial (organiser/sitl-tests/photo_game_trial.py on the
solutions branch) and are still provisional: all the numbers are in RULES so they are easy to change.
"""
import math
import random
import threading

METERS_PER_DEGREE = 111319.5
CENTER = (39.36052354733652, 22.949173450469974) # The church, middle of the game area

RULES = {
    "countdown_seconds": 60, # Before a round: planes fly themselves to their start positions
    "start_radius": 1000, # m from CENTER to each plane's start position, spread evenly around it
    "first_distance": (400, 600), # m from a plane's start position to its own first landmark
    "next_distance": (400, 700), # m from a landmark to the one(s) photographing it reveals
    "lean_after": 600, # m from CENTER beyond which new landmarks lean back towards it
    "lean_width": 100, # degrees: how wide that lean is
    "max_from_center": 1800, # m
    "area": (39.355, 22.922, 39.378, 22.968), # South, west, north, east: landmarks only appear over Volos
    "min_spacing": 250, # m between landmarks
    "two_chance": 0.3, # Chance that a landmark reveals two next ones; the second is public straight away
    "base_price": 100,
    "price_step": 20, # Extra per step down a chain
    "price_drop": 0.7, # Each sale of a landmark pays this much of the one before
    "growth_per_minute": 0.2, # Value a landmark gains per minute while nobody has photographed it
    "inner": 30, "outer": 150, "view_width": 60, # Photo zone of every landmark (m, m, degrees)
    "field_of_view": 60, # degrees
    "photo_cooldown": 3, # s after a photo that didn't count
    "active_after": 10, # s without telemetry before a plane counts as gone
    "trust_distance": 40, # m: a photo's reported position may be this far from the last telemetry
    "trust_heading": 45, # degrees, the same for heading
}


# ---------- Measuring (the same flat-earth maths as game.py) ----------
def distance(a, b):
    north = (b[0] - a[0]) * METERS_PER_DEGREE
    east = (b[1] - a[1]) * METERS_PER_DEGREE * math.cos(math.radians(a[0]))
    return math.hypot(north, east)


def direction(a, b):
    north = (b[0] - a[0]) * METERS_PER_DEGREE
    east = (b[1] - a[1]) * METERS_PER_DEGREE * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(east, north)) % 360


def location_from(a, meters, bearing):
    d = math.radians(bearing)
    return (a[0] + meters * math.cos(d) / METERS_PER_DEGREE,
            a[1] + meters * math.sin(d) / (METERS_PER_DEGREE * math.cos(math.radians(a[0]))))


def angle_between(a, b):
    return abs((a - b + 180) % 360 - 180)


class Contest:
    def __init__(self, rules=None):
        self.rules = dict(RULES, **(rules or {}))
        self.lock = threading.Lock()
        self.players = {} # id -> {"name", "lat", "lon", "heading", "seen", ...}
        self._reset_round()

    def _reset_round(self):
        self.round = {"state": "idle", "name": None, "seed": None, "minutes": None,
                      "countdown_ends": None, "ends": None}
        self.landmarks = {} # name -> landmark dict
        self.public = set() # names everyone knows
        self.private = {} # player id -> names only they know
        self.sold = {} # landmark name -> player ids who sold it, in order
        self.money = {} # player id -> money this round
        self.sales = [] # (seconds into the round, player id, landmark name, price)
        self.start_positions = {} # player id -> (lat, lon)
        self.camera_ready_at = {} # player id -> time

    # ---------- Players ----------
    def update_player(self, player_id, name, telemetry, now):
        """Latest telemetry of one plane. Returns what that player should know (see state_for)."""
        with self.lock:
            player = self.players.setdefault(player_id, {"name": name})
            player.update(telemetry, name=name, seen=now)
            if self.round["state"] in ("countdown", "running") and player_id not in self.start_positions:
                self._join(player_id, now) # Joined late: still gets a start and a first landmark
            self._tick(now)
            return self._state_for(player_id, now)

    def _active(self, now):
        return [pid for pid, p in self.players.items() if now - p["seen"] <= self.rules["active_after"]]

    def _join(self, player_id, now):
        taken = len(self.start_positions)
        bearing = 360 * taken / max(len(self._active(now)), taken + 1) + 30
        start = location_from(CENTER, self.rules["start_radius"], bearing)
        self.start_positions[player_id] = start
        self.money.setdefault(player_id, 0)
        towards_center = (bearing + 180) % 360
        first = self._new_landmark(f"P{taken + 1}", start, self.rules["first_distance"], depth=0, now=now,
                                   bearings=(towards_center - 30, towards_center + 30))
        self.private.setdefault(player_id, set()).add(first["name"])

    # ---------- Rounds ----------
    def start(self, name, minutes, now, seed=1, countdown=None):
        """Starts a round: a countdown while the planes fly to their start positions, then the round itself."""
        with self.lock:
            self._reset_round()
            countdown = self.rules["countdown_seconds"] if countdown is None else countdown
            self.round.update(state="countdown", name=name, seed=seed, minutes=minutes,
                              countdown_ends=now + countdown, ends=now + countdown + minutes * 60)
            for player_id in sorted(self._active(now), key=lambda pid: self.players[pid]["name"]):
                self._join(player_id, now)

    def stop(self, now):
        with self.lock:
            if self.round["state"] in ("countdown", "running"):
                self.round.update(state="over", ends=now)

    def reset(self):
        with self.lock:
            self._reset_round()

    def _tick(self, now):
        if self.round["state"] == "countdown" and now >= self.round["countdown_ends"]:
            self.round["state"] = "running"
            for lm in self.landmarks.values():
                lm["born"] = now # Growth counts from the start, not from the countdown
        if self.round["state"] == "running" and now >= self.round["ends"]:
            self.round["state"] = "over"

    def _clock(self, now):
        return now - self.round["countdown_ends"] if self.round["countdown_ends"] else 0

    # ---------- Landmarks ----------
    def _new_landmark(self, name, near, distances, depth, now, bearings=(0, 360)):
        """Made up the first time it's needed, but seeded by its name, so a round with the same seed has
        the same landmark in the same place whatever order things happen in."""
        rng = random.Random(f"{self.round['seed']}-{name}")
        rules = self.rules
        south, west, north, east = rules["area"]
        for attempt in range(2000):
            if attempt < 1000:
                loc = location_from(near, rng.uniform(*distances), rng.uniform(*bearings))
            else: # Nothing fits near it: anywhere in the area
                loc = (rng.uniform(south, north), rng.uniform(west, east))
            if (south <= loc[0] <= north and west <= loc[1] <= east
                    and distance(CENTER, loc) <= rules["max_from_center"]
                    and all(distance(loc, other["loc"]) >= rules["min_spacing"] for other in self.landmarks.values())):
                break
        lm = {"name": name, "loc": loc, "depth": depth, "approach_from": rng.randrange(0, 360, 5),
              "view_width": rules["view_width"], "inner": rules["inner"], "outer": rules["outer"],
              "two": rng.random() < rules["two_chance"], "next": None, "born": now}
        self.landmarks[name] = lm
        self.sold.setdefault(name, [])
        return lm

    def _price(self, lm, now):
        rules = self.rules
        sales = len(self.sold[lm["name"]])
        grown = 1
        if not sales and self.round["state"] == "running":
            grown += rules["growth_per_minute"] * (now - lm["born"]) / 60
        return round((rules["base_price"] + rules["price_step"] * lm["depth"]) * grown * rules["price_drop"] ** sales)

    def _known(self, player_id):
        names = self.public | self.private.get(player_id, set())
        return [self.landmarks[n] for n in sorted(names) if player_id not in self.sold[n]]

    def _reveal_after(self, lm, player_id, now):
        """The first photo of lm makes up what comes next; the photographer learns it, others don't."""
        lm["next"] = []
        lean = (0, 360)
        if distance(lm["loc"], CENTER) > self.rules["lean_after"]:
            to_center = direction(lm["loc"], CENTER)
            lean = (to_center - self.rules["lean_width"] / 2, to_center + self.rules["lean_width"] / 2)
        for i in range(2 if lm["two"] else 1):
            child = self._new_landmark(f"{lm['name']}.{i + 1}", lm["loc"], self.rules["next_distance"],
                                       lm["depth"] + 1, now, lean)
            lm["next"].append(child["name"])
            if i == 1:
                self.public.add(child["name"]) # The second of two goes to everyone
            else:
                self.private.setdefault(player_id, set()).add(child["name"])

    # ---------- Photos ----------
    def _photo_problem(self, position, heading, lm):
        d = distance(lm["loc"], position)
        if d > lm["outer"]:
            return f"too far from {lm['name']} ({d:.0f} m)"
        if d < lm["inner"]:
            return f"too close to {lm['name']} ({d:.0f} m)"
        if angle_between(direction(lm["loc"], position), lm["approach_from"]) > lm["view_width"] / 2:
            return f"wrong side of {lm['name']}"
        if angle_between(direction(position, lm["loc"]), heading) > self.rules["field_of_view"] / 2:
            return f"not facing {lm['name']}"
        return None

    def photo(self, player_id, reported, now):
        """
        A photo from player_id's plane. reported = (lat, lon, heading) from their GCS at the moment of the
        photo, used if it agrees with the server's own latest telemetry (which can be half a second old);
        otherwise the server's telemetry counts. Returns (sold, text).
        """
        with self.lock:
            self._tick(now)
            player = self.players.get(player_id)
            if self.round["state"] != "running":
                return False, "No round running"
            if player is None or player_id not in self.start_positions:
                return False, "Not in this round"
            if now < self.camera_ready_at.get(player_id, 0):
                return False, f"Camera not ready for another {self.camera_ready_at[player_id] - now:.1f} s"
            position, heading = (player["lat"], player["lon"]), player["heading"]
            if reported and None not in reported:
                if (distance(position, reported[:2]) <= self.rules["trust_distance"]
                        and angle_between(heading, reported[2]) <= self.rules["trust_heading"]):
                    position, heading = reported[:2], reported[2]
            known = self._known(player_id)
            for lm in known:
                if self._photo_problem(position, heading, lm) is None:
                    return True, self._sell(player_id, lm, now)
            self.camera_ready_at[player_id] = now + self.rules["photo_cooldown"]
            if not known:
                return False, "Nothing to photograph"
            nearest = min(known, key=lambda lm: distance(position, lm["loc"]))
            return False, f"Photo didn't count: {self._photo_problem(position, heading, nearest)}"

    def _sell(self, player_id, lm, now):
        price = self._price(lm, now)
        first = not self.sold[lm["name"]]
        self.sold[lm["name"]].append(player_id)
        self.money[player_id] = self.money.get(player_id, 0) + price
        self.public.add(lm["name"])
        self.private.get(player_id, set()).discard(lm["name"])
        self.sales.append((round(self._clock(now), 1), player_id, lm["name"], price))
        if first:
            self._reveal_after(lm, player_id, now)
        return f"Sold {lm['name']} for {price}"

    # ---------- What each side sees ----------
    def _leaderboard(self):
        players = [(pid, self.players[pid]["name"], money) for pid, money in self.money.items() if pid in self.players]
        return sorted(players, key=lambda p: (-p[2], p[1]))

    def _round_info(self, now):
        info = {"state": self.round["state"], "name": self.round["name"]}
        if self.round["state"] == "countdown":
            info["starts_in"] = max(0, self.round["countdown_ends"] - now)
        if self.round["state"] == "running":
            info["seconds_left"] = max(0, self.round["ends"] - now)
        return info

    def _landmark_view(self, lm, now, player_id=None):
        return {"name": lm["name"], "lat": lm["loc"][0], "lon": lm["loc"][1], "approach_from": lm["approach_from"],
                "view_width": lm["view_width"], "inner": lm["inner"], "outer": lm["outer"],
                "price": self._price(lm, now), "public": lm["name"] in self.public}

    def state_for(self, player_id, now):
        with self.lock:
            self._tick(now)
            return self._state_for(player_id, now)

    def _state_for(self, player_id, now):
        state = {"round": self._round_info(now),
                 "others": [{"name": self.players[pid]["name"], "lat": self.players[pid]["lat"],
                             "lon": self.players[pid]["lon"], "heading": self.players[pid].get("heading")}
                            for pid in self._active(now) if pid != player_id]}
        if self.round["state"] == "idle":
            return state
        playing = player_id in self.start_positions
        if self.round["state"] == "countdown" and playing:
            state["start_position"] = self.start_positions[player_id]
        if self.round["state"] == "running" and playing:
            state["landmarks"] = [self._landmark_view(lm, now) for lm in self._known(player_id)]
        board = self._leaderboard()
        ranks = [pid for pid, _, _ in board]
        mine = [s for s in self.sales if s[1] == player_id]
        score = {"money": self.money.get(player_id, 0), "photos": len(mine),
                 "last_sale": f"{mine[-1][2]} +{mine[-1][3]}" if mine else None}
        if player_id in ranks:
            rank = ranks.index(player_id)
            score["rank"] = rank + 1
            score["players"] = len(ranks)
            score["leader"] = {"name": board[0][1], "money": board[0][2]}
            if rank > 0:
                score["ahead"] = {"name": board[rank - 1][1], "money": board[rank - 1][2]}
        state["score"] = score
        return state

    def public_view(self, now):
        """What the projector shows: the round, public landmarks and the leaderboard."""
        with self.lock:
            self._tick(now)
            return {"round": self._round_info(now),
                    "landmarks": [self._landmark_view(self.landmarks[n], now) for n in sorted(self.public)],
                    "leaderboard": [{"name": name, "money": money} for _, name, money in self._leaderboard()],
                    "sales": [{"time": t, "name": self.players[pid]["name"], "landmark": lm, "price": price}
                              for t, pid, lm, price in self.sales[-8:]]}

    def organiser_view(self, now):
        """Everything, for the organisers' page: who is connected and every landmark, private ones too."""
        view = self.public_view(now)
        with self.lock:
            view["players"] = [{"id": pid, "name": p["name"], "age": round(now - p["seen"], 1),
                                "playing": pid in self.start_positions, "money": self.money.get(pid, 0)}
                               for pid, p in sorted(self.players.items(), key=lambda item: item[1]["name"])]
            view["all_landmarks"] = [dict(self._landmark_view(lm, now), sales=len(self.sold[lm["name"]]))
                                     for lm in self.landmarks.values()]
            view["rules"] = self.rules
            view["round"].update(seed=self.round["seed"], minutes=self.round["minutes"])
        return view
