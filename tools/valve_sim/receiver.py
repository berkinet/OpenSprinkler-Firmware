"""Local fake valves only: records HTTP commands, never controls hardware."""
import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4


def serve(log_path, zones=0):
    state = {"lt": False, "rm": False}
    state.update({f"zone{i}": False for i in range(1, zones+1)})
    events = deque(maxlen=10000)
    session = str(uuid4())
    sequence = 0
    log_path.parent.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal sequence
            path = urlsplit(self.path).path
            if path in ("/state", "/status"):
                body = dict(service="opensprinkler-valve-simulator", session=session,
                            states=state, sequence=sequence)
                if path == "/status":
                    body['events'] = list(events)
            else:
                parts = path.strip("/").split("/")
                if (len(parts) != 3 or parts[0] != "sim" or
                        parts[1] not in state or parts[2] not in ("on", "off")):
                    self.send_error(404)
                    return
                _, zone, action = parts
                value = action == "on"
                sequence += 1
                event = dict(sequence=sequence, session=session, zone=zone,
                             action=action, changed=state[zone] != value,
                             monotonic=time.monotonic(), unix=time.time())
                with log_path.open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
                state[zone] = value
                events.append(event)
                body = dict(result=1, simulated=True, **event)
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    # Deliberately fixed to loopback. This is not a production bridge adapter.
    HTTPServer(("127.0.0.1", 18080), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--zones", type=int, choices=range(0, 201), default=0, metavar="0..200")
    args = parser.parse_args()
    serve(args.log, args.zones)
