"""Serve map.html and its GeoJSON files on localhost for Leaflet fetch()."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os


DATA_FOLDER = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000


class MapRequestHandler(SimpleHTTPRequestHandler):
    """Serve the map and provide a live listing of GeoJSON files."""

    def do_GET(self):
        if self.path == "/api/files":
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
        super().do_GET()


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
