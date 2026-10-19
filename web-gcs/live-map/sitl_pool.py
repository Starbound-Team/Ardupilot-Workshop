"""
Server SITLs: which laptop runs which participant's plane.

SITL agents (sitl_agent.py, on every laptop that hosts planes) check in every second with the planes they
run, and get back the planes they should start. A GCS asks for its plane with its id; the first time, the
agent with the most free room starts one for it, and after that the plane stays that player's, so a GCS
that restarts gets the same plane back.

Pure logic with the time passed in, like contest.py; server.py holds one SitlPool.
"""
import threading

AGENT_TIMEOUT = 10 # s without a check-in before an agent (and its planes) counts as gone
BASE_PORT = 5760 # SITL instance N listens on BASE_PORT + 10 * N


class SitlPool:
    def __init__(self):
        self.lock = threading.Lock()
        self.agents = {} # agent id -> {"ip", "max", "seen", "planes": {instance: state}, "to_start": set()}
        self.assigned = {} # player id -> (agent id, instance)

    def agent_check_in(self, agent_id, ip, max_planes, planes, now):
        """planes: {instance: "starting" or "ready"} as the agent sees them. Returns the instances to start."""
        with self.lock:
            agent = self.agents.setdefault(agent_id, {"to_start": set()})
            agent.update(ip=ip, max=max_planes, seen=now, planes={int(i): state for i, state in planes.items()})
            agent["to_start"] -= set(agent["planes"]) # Those it has started now
            return sorted(agent["to_start"])

    def _alive(self, now):
        return {aid: a for aid, a in self.agents.items() if now - a["seen"] <= AGENT_TIMEOUT}

    def _used(self, agent_id, agent):
        return set(agent["planes"]) | agent["to_start"] | {i for aid, i in self.assigned.values() if aid == agent_id}

    def plane_for(self, player_id, now):
        """("ready", "tcp:ip:port"), ("starting", None) or ("none", why not)."""
        with self.lock:
            alive = self._alive(now)
            if player_id in self.assigned:
                agent_id, instance = self.assigned[player_id]
                agent = alive.get(agent_id)
                if agent is not None:
                    state = agent["planes"].get(instance)
                    if state == "ready":
                        return "ready", f"tcp:{agent['ip']}:{BASE_PORT + 10 * instance}"
                    if state is None:
                        agent["to_start"].add(instance) # The agent lost it (restarted?): start it again
                    return "starting", None
                del self.assigned[player_id] # Its laptop is gone: a new plane somewhere else
            if not alive:
                return "none", "No laptop is hosting planes"
            agent_id, agent = max(alive.items(), key=lambda item: item[1]["max"] - len(self._used(*item)))
            used = self._used(agent_id, agent)
            if len(used) >= agent["max"]:
                return "none", "All planes are taken"
            instance = next(i for i in range(1, 1000) if i not in used)
            agent["to_start"].add(instance)
            self.assigned[player_id] = (agent_id, instance)
            return "starting", None

    def view(self, now, names):
        """For the organiser page. names: player id -> name."""
        with self.lock:
            owners = {plane: pid for pid, plane in self.assigned.items()}
            return [{"agent": aid, "ip": a["ip"], "max": a["max"], "alive": now - a["seen"] <= AGENT_TIMEOUT,
                     "planes": [{"port": BASE_PORT + 10 * i, "state": a["planes"].get(i, "to start"),
                                 "player": names.get(owners.get((aid, i)), "-" if (aid, i) not in owners else "?")}
                                for i in sorted(set(a["planes"]) | a["to_start"])]}
                    for aid, a in sorted(self.agents.items())]
