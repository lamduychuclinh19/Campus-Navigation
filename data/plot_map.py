"""Serve the CampusNav map and its routing/editor APIs."""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import os
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import subprocess
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import sys
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import threading
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from gps_routing import (  # noqa: E402
    RoutingError,
    projection_for_graph,
    read_access_rows,
    route_between_places,
    route_from_gps,
)
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from graph_editor import (  # noqa: E402
    GraphEditError,
    load_graph_snapshot,
    save_graph_changes,
)
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from dual_gps_routing import evaluate_gps_routes  # noqa: E402


# Ghi chú: Gán/cập nhật DATA_FOLDER để lưu dữ liệu dùng ở bước tiếp theo.
DATA_FOLDER = Path(__file__).resolve().parent
# Ghi chú: Gán/cập nhật ROUTING_FOLDER để lưu dữ liệu dùng ở bước tiếp theo.
ROUTING_FOLDER = DATA_FOLDER / "routing"
# Ghi chú: Gán/cập nhật GRAPH_PATH để lưu dữ liệu dùng ở bước tiếp theo.
GRAPH_PATH = ROUTING_FOLDER / "graph.json"
# Ghi chú: Gán/cập nhật GRAPH_NODES_PATH để lưu dữ liệu dùng ở bước tiếp theo.
GRAPH_NODES_PATH = ROUTING_FOLDER / "graph_nodes.csv"
# Ghi chú: Gán/cập nhật GRAPH_BACKUP_FOLDER để lưu dữ liệu dùng ở bước tiếp theo.
GRAPH_BACKUP_FOLDER = ROUTING_FOLDER / "backups"
# Ghi chú: Gán/cập nhật GRAPH_EDIT_LOG để lưu dữ liệu dùng ở bước tiếp theo.
GRAPH_EDIT_LOG = ROUTING_FOLDER / "graph_edit_log.jsonl"
# Ghi chú: Gán/cập nhật HOST để lưu dữ liệu dùng ở bước tiếp theo.
HOST = "127.0.0.1"
# Ghi chú: Gán/cập nhật PORT để lưu dữ liệu dùng ở bước tiếp theo.
PORT = int(os.environ.get("CAMPUSNAV_PORT", "8000"))
# Ghi chú: Gán/cập nhật ROUTE_LOCK để lưu dữ liệu dùng ở bước tiếp theo.
ROUTE_LOCK = threading.Lock()


# Ghi chú: Lớp MapRequestHandler; xem các câu lệnh bên dưới để theo dõi cách xử lý.
class MapRequestHandler(SimpleHTTPRequestHandler):
    """Serve static map assets and legacy/current CampusNav APIs."""

    # Ghi chú: Hàm do_GET; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def do_GET(self):
        # Ghi chú: Gán/cập nhật request để lưu dữ liệu dùng ở bước tiếp theo.
        request = urlsplit(self.path)
        # Ghi chú: Gán/cập nhật path để lưu dữ liệu dùng ở bước tiếp theo.
        path = request.path

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if path == "/api/files":
            # Ghi chú: Gán/cập nhật files để lưu dữ liệu dùng ở bước tiếp theo.
            files = {
                folder: sorted(item.name for item in (DATA_FOLDER / folder).glob("*.geojson"))
                for folder in ("ways", "nodes")
            }
            self._json_response(200, files)
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if path == "/api/route":
            self._legacy_route(parse_qs(request.query))
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if path == "/api/places":
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật rows để lưu dữ liệu dùng ở bước tiếp theo.
                rows = read_access_rows()
                # Ghi chú: Gán/cập nhật places để lưu dữ liệu dùng ở bước tiếp theo.
                places = sorted({
                    row.get("place_id", "").strip()
                    for row in rows
                    if row.get("confirmed_access", "").strip().lower() == "yes"
                })
                self._json_response(200, {"places": places})
            except Exception as error:
                self._json_response(500, {"success": False, "error": str(error)})
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if path == "/api/graph":
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật (graph, revision) để lưu dữ liệu dùng ở bước tiếp theo.
                graph, revision = load_graph_snapshot(GRAPH_PATH)
                self._json_response(200, {"graph": graph, "revision": revision})
            except GraphEditError as error:
                self._json_response(error.status, {
                    "success": False, "code": error.code, "error": str(error)
                })
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if path == "/api/audit/access-points":
            self._access_point_audit()
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return

        super().do_GET()

    # Ghi chú: Hàm do_POST; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def do_POST(self):
        # Ghi chú: Gán/cập nhật path để lưu dữ liệu dùng ở bước tiếp theo.
        path = urlsplit(self.path).path
        # Ghi chú: Gán/cập nhật allowed để lưu dữ liệu dùng ở bước tiếp theo.
        allowed = {
            "/api/route/from-gps",
            "/api/route/between-places",
            "/api/route/evaluate-gps",
            "/api/graph/edits",
        }
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if path not in allowed:
            self._json_response(404, {"success": False, "error": "API không tồn tại."})
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return

        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật length để lưu dữ liệu dùng ở bước tiếp theo.
            length = int(self.headers.get("Content-Length", "0"))
            # Ghi chú: Gán/cập nhật limit để lưu dữ liệu dùng ở bước tiếp theo.
            limit = 4_194_304 if path == "/api/graph/edits" else 65_536
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if length <= 0 or length > limit:
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise RoutingError("Request body không hợp lệ.")
            # Ghi chú: Gán/cập nhật payload để lưu dữ liệu dùng ở bước tiếp theo.
            payload = json.loads(self.rfile.read(length).decode("utf-8"))

            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if path == "/api/graph/edits":
                # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
                result = save_graph_changes(
                    payload, GRAPH_PATH, GRAPH_NODES_PATH,
                    GRAPH_BACKUP_FOLDER, GRAPH_EDIT_LOG,
                )
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            elif path == "/api/route/evaluate-gps":
                # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
                result = evaluate_gps_routes(payload)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            elif path == "/api/route/from-gps":
                # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
                result = route_from_gps(payload)
            else:
                # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
                result = route_between_places(payload)
            self._json_response(200, {"success": True, **result} if path == "/api/graph/edits" else result)
        except RoutingError as error:
            self._json_response(error.status, {
                "success": False, "code": error.code, "error": str(error)
            })
        except GraphEditError as error:
            self._json_response(error.status, {
                "success": False, "code": error.code, "error": str(error)
            })
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_response(400, {
                "success": False, "code": "invalid_json", "error": "Request JSON không hợp lệ."
            })
        except Exception as error:
            self._json_response(500, {
                "success": False, "code": "server_error",
                "error": f"Lỗi xử lý định tuyến: {error}",
            })

    # Ghi chú: Hàm _legacy_route; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def _legacy_route(self, params):
        """Serve the pre-JSON GET route endpoint without changing its schema."""
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật destination để lưu dữ liệu dùng ở bước tiếp theo.
            destination = params["destination"][0]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if Path(destination).name != destination or destination in (".", ".."):
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise ValueError("Invalid destination ID.")
            # Ghi chú: Gán/cập nhật start_place để lưu dữ liệu dùng ở bước tiếp theo.
            start_place = params.get("start_place", [""])[0].strip()
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if start_place:
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if Path(start_place).name != start_place or start_place in (".", ".."):
                    # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                    raise ValueError("Invalid start place ID.")
                # Ghi chú: Gán/cập nhật route_args để lưu dữ liệu dùng ở bước tiếp theo.
                route_args = [start_place, destination]
            else:
                # Ghi chú: Gán/cập nhật latitude để lưu dữ liệu dùng ở bước tiếp theo.
                latitude = float(params["lat"][0])
                # Ghi chú: Gán/cập nhật longitude để lưu dữ liệu dùng ở bước tiếp theo.
                longitude = float(params["lon"][0])
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                    # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                    raise ValueError("Latitude or longitude is out of range.")
                # Ghi chú: Gán/cập nhật route_args để lưu dữ liệu dùng ở bước tiếp theo.
                route_args = [destination, "--start-coordinate", str(latitude), str(longitude)]
        except (KeyError, IndexError, ValueError) as error:
            self._json_response(400, {"error": f"Invalid route request: {error}"})
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return

        # Ghi chú: Gán/cập nhật route_script để lưu dữ liệu dùng ở bước tiếp theo.
        route_script = DATA_FOLDER.parent / "scripts" / "route_between_places.py"
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with ROUTE_LOCK:
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
                result = subprocess.run(
                    [sys.executable, str(route_script), *route_args],
                    cwd=DATA_FOLDER.parent,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                self._json_response(504, {
                    "error": "Route calculation took too long; please try again."
                })
                # Ghi chú: Trả kết quả hiện tại về nơi gọi.
                return
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if result.returncode != 0:
                self._json_response(422, {
                    "error": result.stdout.strip() or result.stderr.strip() or "No route found."
                })
                # Ghi chú: Trả kết quả hiện tại về nơi gọi.
                return
            # Ghi chú: Gán/cập nhật route_path để lưu dữ liệu dùng ở bước tiếp theo.
            route_path = ROUTING_FOLDER / "route_result.geojson"
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật route để lưu dữ liệu dùng ở bước tiếp theo.
                route = json.loads(route_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                self._json_response(500, {"error": f"Could not read route result: {error}"})
                # Ghi chú: Trả kết quả hiện tại về nơi gọi.
                return
        self._json_response(200, {"route": route, "summary": result.stdout.strip()})

    # Ghi chú: Hàm _access_point_audit; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def _access_point_audit(self):
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
            graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
            # Ghi chú: Gán/cập nhật transformer để lưu dữ liệu dùng ở bước tiếp theo.
            transformer = projection_for_graph(graph)
            # Ghi chú: Gán/cập nhật incident để lưu dữ liệu dùng ở bước tiếp theo.
            incident = {node_id: [] for node_id in graph.get("nodes", {})}
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for edge in graph.get("edges", []):
                incident[edge["from"]].append(edge["edge_id"])
                incident[edge["to"]].append(edge["edge_id"])
            # Ghi chú: Gán/cập nhật features để lưu dữ liệu dùng ở bước tiếp theo.
            features = []
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for row in read_access_rows():
                # Ghi chú: Gán/cập nhật node_id để lưu dữ liệu dùng ở bước tiếp theo.
                node_id = row.get("graph_node_candidate", "").strip()
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if node_id not in graph.get("nodes", {}):
                    continue
                # Ghi chú: Gán/cập nhật boundary để lưu dữ liệu dùng ở bước tiếp theo.
                boundary = [
                    float(row["projected_boundary_lon"]),
                    float(row["projected_boundary_lat"]),
                ]
                # Ghi chú: Gán/cập nhật node_coordinate để lưu dữ liệu dùng ở bước tiếp theo.
                node_coordinate = graph["nodes"][node_id]["coordinates"]
                # Ghi chú: Gán/cập nhật distance để lưu dữ liệu dùng ở bước tiếp theo.
                distance = math.dist(
                    transformer.forward(boundary), transformer.forward(node_coordinate)
                )
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

    # Ghi chú: Hàm _json_response; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def _json_response(self, status, value):
        # Ghi chú: Gán/cập nhật body để lưu dữ liệu dùng ở bước tiếp theo.
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Ghi chú: Hàm _send_json; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def _send_json(self, status, payload):
        self._json_response(status, payload)


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for stream in (sys.stdout, sys.stderr):
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    os.chdir(DATA_FOLDER)
    # Ghi chú: Gán/cập nhật server để lưu dữ liệu dùng ở bước tiếp theo.
    server = ThreadingHTTPServer((HOST, PORT), MapRequestHandler)
    print(f"Mở bản đồ tại: http://{HOST}:{PORT}/map.html")
    print("Nhấn Ctrl+C để dừng web server.")
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng web server.")
    finally:
        server.server_close()
