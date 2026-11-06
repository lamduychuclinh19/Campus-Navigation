"""GPS snapping and shortest routing over the reviewed campus graph.

All internal projection and edge measurements use a local spherical AEQD
projection centered on the mean graph-node coordinate. GeoJSON coordinates
remain WGS84 [longitude, latitude].
"""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import csv
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import heapq
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path

from building_obstacles import (
    CONFIRMED_INDOOR_PASSAGE_BUILDINGS,
    edge_building_intersection,
    filter_access_points,
    load_building_geometries,
    first_building_intersection,
)


# Ghi chú: Gán/cập nhật ROOT để lưu dữ liệu dùng ở bước tiếp theo.
ROOT = Path(__file__).resolve().parents[1]
# Ghi chú: Gán/cập nhật DATA để lưu dữ liệu dùng ở bước tiếp theo.
DATA = ROOT / "data"
# Ghi chú: Gán/cập nhật ROUTING để lưu dữ liệu dùng ở bước tiếp theo.
ROUTING = DATA / "routing"
# Ghi chú: Gán/cập nhật GRAPH_PATH để lưu dữ liệu dùng ở bước tiếp theo.
GRAPH_PATH = ROUTING / "graph.json"
# Ghi chú: Gán/cập nhật ACCESS_PATH để lưu dữ liệu dùng ở bước tiếp theo.
ACCESS_PATH = ROUTING / "place_access_candidates_multi.csv"
# Ghi chú: Gán/cập nhật MAX_SNAP_DISTANCE_METERS để lưu dữ liệu dùng ở bước tiếp theo.
MAX_SNAP_DISTANCE_METERS = 50.0
# Ghi chú: Gán/cập nhật MAX_GPS_ACCURACY_METERS để lưu dữ liệu dùng ở bước tiếp theo.
MAX_GPS_ACCURACY_METERS = 50.0
# Ghi chú: Gán/cập nhật EARTH_RADIUS_M để lưu dữ liệu dùng ở bước tiếp theo.
EARTH_RADIUS_M = 6_371_000.0
# Ghi chú: Gán/cập nhật ENDPOINT_EPSILON để lưu dữ liệu dùng ở bước tiếp theo.
ENDPOINT_EPSILON = 1e-6


# Ghi chú: Lớp RoutingError; xem các câu lệnh bên dưới để theo dõi cách xử lý.
class RoutingError(ValueError):
    # Ghi chú: Hàm __init__; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        # Ghi chú: Gán/cập nhật self.status để lưu dữ liệu dùng ở bước tiếp theo.
        self.status = status
        # Ghi chú: Gán/cập nhật self.code để lưu dữ liệu dùng ở bước tiếp theo.
        self.code = code


# Ghi chú: Hàm read_access_rows; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def read_access_rows(path=ACCESS_PATH):
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Gán/cập nhật content để lưu dữ liệu dùng ở bước tiếp theo.
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Ghi chú: Gán/cập nhật content để lưu dữ liệu dùng ở bước tiếp theo.
        content = path.read_text(encoding="cp1258")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return list(csv.DictReader(content.splitlines()))


# Ghi chú: Hàm valid_lonlat; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def valid_lonlat(lon, lat):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90


# Ghi chú: Lớp LocalAEQD; xem các câu lệnh bên dưới để theo dõi cách xử lý.
class LocalAEQD:
    """Spherical azimuthal-equidistant transform for the small campus area."""

    # Ghi chú: Hàm __init__; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def __init__(self, lon0, lat0):
        # Ghi chú: Gán/cập nhật self.lon0 để lưu dữ liệu dùng ở bước tiếp theo.
        self.lon0 = math.radians(lon0)
        # Ghi chú: Gán/cập nhật self.lat0 để lưu dữ liệu dùng ở bước tiếp theo.
        self.lat0 = math.radians(lat0)
        # Ghi chú: Gán/cập nhật self.sin_lat0 để lưu dữ liệu dùng ở bước tiếp theo.
        self.sin_lat0 = math.sin(self.lat0)
        # Ghi chú: Gán/cập nhật self.cos_lat0 để lưu dữ liệu dùng ở bước tiếp theo.
        self.cos_lat0 = math.cos(self.lat0)

    # Ghi chú: Hàm forward; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def forward(self, coordinate):
        # Ghi chú: Gán/cập nhật (lon, lat) để lưu dữ liệu dùng ở bước tiếp theo.
        lon, lat = map(float, coordinate[:2])
        # Ghi chú: Gán/cập nhật (lon, lat) để lưu dữ liệu dùng ở bước tiếp theo.
        lon, lat = math.radians(lon), math.radians(lat)
        # Ghi chú: Gán/cập nhật delta_lon để lưu dữ liệu dùng ở bước tiếp theo.
        delta_lon = lon - self.lon0
        # Ghi chú: Gán/cập nhật cos_c để lưu dữ liệu dùng ở bước tiếp theo.
        cos_c = max(-1.0, min(1.0, self.sin_lat0 * math.sin(lat) + self.cos_lat0 * math.cos(lat) * math.cos(delta_lon)))
        # Ghi chú: Gán/cập nhật c để lưu dữ liệu dùng ở bước tiếp theo.
        c = math.acos(cos_c)
        # Ghi chú: Gán/cập nhật k để lưu dữ liệu dùng ở bước tiếp theo.
        k = 1.0 if c < 1e-12 else c / math.sin(c)
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return (EARTH_RADIUS_M * k * math.cos(lat) * math.sin(delta_lon),
                EARTH_RADIUS_M * k * (self.cos_lat0 * math.sin(lat) - self.sin_lat0 * math.cos(lat) * math.cos(delta_lon)))

    # Ghi chú: Hàm inverse; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def inverse(self, point):
        # Ghi chú: Gán/cập nhật (x, y) để lưu dữ liệu dùng ở bước tiếp theo.
        x, y = point
        # Ghi chú: Gán/cập nhật rho để lưu dữ liệu dùng ở bước tiếp theo.
        rho = math.hypot(x, y)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if rho < 1e-12:
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return [math.degrees(self.lon0), math.degrees(self.lat0)]
        # Ghi chú: Gán/cập nhật c để lưu dữ liệu dùng ở bước tiếp theo.
        c = rho / EARTH_RADIUS_M
        # Ghi chú: Gán/cập nhật lat để lưu dữ liệu dùng ở bước tiếp theo.
        lat = math.asin(math.cos(c) * self.sin_lat0 + y * math.sin(c) * self.cos_lat0 / rho)
        # Ghi chú: Gán/cập nhật lon để lưu dữ liệu dùng ở bước tiếp theo.
        lon = self.lon0 + math.atan2(x * math.sin(c), rho * self.cos_lat0 * math.cos(c) - y * self.sin_lat0 * math.sin(c))
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return [math.degrees(lon), math.degrees(lat)]


# Ghi chú: Hàm projection_for_graph; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def projection_for_graph(graph):
    # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
    coords = [node["coordinates"] for node in graph.get("nodes", {}).values()]
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not coords:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Đồ thị không có node hợp lệ.", 500, "invalid_graph")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return LocalAEQD(sum(float(p[0]) for p in coords) / len(coords),
                     sum(float(p[1]) for p in coords) / len(coords))


# Ghi chú: Hàm project_point_to_segment; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def project_point_to_segment(point, start, end):
    # Ghi chú: Gán/cập nhật (dx, dy) để lưu dữ liệu dùng ở bước tiếp theo.
    dx, dy = end[0] - start[0], end[1] - start[1]
    # Ghi chú: Gán/cập nhật denom để lưu dữ liệu dùng ở bước tiếp theo.
    denom = dx * dx + dy * dy
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if denom <= 1e-18:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return (start[0], start[1]), 0.0, math.hypot(point[0] - start[0], point[1] - start[1])
    # Ghi chú: Gán/cập nhật t để lưu dữ liệu dùng ở bước tiếp theo.
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denom))
    # Ghi chú: Gán/cập nhật projected để lưu dữ liệu dùng ở bước tiếp theo.
    projected = (start[0] + t * dx, start[1] + t * dy)
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return projected, t, math.hypot(point[0] - projected[0], point[1] - projected[1])


# Ghi chú: Hàm project_to_nearest_edge; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def project_to_nearest_edge(graph, point_lonlat, transformer=None, excluded_edge_ids=None):
    # Ghi chú: Gán/cập nhật transformer để lưu dữ liệu dùng ở bước tiếp theo.
    transformer = transformer or projection_for_graph(graph)
    # Ghi chú: Gán/cập nhật point để lưu dữ liệu dùng ở bước tiếp theo.
    point = transformer.forward(point_lonlat)
    # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
    best = None
    excluded_edge_ids = excluded_edge_ids or set()
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge in graph.get("edges", []):
        if edge.get("edge_id") in excluded_edge_ids:
            continue
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
            coordinates = edge.get("coordinates") or [graph["nodes"][edge["from"]]["coordinates"], graph["nodes"][edge["to"]]["coordinates"]]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if len(coordinates) < 2 or not math.isfinite(float(edge["length_m"])) or float(edge["length_m"]) <= 0:
                continue
            # Ghi chú: Gán/cập nhật projected_coords để lưu dữ liệu dùng ở bước tiếp theo.
            projected_coords = [transformer.forward(c) for c in coordinates]
            # Ghi chú: Gán/cập nhật segment_lengths để lưu dữ liệu dùng ở bước tiếp theo.
            segment_lengths = [math.dist(a, b) for a, b in zip(projected_coords, projected_coords[1:])]
            # Ghi chú: Gán/cập nhật total_geometry để lưu dữ liệu dùng ở bước tiếp theo.
            total_geometry = sum(segment_lengths)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if total_geometry <= 1e-9:
                continue
            # Ghi chú: Gán/cập nhật offset để lưu dữ liệu dùng ở bước tiếp theo.
            offset = 0.0
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for i, (a, b) in enumerate(zip(projected_coords, projected_coords[1:])):
                # Ghi chú: Gán/cập nhật (projected, t, gap) để lưu dữ liệu dùng ở bước tiếp theo.
                projected, t, gap = project_point_to_segment(point, a, b)
                # Ghi chú: Gán/cập nhật along_geometry để lưu dữ liệu dùng ở bước tiếp theo.
                along_geometry = offset + t * segment_lengths[i]
                # Ghi chú: Gán/cập nhật fraction để lưu dữ liệu dùng ở bước tiếp theo.
                fraction = along_geometry / total_geometry
                # Ghi chú: Gán/cập nhật candidate để lưu dữ liệu dùng ở bước tiếp theo.
                candidate = (gap, edge, transformer.inverse(projected), fraction)
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if best is None or gap < best[0]:
                    # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
                    best = candidate
                offset += segment_lengths[i]
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            continue
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return best


# Ghi chú: Hàm get_places; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def get_places(graph, rows=None):
    # Ghi chú: Gán/cập nhật rows để lưu dữ liệu dùng ở bước tiếp theo.
    rows = read_access_rows() if rows is None else rows
    # Ghi chú: Gán/cập nhật places để lưu dữ liệu dùng ở bước tiếp theo.
    places = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for row in rows:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if row.get("confirmed_access", "").strip().lower() != "yes":
            continue
        # Ghi chú: Gán/cập nhật node để lưu dữ liệu dùng ở bước tiếp theo.
        node = row.get("graph_node_candidate", "").strip()
        # Ghi chú: Gán/cập nhật place để lưu dữ liệu dùng ở bước tiếp theo.
        place = row.get("place_id", "").strip()
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if node not in graph.get("nodes", {}) or not place:
            continue
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật boundary để lưu dữ liệu dùng ở bước tiếp theo.
            boundary = [float(row["projected_boundary_lon"]), float(row["projected_boundary_lat"])]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if not valid_lonlat(*boundary):
                continue
            # Ghi chú: Gán/cập nhật node_coord để lưu dữ liệu dùng ở bước tiếp theo.
            node_coord = graph["nodes"][node]["coordinates"]
            # Ghi chú: Gán/cập nhật transformer để lưu dữ liệu dùng ở bước tiếp theo.
            transformer = projection_for_graph(graph)
            # Ghi chú: Gán/cập nhật connector để lưu dữ liệu dùng ở bước tiếp theo.
            connector = math.dist(transformer.forward(boundary), transformer.forward(node_coord))
        except (KeyError, TypeError, ValueError):
            continue
        places.setdefault(place, []).append({"node": node, "boundary": boundary, "connector_m": connector})
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return places


# Ghi chú: Hàm dijkstra; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def dijkstra(adjacency, starts):
    # Ghi chú: Gán/cập nhật (distances, previous, origin) để lưu dữ liệu dùng ở bước tiếp theo.
    distances, previous, origin = {}, {}, {}
    # Ghi chú: Gán/cập nhật queue để lưu dữ liệu dùng ở bước tiếp theo.
    queue = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node, distance in starts:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if distance < distances.get(node, math.inf):
            # Ghi chú: Gán/cập nhật distances[node] để lưu dữ liệu dùng ở bước tiếp theo.
            distances[node] = distance
            # Ghi chú: Gán/cập nhật origin[node] để lưu dữ liệu dùng ở bước tiếp theo.
            origin[node] = node
            heapq.heappush(queue, (distance, node))
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    while queue:
        # Ghi chú: Gán/cập nhật (cost, node) để lưu dữ liệu dùng ở bước tiếp theo.
        cost, node = heapq.heappop(queue)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if cost != distances.get(node):
            continue
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for neighbor, weight, edge_id in adjacency.get(node, []):
            # Ghi chú: Gán/cập nhật candidate để lưu dữ liệu dùng ở bước tiếp theo.
            candidate = cost + weight
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if candidate < distances.get(neighbor, math.inf):
                # Ghi chú: Gán/cập nhật distances[neighbor] để lưu dữ liệu dùng ở bước tiếp theo.
                distances[neighbor] = candidate
                # Ghi chú: Gán/cập nhật previous[neighbor] để lưu dữ liệu dùng ở bước tiếp theo.
                previous[neighbor] = (node, edge_id)
                # Ghi chú: Gán/cập nhật origin[neighbor] để lưu dữ liệu dùng ở bước tiếp theo.
                origin[neighbor] = origin[node]
                heapq.heappush(queue, (candidate, neighbor))
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return distances, previous, origin


# Ghi chú: Hàm route_from_gps; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def route_from_gps(payload, graph=None, access_rows=None, buildings=None,
                   excluded_edge_ids=None):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not isinstance(payload, dict):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Request JSON không hợp lệ.")
    # Ghi chú: Gán/cập nhật source để lưu dữ liệu dùng ở bước tiếp theo.
    source = payload.get("location_source", "browser")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source not in ("browser", "map"):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("location_source phải là browser hoặc map.")
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Gán/cập nhật (lat, lon) để lưu dữ liệu dùng ở bước tiếp theo.
        lat, lon = float(payload["latitude"]), float(payload["longitude"])
        # Ghi chú: Gán/cập nhật raw_accuracy để lưu dữ liệu dùng ở bước tiếp theo.
        raw_accuracy = payload.get("accuracy")
        # Ghi chú: Gán/cập nhật accuracy để lưu dữ liệu dùng ở bước tiếp theo.
        accuracy = None if raw_accuracy is None else float(raw_accuracy)
    except (KeyError, TypeError, ValueError):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Cần latitude, longitude và accuracy hợp lệ (accuracy có thể null cho vị trí chọn trên bản đồ).")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not valid_lonlat(lon, lat) or (accuracy is not None and (not math.isfinite(accuracy) or accuracy < 0)):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Tọa độ GPS hoặc accuracy không hợp lệ.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source == "browser" and accuracy is None:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("GPS trình duyệt cần có accuracy.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source == "map" and accuracy is not None:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Vị trí chọn trên bản đồ không có accuracy GPS; gửi accuracy=null.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source == "browser" and accuracy > MAX_GPS_ACCURACY_METERS:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError(f"GPS chưa đủ chính xác ({accuracy:.1f} m). Hãy định vị lại; ngưỡng là {MAX_GPS_ACCURACY_METERS:g} m.", 422, "poor_accuracy")
    # Ghi chú: Gán/cập nhật destination để lưu dữ liệu dùng ở bước tiếp theo.
    destination = str(payload.get("destination_place_id", "")).strip()
    # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
    graph = graph if graph is not None else json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    buildings = load_building_geometries(DATA / "nodes") if buildings is None else buildings
    # Exclude graph edges whose full source geometry crosses a building interior.
    blocked_edges = {
        edge.get("edge_id") for edge in graph.get("edges", [])
        if edge_building_intersection(edge, graph, buildings) is not None
    }
    blocked_edges.update(excluded_edge_ids or ())
    places = filter_access_points(
        get_places(graph, read_access_rows() if access_rows is None else access_rows),
        graph, buildings,
    )
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if destination not in places:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Địa điểm đích không tồn tại hoặc chưa có cổng tiếp cận được xác nhận.", 404, "unknown_destination")
    if not places[destination]:
        raise RoutingError("All confirmed destination access connectors cross known building footprints.", 422, "blocked_access")
    # Ghi chú: Gán/cập nhật transformer để lưu dữ liệu dùng ở bước tiếp theo.
    transformer = projection_for_graph(graph)
    # Ghi chú: Gán/cập nhật nearest để lưu dữ liệu dùng ở bước tiếp theo.
    nearest = project_to_nearest_edge(graph, [lon, lat], transformer, blocked_edges)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if nearest is None:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Không tìm thấy cạnh đi bộ hợp lệ trong đồ thị.", 422, "no_valid_edge")
    # Ghi chú: Gán/cập nhật (snap_distance, edge, projected_lonlat, fraction) để lưu dữ liệu dùng ở bước tiếp theo.
    snap_distance, edge, projected_lonlat, fraction = nearest
    blocked_gps_connector = first_building_intersection(
        [[lon, lat], projected_lonlat], buildings,
    )
    if blocked_gps_connector is not None:
        raise RoutingError(
            f"GPS-to-route connector crosses building {blocked_gps_connector}.",
            422, "blocked_gps_connector",
        )
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if snap_distance > MAX_SNAP_DISTANCE_METERS:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError(f"Không có lối đi trong phạm vi {MAX_SNAP_DISTANCE_METERS:g} m (gần nhất {snap_distance:.1f} m).", 422, "too_far_to_snap")

    # Ghi chú: Gán/cập nhật virtual_id để lưu dữ liệu dùng ở bước tiếp theo.
    virtual_id = "GPS_SOURCE"
    # Ghi chú: Gán/cập nhật split_interior để lưu dữ liệu dùng ở bước tiếp theo.
    split_interior = ENDPOINT_EPSILON < fraction < 1 - ENDPOINT_EPSILON
    # Ghi chú: Gán/cập nhật adjacency để lưu dữ liệu dùng ở bước tiếp theo.
    adjacency = {node_id: [] for node_id in graph["nodes"]}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for current in graph["edges"]:
        if current.get("edge_id") in blocked_edges:
            continue
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if current["edge_id"] == edge["edge_id"] and split_interior:
            continue
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật weight để lưu dữ liệu dùng ở bước tiếp theo.
            weight = float(current["length_m"])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if weight < 0 or not math.isfinite(weight):
                continue
            adjacency[current["from"]].append((current["to"], weight, current["edge_id"]))
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if not graph.get("directed", False):
                adjacency[current["to"]].append((current["from"], weight, current["edge_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    # Ghi chú: Gán/cập nhật (u, v, length) để lưu dữ liệu dùng ở bước tiếp theo.
    u, v, length = edge["from"], edge["to"], float(edge["length_m"])
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if fraction <= ENDPOINT_EPSILON:
        # Ghi chú: Gán/cập nhật virtual_id để lưu dữ liệu dùng ở bước tiếp theo.
        virtual_id = u
        # Ghi chú: Gán/cập nhật projected_lonlat để lưu dữ liệu dùng ở bước tiếp theo.
        projected_lonlat = graph["nodes"][u]["coordinates"]
        # Ghi chú: Gán/cập nhật starts để lưu dữ liệu dùng ở bước tiếp theo.
        starts = [(virtual_id, 0.0)]
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    elif fraction >= 1 - ENDPOINT_EPSILON:
        # Ghi chú: Gán/cập nhật virtual_id để lưu dữ liệu dùng ở bước tiếp theo.
        virtual_id = v
        # Ghi chú: Gán/cập nhật projected_lonlat để lưu dữ liệu dùng ở bước tiếp theo.
        projected_lonlat = graph["nodes"][v]["coordinates"]
        # Ghi chú: Gán/cập nhật starts để lưu dữ liệu dùng ở bước tiếp theo.
        starts = [(virtual_id, 0.0)]
    else:
        # Ghi chú: Gán/cập nhật forward_weight để lưu dữ liệu dùng ở bước tiếp theo.
        forward_weight = fraction * length
        # Ghi chú: Gán/cập nhật reverse_weight để lưu dữ liệu dùng ở bước tiếp theo.
        reverse_weight = (1 - fraction) * length
        # Ghi chú: Gán/cập nhật adjacency[virtual_id] để lưu dữ liệu dùng ở bước tiếp theo.
        adjacency[virtual_id] = []
        adjacency[u].append((virtual_id, forward_weight, f"{edge['edge_id']}:gps-a"))
        adjacency[virtual_id].append((v, reverse_weight, f"{edge['edge_id']}:gps-b"))
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not graph.get("directed", False):
            adjacency[virtual_id].append((u, forward_weight, f"{edge['edge_id']}:gps-a"))
            adjacency[v].append((virtual_id, reverse_weight, f"{edge['edge_id']}:gps-b"))
        # Ghi chú: Gán/cập nhật starts để lưu dữ liệu dùng ở bước tiếp theo.
        starts = [(virtual_id, 0.0)]

    # Ghi chú: Gán/cập nhật (distances, previous, _origin) để lưu dữ liệu dùng ở bước tiếp theo.
    distances, previous, _origin = dijkstra(adjacency, starts)
    # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
    best = None
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for access in places[destination]:
        # Ghi chú: Gán/cập nhật node để lưu dữ liệu dùng ở bước tiếp theo.
        node = access["node"]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if node in distances:
            # Ghi chú: Gán/cập nhật total để lưu dữ liệu dùng ở bước tiếp theo.
            total = distances[node] + access["connector_m"]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if best is None or total < best[0]:
                # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
                best = total, access
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if best is None:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Không có đường đi từ vị trí GPS đến các cổng đã xác nhận của địa điểm.", 404, "no_route")
    # Ghi chú: Gán/cập nhật (total, target) để lưu dữ liệu dùng ở bước tiếp theo.
    total, target = best
    # Ghi chú: Gán/cập nhật route_nodes để lưu dữ liệu dùng ở bước tiếp theo.
    route_nodes = [target["node"]]
    # Ghi chú: Gán/cập nhật cursor để lưu dữ liệu dùng ở bước tiếp theo.
    cursor = target["node"]
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    while cursor != virtual_id and cursor in previous:
        # Ghi chú: Gán/cập nhật cursor để lưu dữ liệu dùng ở bước tiếp theo.
        cursor = previous[cursor][0]
        route_nodes.append(cursor)
    route_nodes.reverse()
    # Ghi chú: Gán/cập nhật route_edge_ids để lưu dữ liệu dùng ở bước tiếp theo.
    route_edge_ids = [previous[node][1] for node in route_nodes[1:] if node in previous]
    # Ghi chú: Gán/cập nhật edge_by_id để lưu dữ liệu dùng ở bước tiếp theo.
    edge_by_id = {item["edge_id"]: item for item in graph["edges"]}
    # Ghi chú: Gán/cập nhật route_coordinates để lưu dữ liệu dùng ở bước tiếp theo.
    route_coordinates = [projected_lonlat]
    # Ghi chú: Gán/cập nhật cursor để lưu dữ liệu dùng ở bước tiếp theo.
    cursor = virtual_id
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for next_node in route_nodes[1:]:
        # Ghi chú: Gán/cập nhật (prev_node, used_id) để lưu dữ liệu dùng ở bước tiếp theo.
        prev_node, used_id = previous[next_node]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if prev_node != cursor:
            break
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if used_id.endswith(":gps-a") or used_id.endswith(":gps-b"):
            # The virtual split is represented by the projected point followed by graph node.
            route_coordinates.append(graph["nodes"][next_node]["coordinates"])
        else:
            # Ghi chú: Gán/cập nhật used_edge để lưu dữ liệu dùng ở bước tiếp theo.
            used_edge = edge_by_id[used_id]
            # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
            coords = list(used_edge.get("coordinates") or [graph["nodes"][prev_node]["coordinates"], graph["nodes"][next_node]["coordinates"]])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if used_edge["from"] != prev_node:
                coords.reverse()
            route_coordinates.extend(coords[1:])
        # Ghi chú: Gán/cập nhật cursor để lưu dữ liệu dùng ở bước tiếp theo.
        cursor = next_node
    route_coordinates.append(target["boundary"])
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {
        "success": True,
        "route": {"node_ids": route_nodes, "edge_ids": route_edge_ids, "coordinates": route_coordinates, "distance_meters": round(total, 2)},
        "gps": {"latitude": lat, "longitude": lon, "accuracy_meters": accuracy, "location_source": source},
        "projection": {"latitude": projected_lonlat[1], "longitude": projected_lonlat[0],
                       "distance_meters": round(snap_distance, 2), "edge_id": edge["edge_id"], "t": fraction},
        "virtual_node": {"id": virtual_id},
        "destination": {"place_id": destination, "access_point_id": target["node"]},
    }


# Ghi chú: Hàm route_between_places; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def route_between_places(payload, graph=None, access_rows=None):
    # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
    graph = graph if graph is not None else json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    # Ghi chú: Gán/cập nhật places để lưu dữ liệu dùng ở bước tiếp theo.
    buildings = load_building_geometries(DATA / "nodes")
    places = filter_access_points(
        get_places(graph, read_access_rows() if access_rows is None else access_rows),
        graph, buildings,
    )
    # Ghi chú: Gán/cập nhật (start, destination) để lưu dữ liệu dùng ở bước tiếp theo.
    start, destination = str(payload.get("start_place_id", "")), str(payload.get("destination_place_id", ""))
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if start not in places or destination not in places:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Địa điểm xuất phát hoặc đích không tồn tại/chưa có cổng đã xác nhận.", 404, "unknown_place")
    if not places[start] or not places[destination]:
        raise RoutingError("All confirmed access connectors for the start or destination cross known building footprints.", 422, "blocked_access")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if start == destination:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Xuất phát và đích phải là hai địa điểm khác nhau.")
    # Ghi chú: Gán/cập nhật adjacency để lưu dữ liệu dùng ở bước tiếp theo.
    adjacency = {node_id: [] for node_id in graph["nodes"]}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge in graph["edges"]:
        if edge_building_intersection(edge, graph, buildings) is not None:
            continue
        # Ghi chú: Gán/cập nhật weight để lưu dữ liệu dùng ở bước tiếp theo.
        weight = float(edge["length_m"])
        adjacency[edge["from"]].append((edge["to"], weight, edge["edge_id"]))
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not graph.get("directed", False):
            adjacency[edge["to"]].append((edge["from"], weight, edge["edge_id"]))
    # Ghi chú: Gán/cập nhật starts để lưu dữ liệu dùng ở bước tiếp theo.
    starts = [(access["node"], access["connector_m"]) for access in places[start]]
    # Ghi chú: Gán/cập nhật (distances, previous, _) để lưu dữ liệu dùng ở bước tiếp theo.
    distances, previous, _ = dijkstra(adjacency, starts)
    # Ghi chú: Gán/cập nhật winner để lưu dữ liệu dùng ở bước tiếp theo.
    winner = min(((distances[a["node"]] + a["connector_m"], a) for a in places[destination] if a["node"] in distances), default=None)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if winner is None:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Không có đường giữa các cổng đã xác nhận.", 404, "no_route")
    # Ghi chú: Gán/cập nhật (total, target) để lưu dữ liệu dùng ở bước tiếp theo.
    total, target = winner
    # Ghi chú: Gán/cập nhật nodes để lưu dữ liệu dùng ở bước tiếp theo.
    nodes = [target["node"]]
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    while nodes[-1] in previous:
        nodes.append(previous[nodes[-1]][0])
    nodes.reverse()
    # Ghi chú: Gán/cập nhật edge_lookup để lưu dữ liệu dùng ở bước tiếp theo.
    edge_lookup = {edge["edge_id"]: edge for edge in graph["edges"]}
    # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
    coordinates = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node_index, node in enumerate(nodes):
        # Ghi chú: Gán/cập nhật coord để lưu dữ liệu dùng ở bước tiếp theo.
        coord = graph["nodes"][node]["coordinates"]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not coordinates:
            coordinates.append(coord)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if node_index + 1 < len(nodes):
            # Ghi chú: Gán/cập nhật next_node để lưu dữ liệu dùng ở bước tiếp theo.
            next_node = nodes[node_index + 1]
            # Ghi chú: Gán/cập nhật edge_id để lưu dữ liệu dùng ở bước tiếp theo.
            edge_id = previous[next_node][1]
            # Ghi chú: Gán/cập nhật edge để lưu dữ liệu dùng ở bước tiếp theo.
            edge = edge_lookup[edge_id]
            # Ghi chú: Gán/cập nhật edge_coords để lưu dữ liệu dùng ở bước tiếp theo.
            edge_coords = list(edge.get("coordinates") or [coord, graph["nodes"][next_node]["coordinates"]])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if edge["from"] != node:
                edge_coords.reverse()
            coordinates.extend(edge_coords[1:])
    # Ghi chú: Gán/cập nhật start_access để lưu dữ liệu dùng ở bước tiếp theo.
    start_access = min(places[start], key=lambda access: access["connector_m"] if access["node"] == nodes[0] else math.inf)
    coordinates.insert(0, start_access["boundary"])
    coordinates.append(target["boundary"])
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {"success": True, "route": {"node_ids": nodes, "coordinates": coordinates, "distance_meters": round(total, 2)}, "destination": {"place_id": destination, "access_point_id": target["node"]}}
