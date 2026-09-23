"""Serve the packaged UI assets for a LAN-only development controller."""
import argparse
import json
import sys
import signal
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Assets(SimpleHTTPRequestHandler):
    simulation = None
    controller_origin = None

    def reply(self, value, status=200):
        body = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/simulation/status" and self.simulation:
            self.reply(self.simulation.snapshot())
        else:
            super().do_GET()

    def authorized_origin(self):
        return self.headers.get("Origin") == self.controller_origin

    def do_OPTIONS(self):
        if not self.simulation or not self.authorized_origin():
            self.send_error(403); return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if not self.simulation or not self.authorized_origin():
            self.send_error(403); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 262144 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Expected a bounded JSON request")
            body = json.loads(self.rfile.read(length))
            if self.path == "/simulation/config":
                result = self.simulation.configure(body)
            elif self.path == "/simulation/control":
                result = self.simulation.control(body.get("action"))
            else:
                self.send_error(404); return
            self.reply(result)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.reply(dict(error=str(exc)), 400)

    def end_headers(self):
        # The controller page on port 80 loads assets from this separate port.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--simulation-directory", type=Path)
    parser.add_argument("--controller-origin", help="Exact browser origin allowed to apply simulation drafts")
    parser.add_argument("--simulation-speed", type=int, default=60, choices=(1, 10, 60, 300))
    parser.add_argument("--simulation-timezone", default="Europe/Paris")
    parser.add_argument("--simulation-location", type=Path, help="Private JSON latitude/longitude for night rules")
    args = parser.parse_args()
    if not (args.directory / "modules.json").is_file():
        parser.error("Expected packaged UI directory containing modules.json")
    if args.simulation_directory:
        if not args.controller_origin:
            parser.error("Simulation requires --controller-origin")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.valve_sim.automatic import Simulation
        location = json.loads(args.simulation_location.read_text()) if args.simulation_location else None
        Assets.simulation = Simulation(args.simulation_directory, timezone_name=args.simulation_timezone,
            speed=args.simulation_speed, location=location)
        Assets.controller_origin = args.controller_origin
        threading.Thread(target=Assets.simulation.loop, daemon=True).start()
    handler = partial(Assets, directory=str(args.directory.resolve()))
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    def shutdown(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    finally:
        if Assets.simulation:
            Assets.simulation.stop.set()
            with Assets.simulation.lock:
                Assets.simulation.pause('Simulation service stopped')
        server.server_close()
