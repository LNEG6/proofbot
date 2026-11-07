"""Talks to the Switch room directly, so the harness doesn't have to trust an AI to pass things on.

Inside a Switch session, the Console gives an agent SWITCH_API_ENDPOINT, SWITCH_API_TOKEN and SWITCH_AGENT_ID, and
anything that agent runs inherits them. With those the harness can do two things itself:

- post its own verdict to the room, so no AI can retype or soften it
- read who really said something, so only a person's answer counts
"""
import json
import os
import re
import urllib.error
import urllib.request


class SwitchError(Exception):
    pass


def says(body, reply):
    """Did this message give that answer? A letter must stand alone; words can sit inside a longer message."""
    text = " ".join(re.sub(r"@\S+", " ", body or "").lower().split())
    wanted = " ".join(reply.lower().split())
    if len(wanted) > 2:
        return wanted in text
    return re.findall(r"\w+", text) in ([wanted], ["option", wanted])


class Room:
    def __init__(self, name, env=None, timeout=20):
        env = os.environ if env is None else env
        self.endpoint = (env.get("SWITCH_API_ENDPOINT") or "").rstrip("/")
        self.token, self.agent = env.get("SWITCH_API_TOKEN"), env.get("SWITCH_AGENT_ID")
        self.timeout = timeout
        if not (self.endpoint and self.token and self.agent):
            raise SwitchError("this isn't running inside a Switch session")
        rooms = [room for room in self.op("list_rooms") if room.get("name", "").lower() == name.lower()]
        if len(rooms) != 1:
            raise SwitchError(f"found {len(rooms)} rooms called {name}")
        self.id = rooms[0]["room_id"]

    def call(self, path, body):
        request = urllib.request.Request(f"{self.endpoint}{path}", data=json.dumps(body).encode("utf-8"), method="POST",
                                         headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            raise SwitchError(f"Switch said {error.code} to {path}") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise SwitchError(f"couldn't reach Switch ({type(error).__name__})") from None

    def op(self, name, **args):
        return self.call(f"/agents/{self.agent}/ops/{name}", args).get("result")

    def post(self, text):
        self.call(f"/agents/{self.agent}/message", {"room_id": self.id, "content": text})

    def people_said(self, since):
        """What people, not agents, have said in this room since a time in milliseconds, oldest first."""
        agents = set(self.op("get_room_detail", room_id=self.id).get("agent_names") or [])
        timeline = self.op("read_context", limit=100, room_id=self.id) or {}
        said = [entry for thread in timeline.get("threads", []) for entry in [thread.get("root"), *thread.get("replies", [])] if entry]
        return sorted((entry for entry in said if entry.get("kind") == "message" and entry.get("sender_name") not in agents
                       and (entry.get("timestamp") or 0) >= since), key=lambda entry: entry["timestamp"])

    def confirm(self, reply, since):
        """The newest message from a person that gave this answer, or None. This is what makes an answer a person's."""
        for entry in reversed(self.people_said(since)):
            if says(entry.get("body"), reply):
                return entry
        return None
