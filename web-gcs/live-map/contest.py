"""
The photo game, as the organisers' server runs it: rounds, landmarks, photos, money.

Pure logic with no web server, so it can be tested on its own: every method takes the time (`now`,
seconds) from the caller. server.py holds one Contest and calls it from its routes.

How a round goes:
- During the countdown the planes fly to start positions near the 4 corners of the area.
- From each corner a trail of landmarks leads towards the middle. The trails are the same shape,
  mirrored, so no corner is better off. A trail point is public the moment the one before it is
  photographed. Nothing marks them as a trail: they look like any other landmark.
- The first photo of a trail's last point, and of every landmark after that, makes up the next
  landmark nearby, inside the current area. Only the photographer knows it for a short head start,
  then it goes public. Sometimes there are two, the second public straight away; that happens less as
  the map fills up.
- A landmark's value grows while it's public and unsold. Each sale takes a bite out of what's above
  the price floor, so prices settle on the floor instead of dropping to nothing.
- The area shrinks towards its middle over the round. Landmarks already outside it stay.

Every number is in RULES, so it's easy to change. Landmarks are sent to each GCS as a numbered change
log (see changes_for), so a busy map doesn't mean big answers twice a second.
"""
import math
import random
import threading

METERS_PER_DEGREE = 111319.5

RULES = {
    "countdown_seconds": 60, # Before a round: planes fly themselves to their start positions
    "area": (39.355, 22.922, 39.378, 22.968), # South, west, north, east: where landmarks appear (over Volos)
    "area_end": 0.5, # Size of the area at the round's end, as a fraction of its full width and height
    "start_inset": 0.15, # Start positions are this fraction of the way in from the corners towards the middle
    "trail_points": 4, # Landmarks per trail, from a corner towards the middle
    "trail_end": 300, # m from the middle to each trail's last point
    "trail_wiggle": (60, 160), # m a trail point is off the straight line, alternately left and right
    "trail_view_jitter": 20, # degrees: a trail point's photo zone faces back along the trail, give or take this
    "next_distance": (400, 700), # m from a landmark to the one(s) its first photo makes up
    "lean_after": 600, # m from the middle beyond which new landmarks lean back towards it
    "lean_width": 100, # degrees: how wide that lean is
    "min_spacing": 250, # m between landmarks
    "head_start": 20, # s only the discoverer knows a new landmark, before it goes public
    "split_chance": 0.5, # Chance of two new landmarks instead of one, on an empty map...
    "max_landmarks": (2, 6), # ...falling to 0 at this many landmarks on the map (trails not counted): 2 per player + 6
    "trail_price": 50,
    "base_price": 100, # The first landmark after a trail
    "price_step": 10, # Extra per step further along a chain
    "price_floor": 30, # Prices settle here, however many times a landmark sells
    "sale_keep": 0.7, # Each sale keeps this much of what's above the floor
    "growth_step": 5, # A public landmark nobody has sold gains this much...
    "growth_seconds": 15, # ...every this many seconds
    "inner": 30, "outer": 150, "view_width": 60, # Photo zone of every landmark (m, m, degrees)
    "field_of_view": 60, # degrees
    "photo_cooldown": 3, # s after a photo that didn't count
    "active_after": 10, # s without telemetry before a plane counts as gone
    "trust_distance": 40, # m: a photo's reported position may be this far from the last telemetry
    "trust_heading": 45, # degrees, the same for heading
}

PRICING = ("price_floor", "sale_keep", "growth_step", "growth_seconds") # Rules a GCS needs to work out prices


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


def price(lm, pricing, now, until):
    """
    What a photo of lm sells for at time now. The GCS works this out too (game.py has the same formula),
    so prices growing isn't a change it needs to be sent. until = when the round ends: prices stop there.
    """
    value = lm["value"]
    if lm["public_since"] is not None:
        grew_until = min(t for t in (now, until, lm["first_sale"]) if t is not None)
        value += pricing["growth_step"] * max(0, int((grew_until - lm["public_since"]) // pricing["growth_seconds"]))
    floor = pricing["price_floor"]
    return round(floor + max(0, value - floor) * pricing["sale_keep"] ** lm["sales"])


class Contest:
    def __init__(self, rules=None):
        self.rules = dict(RULES, **(rules or {}))
        self.lock = threading.Lock()
        self.players = {} # id -> {"name", "lat", "lon", "heading", "seen", ...}
        self.round_number = 0
        self.area_end = self.rules["area_end"]
        self._reset_round()

    def _reset_round(self):
        self.round_number += 1 # Tells every GCS its landmarks are from an older round
        self.round = {"state": "idle", "name": None, "seed": None, "minutes": None,
                      "countdown_ends": None, "ends": None}
        self.landmarks = {} # key -> landmark dict; the key ("T2.3", "T2.4.1.2") seeds where it goes
        self.planned = [] # Trail points not on the map yet: [corner][i] -> landmark dict
        self.discoverer = {} # key -> player id who alone knows it, during its head start
        self.sold = {} # key -> player ids who sold it, in order
        self.money = {} # player id -> money this round
        self.sales = [] # (seconds into the round, player id, landmark name, price)
        self.corner_of = {} # player id -> corner number 0-3
        self.camera_ready_at = {} # player id -> time
        self.log = [] # Changes to landmarks, change n is log[n - 1]: (who may see it or None for everyone, change)
        self.area_scale = (1.0, None) # (size, at time): the area shrinks steadily from there to area_end
        self.area_hold = False

    # ---------- Players ----------
    def update_player(self, player_id, name, telemetry, now, have=None):
        """Latest telemetry of one plane. Returns what that player should know (see _state_for)."""
        with self.lock:
            player = self.players.setdefault(player_id, {"name": name})
            player.update(telemetry, name=name, seen=now)
            if self.round["state"] in ("countdown", "running") and player_id not in self.corner_of:
                self._join(player_id) # Joined late: still gets a corner
            self._tick(now)
            return self._state_for(player_id, now, have)

    def _active(self, now):
        return [pid for pid, p in self.players.items() if now - p["seen"] <= self.rules["active_after"]]

    def _join(self, player_id):
        """Corners in turn (NE, SW, NW, SE, then round again), so 2 players start on opposite sides."""
        self.corner_of[player_id] = [0, 2, 3, 1][len(self.corner_of) % 4]
        self.money.setdefault(player_id, 0)

    # ---------- The area ----------
    def _area_middle(self):
        south, west, north, east = self.rules["area"]
        return ((south + north) / 2, (west + east) / 2)

    def _scale(self, now):
        """How big the area is now, as a fraction of its full size."""
        size, since = self.area_scale
        if self.round["state"] != "running" or self.area_hold or since is None:
            return size
        left = self.round["ends"] - since
        done = min(1, (now - since) / left) if left > 0 else 1
        return size + (self.area_end - size) * done

    def _area(self, now):
        """The area now: (south, west, north, east), shrunk towards its middle."""
        south, west, north, east = self.rules["area"]
        middle, scale = self._area_middle(), self._scale(now)
        half_lat, half_lon = (north - south) / 2 * scale, (east - west) / 2 * scale
        return (middle[0] - half_lat, middle[1] - half_lon, middle[0] + half_lat, middle[1] + half_lon)

    def set_area(self, now, end=None, hold=None):
        """From the organiser page: the size to shrink to by the end, and holding the area where it is."""
        with self.lock:
            self.area_scale = (self._scale(now), now if self.round["state"] == "running" else self.area_scale[1])
            if end is not None:
                self.area_end = min(1.0, max(0.1, end))
            if hold is not None:
                self.area_hold = bool(hold)

    # ---------- Rounds ----------
    def start(self, name, minutes, now, seed=1, countdown=None):
        """Starts a round: a countdown while the planes fly to their start positions, then the round itself."""
        with self.lock:
            self._reset_round()
            countdown = self.rules["countdown_seconds"] if countdown is None else countdown
            self.round.update(state="countdown", name=name, seed=seed, minutes=minutes,
                              countdown_ends=now + countdown, ends=now + countdown + minutes * 60)
            self._plan_trails()
            for player_id in sorted(self._active(now), key=lambda pid: self.players[pid]["name"]):
                self._join(player_id)

    def stop(self, now):
        with self.lock:
            if self.round["state"] in ("countdown", "running"):
                self.area_scale = (self._scale(now), now)
                self.round.update(state="over", ends=now)

    def reset(self):
        with self.lock:
            self._reset_round()

    def _tick(self, now):
        if self.round["state"] == "countdown" and now >= self.round["countdown_ends"]:
            self.round["state"] = "running"
            self.area_scale = (1.0, now)
            for trail in self.planned:
                self._appear(trail.pop(0), now) # Each trail's first point
        if self.round["state"] == "running" and now >= self.round["ends"]:
            self.area_scale = (self._scale(now), now)
            self.round["state"] = "over"
        for key, player_id in list(self.discoverer.items()):
            if now >= self.landmarks[key]["head_start_until"]:
                self._go_public(key, now)

    def _clock(self, now):
        return now - self.round["countdown_ends"] if self.round["countdown_ends"] else 0

    # ---------- Landmarks ----------
    def _corner_start(self, corner):
        """Start position of a corner: 0 NE, 1 SE, 2 SW, 3 NW."""
        south, west, north, east = self.rules["area"]
        middle, inset = self._area_middle(), 1 - self.rules["start_inset"]
        sign_lat, sign_lon = (1, -1, -1, 1)[corner], (1, 1, -1, -1)[corner]
        return (middle[0] + sign_lat * (north - south) / 2 * inset, middle[1] + sign_lon * (east - west) / 2 * inset)

    def _plan_trails(self):
        """
        One trail, made up from the round's seed for the NE corner and mirrored onto the others. Points go
        from the start position towards the middle, alternately left and right of the straight line, and each
        photo zone faces back towards the point before, so a plane flies in lined up and the next turn is gentle.
        """
        rules = self.rules
        rng = random.Random(f"{self.round['seed']}-trail")
        middle = self._area_middle()
        north_m = lambda loc: (loc[0] - middle[0]) * METERS_PER_DEGREE # Flat x/y in metres from the middle
        east_m = lambda loc: (loc[1] - middle[1]) * METERS_PER_DEGREE * math.cos(math.radians(middle[0]))
        start = self._corner_start(0)
        sx, sy = east_m(start), north_m(start)
        ex, ey = rules["trail_end"] / math.sqrt(2), rules["trail_end"] / math.sqrt(2)
        length = math.hypot(ex - sx, ey - sy)
        across = (-(ey - sy) / length, (ex - sx) / length) # Unit vector left of the line
        count = rules["trail_points"]
        shape = [] # (east, north, jitter) in metres from the middle, for the NE corner
        for i in range(1, count + 1):
            t = i / count
            side = 0 if i == count else rng.uniform(*rules["trail_wiggle"]) * (1 if i % 2 else -1)
            shape.append((sx + (ex - sx) * t + across[0] * side, sy + (ey - sy) * t + across[1] * side,
                          rng.uniform(-rules["trail_view_jitter"], rules["trail_view_jitter"])))
        self.planned = []
        for corner in range(4):
            mirror_lat, mirror_lon = (1, -1, -1, 1)[corner], (1, 1, -1, -1)[corner]
            to_loc = lambda x, y: (middle[0] + y * mirror_lat / METERS_PER_DEGREE,
                                   middle[1] + x * mirror_lon / (METERS_PER_DEGREE * math.cos(math.radians(middle[0]))))
            previous, trail = self._corner_start(corner), []
            for i, (x, y, jitter) in enumerate(shape):
                loc = to_loc(x, y)
                # Mirroring once flips left and right, so the jitter flips too and the corners stay alike
                approach = (direction(loc, previous) + jitter * mirror_lat * mirror_lon) % 360
                trail.append(self._landmark(f"T{corner}.{i + 1}", loc, approach, rules["trail_price"], depth=0,
                                            last=i == count - 1))
                previous = loc
            self.planned.append(trail)

    def _landmark(self, key, loc, approach_from, value, depth, last=False):
        rules = self.rules
        trail = key.count(".") == 1 # "T2.3"; what comes after a trail is "T2.4.1", "T2.4.1.2" ...
        return {"key": key, "name": None, "loc": loc, "approach_from": round(approach_from) % 360, "value": value,
                "depth": depth, "trail": trail, "chains": not trail or last,
                "view_width": rules["view_width"], "inner": rules["inner"], "outer": rules["outer"],
                "born": None, "public_since": None, "first_sale": None, "sales": 0, "head_start_until": None}

    def _new_landmark(self, key, near, depth, now, bearings):
        """Made up the first time it's needed, but seeded by its key, so a round with the same seed has the
        same landmark in the same place whatever order things happen in (as long as the area is the same)."""
        rng = random.Random(f"{self.round['seed']}-{key}")
        rules = self.rules
        south, west, north, east = self._area(now)
        taken = [lm["loc"] for lm in self.landmarks.values()] + [lm["loc"] for trail in self.planned for lm in trail]
        for attempt in range(2000):
            if attempt < 1000:
                loc = location_from(near, rng.uniform(*rules["next_distance"]), rng.uniform(*bearings))
            else: # Nothing fits near it: anywhere in the area
                loc = (rng.uniform(south, north), rng.uniform(west, east))
            if (south <= loc[0] <= north and west <= loc[1] <= east
                    and all(distance(loc, other) >= rules["min_spacing"] for other in taken)):
                break
        return self._landmark(key, loc, rng.randrange(0, 360, 5),
                              self.rules["base_price"] + self.rules["price_step"] * depth, depth)

    def _record(self, lm):
        """A landmark as a GCS gets it: where, its photo zone and what it needs to work out the price."""
        return {"name": lm["name"], "lat": lm["loc"][0], "lon": lm["loc"][1], "approach_from": lm["approach_from"],
                "view_width": lm["view_width"], "inner": lm["inner"], "outer": lm["outer"], "value": lm["value"],
                "born": lm["born"], "public_since": lm["public_since"], "first_sale": lm["first_sale"],
                "sales": lm["sales"], "head_start_until": lm["head_start_until"]}

    def _change(self, lm, who=None):
        self.log.append((who, {"landmark": self._record(lm)}))

    def _appear(self, lm, now, discoverer=None):
        """Puts lm on the map: public, or known only to its discoverer for the head start."""
        lm["name"] = f"L{len(self.landmarks) + 1}"
        lm["born"] = now
        self.landmarks[lm["key"]] = lm
        self.sold[lm["key"]] = []
        if discoverer is None:
            lm["public_since"] = now
            self._change(lm)
        else:
            lm["head_start_until"] = now + self.rules["head_start"]
            self.discoverer[lm["key"]] = discoverer
            self._change(lm, discoverer)

    def _go_public(self, key, now):
        lm = self.landmarks[key]
        self.discoverer.pop(key, None)
        lm["public_since"] = now
        lm["head_start_until"] = None
        self._change(lm)

    def _price(self, lm, now):
        return price(lm, self.rules, now, self.round["ends"])

    def _knows(self, player_id, lm):
        return self.discoverer.get(lm["key"], player_id) == player_id

    def _known(self, player_id):
        """The landmarks player_id can still sell."""
        return [lm for lm in self.landmarks.values() if self._knows(player_id, lm) and player_id not in self.sold[lm["key"]]]

    def _after(self, lm, player_id, now):
        """The first photo of lm: the next trail point goes public, or new landmarks appear nearby."""
        if not lm["chains"]:
            corner = int(lm["key"][1])
            if self.planned[corner]:
                self._appear(self.planned[corner].pop(0), now)
            return
        rules = self.rules
        middle = self._area_middle()
        lean = (0, 360)
        if distance(lm["loc"], middle) > rules["lean_after"]:
            to_middle = direction(lm["loc"], middle)
            lean = (to_middle - rules["lean_width"] / 2, to_middle + rules["lean_width"] / 2)
        per_player, extra = rules["max_landmarks"]
        most = per_player * len(self.corner_of) + extra
        rng = random.Random(f"{self.round['seed']}-{lm['key']}-split")
        chain = sum(1 for other in self.landmarks.values() if not other["trail"])
        split = rng.random() < rules["split_chance"] * max(0, 1 - chain / most)
        children = [self._new_landmark(f"{lm['key']}.{i + 1}", lm["loc"], lm["depth"] + 1, now, lean)
                    for i in range(2 if split else 1)]
        self._appear(children[0], now, discoverer=player_id)
        if split:
            self._appear(children[1], now) # The second of two goes to everyone

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

    def photo(self, player_id, reported, now, have=None):
        """
        A photo from player_id's plane. reported = (lat, lon, heading) from their GCS at the moment of the
        photo, used if it agrees with the server's own latest telemetry (which can be half a second old);
        otherwise the server's telemetry counts. Returns (sold, text, price or None, that player's state).
        """
        with self.lock:
            self._tick(now)
            sold, text, paid = self._photo(player_id, reported, now)
            return sold, text, paid, self._state_for(player_id, now, have)

    def _photo(self, player_id, reported, now):
        player = self.players.get(player_id)
        if self.round["state"] != "running":
            return False, "No round running", None
        if player is None or player_id not in self.corner_of:
            return False, "Not in this round", None
        if now < self.camera_ready_at.get(player_id, 0):
            return False, f"Camera not ready for another {self.camera_ready_at[player_id] - now:.1f} s", None
        position, heading = (player["lat"], player["lon"]), player["heading"]
        if reported and None not in reported:
            if (distance(position, reported[:2]) <= self.rules["trust_distance"]
                    and angle_between(heading, reported[2]) <= self.rules["trust_heading"]):
                position, heading = reported[:2], reported[2]
        known = self._known(player_id)
        for lm in known:
            if self._photo_problem(position, heading, lm) is None:
                paid = self._sell(player_id, lm, now)
                return True, f"Sold {lm['name']} for {paid}", paid
        self.camera_ready_at[player_id] = now + self.rules["photo_cooldown"]
        if not known:
            return False, "Nothing to photograph", None
        nearest = min(known, key=lambda lm: distance(position, lm["loc"]))
        return False, f"Photo didn't count: {self._photo_problem(position, heading, nearest)}", None

    def _sell(self, player_id, lm, now):
        paid = self._price(lm, now) # The server's price at this moment is what's paid
        first = not self.sold[lm["key"]]
        self.sold[lm["key"]].append(player_id)
        self.money[player_id] = self.money.get(player_id, 0) + paid
        self.sales.append((round(self._clock(now), 1), player_id, lm["name"], paid))
        if first:
            lm["first_sale"] = now
        lm["sales"] += 1
        if lm["key"] in self.discoverer: # Photographed during its head start: everyone knows it now
            self.discoverer.pop(lm["key"])
            lm["public_since"], lm["head_start_until"] = now, None
        self._change(lm)
        self.log.append((player_id, {"sold_by_me": lm["name"]}))
        if first:
            self._after(lm, player_id, now)
        return paid

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

    def changes_for(self, player_id, have):
        """
        The landmark changes player_id hasn't got. have = {"round": n, "upto": n} from their last answer.
        A GCS that's new, restarted or from another round gets everything it may see instead ("full"). A lost
        answer heals itself: their "upto" doesn't move, so the next request asks for the same changes again.
        """
        upto = len(self.log)
        if (not isinstance(have, dict) or have.get("round") != self.round_number
                or not isinstance(have.get("upto"), int) or not 0 <= have["upto"] <= upto):
            return {"round": self.round_number, "upto": upto, "full": True,
                    "landmarks": [self._record(lm) for lm in self.landmarks.values() if self._knows(player_id, lm)],
                    "sold_by_me": [lm["name"] for lm in self.landmarks.values() if player_id in self.sold[lm["key"]]]}
        return {"round": self.round_number, "upto": upto,
                "changes": [dict(change, n=n) for n, (who, change) in enumerate(self.log[have["upto"]:], have["upto"] + 1)
                            if who in (None, player_id)]}

    def state_for(self, player_id, now, have=None):
        with self.lock:
            self._tick(now)
            return self._state_for(player_id, now, have)

    def _state_for(self, player_id, now, have=None):
        state = {"round": self._round_info(now), "now": now, "area": self._area(now),
                 "others": [{"name": self.players[pid]["name"], "lat": self.players[pid]["lat"],
                             "lon": self.players[pid]["lon"], "heading": self.players[pid].get("heading")}
                            for pid in self._active(now) if pid != player_id]}
        if self.round["state"] == "idle":
            return state
        playing = player_id in self.corner_of
        if self.round["state"] == "countdown" and playing:
            state["start_position"] = self._corner_start(self.corner_of[player_id])
        if self.round["state"] in ("running", "over") and playing:
            state["pricing"] = dict({rule: self.rules[rule] for rule in PRICING}, until=self.round["ends"])
            state["landmarks"] = self.changes_for(player_id, have)
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

    def _landmark_view(self, lm, now):
        return {"name": lm["name"], "lat": lm["loc"][0], "lon": lm["loc"][1], "approach_from": lm["approach_from"],
                "view_width": lm["view_width"], "inner": lm["inner"], "outer": lm["outer"],
                "price": self._price(lm, now), "public": lm["key"] not in self.discoverer, "sales": lm["sales"],
                "age": round(now - lm["born"], 1)}

    def public_view(self, now):
        """What the projector shows: the round, the area, public landmarks and the leaderboard."""
        with self.lock:
            self._tick(now)
            return {"round": self._round_info(now), "area": self._area(now),
                    "landmarks": [self._landmark_view(lm, now) for lm in self.landmarks.values()
                                  if lm["key"] not in self.discoverer],
                    "leaderboard": [{"name": name, "money": money} for _, name, money in self._leaderboard()],
                    "sales": [{"time": t, "name": self.players[pid]["name"], "landmark": lm, "price": price}
                              for t, pid, lm, price in self.sales[-8:]]}

    def organiser_view(self, now):
        """Everything, for the organisers' page: who is connected, the area and every landmark, hidden ones too."""
        view = self.public_view(now)
        with self.lock:
            view["players"] = [{"id": pid, "name": p["name"], "age": round(now - p["seen"], 1),
                                "playing": pid in self.corner_of, "money": self.money.get(pid, 0)}
                               for pid, p in sorted(self.players.items(), key=lambda item: item[1]["name"])]
            view["all_landmarks"] = [dict(self._landmark_view(lm, now), trail=lm["trail"],
                                          head_start=max(0, round((lm["head_start_until"] or now) - now, 1)))
                                     for lm in self.landmarks.values()]
            view["area"] = {"box": self._area(now), "full": self.rules["area"], "scale": round(self._scale(now), 3),
                            "end": self.area_end, "hold": self.area_hold}
            view["rules"] = self.rules
            view["round"].update(seed=self.round["seed"], minutes=self.round["minutes"])
        return view
