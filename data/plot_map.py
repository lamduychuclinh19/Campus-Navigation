"""Serve map.html and its GeoJSON files on localhost for Leaflet fetch()."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
<<<<<<< HEAD
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
=======
import math
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from gps_routing import (RoutingError, route_between_places, route_from_gps,
                         read_access_rows, projection_for_graph)
from graph_editor import GraphEditError, load_graph_snapshot, save_graph_changes
from dual_gps_routing import evaluate_gps_routes


DATA_FOLDER = Path(__file__).resolve().parent
ROUTING_FOLDER = DATA_FOLDER / "routing"
GRAPH_PATH = ROUTING_FOLDER / "graph.json"
GRAPH_NODES_PATH = ROUTING_FOLDER / "graph_nodes.csv"
GRAPH_BACKUP_FOLDER = ROUTING_FOLDER / "backups"
GRAPH_EDIT_LOG = ROUTING_FOLDER / "graph_edit_log.jsonl"
HOST = "127.0.0.1"
PORT = int(os.environ.get("CAMPUSNAV_PORT", "8000"))
>>>>>>> afb3adc (feat:them 2 thuat toan tim duong ,chinh sua giao dien ,tao gps de test)


class MapRequestHandler(SimpleHTTPRequestHandler):
    """Serve the map and provide a live listing of GeoJSON files."""

    def do_GET(self):
<<<<<<< HEAD
        request = urlsplit(self.path)
        if request.path == "/api/files":
=======
        if self.path == "/api/graph":
            try:
                graph, revision = load_graph_snapshot(GRAPH_PATH)
                self._json_response(200, {"graph": graph, "revision": revision})
            except GraphEditError as error:
                self._json_response(error.status, {"success": False, "code": error.code, "error": str(error)})
            return
        if self.path == "/api/files":
>>>>>>> afb3adc (feat:them 2 thuat toan tim duong ,chinh sua giao dien ,tao gps de test)
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
<<<<<<< HEAD

        if request.path == "/api/route":
            params = parse_qs(request.query)
            try:
                destination = params["destination"][0]
                if Path(destination).name != destination or destination in (".", ".."):
                    raise ValueError("Invalid destination ID.")
                start_place = params.get("start_place", [""])[0].strip()
                if start_place:
                    if Path(start_place).name != start_place or start_place in (".", ".."):
                        raise ValueError("Invalid start place ID.")
                    route_args = [start_place, destination]
                else:
                    latitude = float(params["lat"][0])
                    longitude = float(params["lon"][0])
                    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                        raise ValueError("Latitude or longitude is out of range.")
                    route_args = [destination, "--start-coordinate", str(latitude), str(longitude)]
            except (KeyError, IndexError, ValueError) as error:
                self._send_json(400, {"error": f"Invalid route request: {error}"})
                return

            route_script = DATA_FOLDER.parent / "scripts" / "route_between_places.py"
            with ROUTE_LOCK:
                try:
                    result = subprocess.run(
                        [sys.executable, str(route_script), *route_args],
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
=======
        if self.path == "/api/places":
            try:
                rows = read_access_rows()
                places = sorted({row.get("place_id", "").strip() for row in rows
                                 if row.get("confirmed_access", "").strip().lower() == "yes"})
                self._json_response(200, {"places": places})
            except Exception as error:
                self._json_response(500, {"success": False, "error": str(error)})
            return
        if self.path == "/api/audit/access-points":
            try:
                graph = json.loads((DATA_FOLDER / "routing" / "graph.json").read_text(encoding="utf-8"))
                transformer = projection_for_graph(graph)
                incident = {node_id: [] for node_id in graph.get("nodes", {})}
                for edge in graph.get("edges", []):
                    incident[edge["from"]].append(edge["edge_id"])
                    incident[edge["to"]].append(edge["edge_id"])
                features = []
                for row in read_access_rows():
                    node_id = row.get("graph_node_candidate", "").strip()
                    if node_id not in graph.get("nodes", {}):
                        continue
                    boundary = [float(row["projected_boundary_lon"]), float(row["projected_boundary_lat"])]
                    node_coordinate = graph["nodes"][node_id]["coordinates"]
                    distance = math.dist(transformer.forward(boundary), transformer.forward(node_coordinate))
                    features.append({
                        "access_id": f"{row.get('place_id', '')}/rank{row.get('candidate_rank', '')}",
                        "place_id": row.get("place_id", ""),
                        "candidate_rank": row.get("candidate_rank", ""),
                        "node_id": node_id,
                        "node_coordinate": node_coordinate,
                        "connector_distance_m": round(distance, 2),
                        "confirmed_access": row.get("confirmed_access", ""),
                        "notes": row.get("notes", ""),
                        "edge_ids": incident[node_id],
                        "access_coordinate": boundary,
                    })
                self._json_response(200, {"access_points": features})
            except Exception as error:
                self._json_response(500, {"success": False, "error": str(error)})
            return
        super().do_GET()

    def do_POST(self):
        allowed = ("/api/route/from-gps", "/api/route/between-places", "/api/route/evaluate-gps", "/api/graph/edits")
        if self.path not in allowed:
            self._json_response(404, {"success": False, "error": "API không tồn tại."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 4_194_304 if self.path == "/api/graph/edits" else 65536
            if length <= 0 or length > limit:
                raise RoutingError("Request body không hợp lệ.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/graph/edits":
                result = save_graph_changes(payload, GRAPH_PATH, GRAPH_NODES_PATH,
                                            GRAPH_BACKUP_FOLDER, GRAPH_EDIT_LOG)
                self._json_response(200, {"success": True, **result})
            else:
                if self.path == "/api/route/evaluate-gps":
                    result = evaluate_gps_routes(payload)
                else:
                    result = route_from_gps(payload) if self.path.endswith("from-gps") else route_between_places(payload)
                self._json_response(200, result)
        except RoutingError as error:
            self._json_response(error.status, {"success": False, "code": error.code, "error": str(error)})
        except GraphEditError as error:
            self._json_response(error.status, {"success": False, "code": error.code, "error": str(error)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_response(400, {"success": False, "code": "invalid_json", "error": "Request JSON không hợp lệ."})
        except Exception as error:
            self._json_response(500, {"success": False, "code": "server_error", "error": f"Lỗi xử lý định tuyến: {error}"})

    def _json_response(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
>>>>>>> afb3adc (feat:them 2 thuat toan tim duong ,chinh sua giao dien ,tao gps de test)
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
