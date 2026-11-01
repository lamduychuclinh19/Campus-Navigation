"""Serve map.html and its GeoJSON files on localhost for Leaflet fetch()."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlsplit


DATA_FOLDER = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000
ROUTE_LOCK = threading.Lock()


class MapRequestHandler(SimpleHTTPRequestHandler):
    """Serve the map and provide a live listing of GeoJSON files."""

    def do_GET(self):
        request = urlsplit(self.path)
        if request.path == "/api/files":
            files = {
                folder: sorted(path.name for path in (DATA_FOLDER / folder).glob("*.geojson"))
                for folder in ("ways", "nodes")
            }
            body = json.dumps(files, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if request.path == "/api/route":
            params = parse_qs(request.query)
            try:
                latitude = float(params["lat"][0])
                longitude = float(params["lon"][0])
                destination = params["destination"][0]
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    raise ValueError("Latitude or longitude is out of range.")
                if Path(destination).name != destination or destination in (".", ".."):
                    raise ValueError("Invalid destination ID.")
            except (KeyError, IndexError, ValueError) as error:
                self._send_json(400, {"error": f"Invalid route request: {error}"})
                return

            route_script = DATA_FOLDER.parent / "scripts" / "route_between_places.py"
            with ROUTE_LOCK:
                try:
                    result = subprocess.run(
                        [sys.executable, str(route_script), destination,
                         "--start-coordinate", str(latitude), str(longitude)],
                        cwd=DATA_FOLDER.parent,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                except subprocess.TimeoutExpired:
                    self._send_json(504, {"error": "Route calculation took too long; please try again."})
                    return
                if result.returncode != 0:
                    self._send_json(422, {"error": result.stdout.strip() or result.stderr.strip() or "No route found."})
                    return

                route_path = DATA_FOLDER / "routing" / "route_result.geojson"
                try:
                    route = json.loads(route_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    self._send_json(500, {"error": f"Could not read route result: {error}"})
                    return
            self._send_json(200, {"route": route, "summary": result.stdout.strip()})
            return

        super().do_GET()

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    os.chdir(DATA_FOLDER)
    server = ThreadingHTTPServer((HOST, PORT), MapRequestHandler)
    print(f"Mở bản đồ tại: http://{HOST}:{PORT}/map.html")
    print("Nhấn Ctrl+C để dừng web server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng web server.")
    finally:
        server.server_close()
