"""Serve the packaged UI assets for a LAN-only development controller."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Assets(SimpleHTTPRequestHandler):
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
    args = parser.parse_args()
    if not (args.directory / "modules.json").is_file():
        parser.error("Expected packaged UI directory containing modules.json")
    handler = partial(Assets, directory=str(args.directory.resolve()))
    ThreadingHTTPServer((args.bind, args.port), handler).serve_forever()
