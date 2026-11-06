#!/usr/bin/env python3
"""Build the Dijkstra graph from GeoJSON and user-reviewed connections.

Run: python scripts/build_routing_graph.py
Requires all rows in nearby_endpoints.csv and way_intersections.csv to be
marked yes/no. Source GeoJSON and review CSVs are never modified.
"""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import csv
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path


# Ghi chú: Gán/cập nhật ROOT để lưu dữ liệu dùng ở bước tiếp theo.
ROOT = Path(__file__).resolve().parents[1]
# Ghi chú: Gán/cập nhật DATA để lưu dữ liệu dùng ở bước tiếp theo.
DATA = ROOT / "data"
# Ghi chú: Gán/cập nhật WAYS để lưu dữ liệu dùng ở bước tiếp theo.
WAYS = DATA / "ways"
# Ghi chú: Gán/cập nhật ROUTING để lưu dữ liệu dùng ở bước tiếp theo.
ROUTING = DATA / "routing"
# Ghi chú: Gán/cập nhật ENDPOINTS_CSV để lưu dữ liệu dùng ở bước tiếp theo.
ENDPOINTS_CSV = ROUTING / "nearby_endpoints.csv"
# Ghi chú: Gán/cập nhật INTERSECTIONS_CSV để lưu dữ liệu dùng ở bước tiếp theo.
INTERSECTIONS_CSV = ROUTING / "way_intersections.csv"
# Ghi chú: Gán/cập nhật GRAPH_JSON để lưu dữ liệu dùng ở bước tiếp theo.
GRAPH_JSON = ROUTING / "graph.json"
# Ghi chú: Gán/cập nhật REPORT_CSV để lưu dữ liệu dùng ở bước tiếp theo.
REPORT_CSV = ROUTING / "graph_nodes.csv"
# Ghi chú: Gán/cập nhật ACCESS_CSV để lưu dữ liệu dùng ở bước tiếp theo.
ACCESS_CSV = ROUTING / "place_access_candidates_multi.csv"
# Ghi chú: Gán/cập nhật EARTH_RADIUS_M để lưu dữ liệu dùng ở bước tiếp theo.
EARTH_RADIUS_M = 6_371_000.0


# Ghi chú: Hàm distance_m; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def distance_m(a, b):
    # Ghi chú: Gán/cập nhật (lon1, lat1) để lưu dữ liệu dùng ở bước tiếp theo.
    lon1, lat1 = map(math.radians, a[:2])
    # Ghi chú: Gán/cập nhật (lon2, lat2) để lưu dữ liệu dùng ở bước tiếp theo.
    lon2, lat2 = map(math.radians, b[:2])
    # Ghi chú: Gán/cập nhật (dlat, dlon) để lưu dữ liệu dùng ở bước tiếp theo.
    dlat, dlon = lat2 - lat1, lon2 - lon1
    # Ghi chú: Gán/cập nhật h để lưu dữ liệu dùng ở bước tiếp theo.
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


# Ghi chú: Hàm line_length_m; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def line_length_m(coords):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return sum(distance_m(a, b) for a, b in zip(coords, coords[1:]))


# Ghi chú: Hàm local_xy; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def local_xy(point, origin_lat):
    # Ghi chú: Gán/cập nhật (lon, lat) để lưu dữ liệu dùng ở bước tiếp theo.
    lon, lat = point[:2]
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return (math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat)),
            math.radians(lat) * EARTH_RADIUS_M)


# Ghi chú: Hàm project_onto_line; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def project_onto_line(point, coords):
    """Return along-line distance and snapped point for a coordinate."""
    # Ghi chú: Gán/cập nhật origin_lat để lưu dữ liệu dùng ở bước tiếp theo.
    origin_lat = sum(float(item[1]) for item in coords) / len(coords)
    # Ghi chú: Gán/cập nhật p để lưu dữ liệu dùng ở bước tiếp theo.
    p = local_xy(point, origin_lat)
    # Ghi chú: Gán/cập nhật cumulative để lưu dữ liệu dùng ở bước tiếp theo.
    cumulative = 0.0
    # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
    best = None
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for index, (a_geo, b_geo) in enumerate(zip(coords, coords[1:])):
        # Ghi chú: Gán/cập nhật (a, b) để lưu dữ liệu dùng ở bước tiếp theo.
        a, b = local_xy(a_geo, origin_lat), local_xy(b_geo, origin_lat)
        # Ghi chú: Gán/cập nhật (dx, dy) để lưu dữ liệu dùng ở bước tiếp theo.
        dx, dy = b[0] - a[0], b[1] - a[1]
        # Ghi chú: Gán/cập nhật segment_length để lưu dữ liệu dùng ở bước tiếp theo.
        segment_length = math.hypot(dx, dy)
        # Ghi chú: Gán/cập nhật denom để lưu dữ liệu dùng ở bước tiếp theo.
        denom = dx * dx + dy * dy
        # Ghi chú: Gán/cập nhật t để lưu dữ liệu dùng ở bước tiếp theo.
        t = 0.0 if denom == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
        # Ghi chú: Gán/cập nhật snapped_xy để lưu dữ liệu dùng ở bước tiếp theo.
        snapped_xy = (a[0] + t * dx, a[1] + t * dy)
        # Ghi chú: Gán/cập nhật gap để lưu dữ liệu dùng ở bước tiếp theo.
        gap = math.hypot(p[0] - snapped_xy[0], p[1] - snapped_xy[1])
        # Ghi chú: Gán/cập nhật snapped để lưu dữ liệu dùng ở bước tiếp theo.
        snapped = [
            math.degrees(snapped_xy[0] / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat)))),
            math.degrees(snapped_xy[1] / EARTH_RADIUS_M),
        ]
        # Ghi chú: Gán/cập nhật candidate để lưu dữ liệu dùng ở bước tiếp theo.
        candidate = (gap, cumulative + segment_length * t, snapped)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if best is None or candidate[0] < best[0]:
            # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
            best = candidate
        cumulative += segment_length
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return best[1], best[2], best[0]


# Ghi chú: Lớp UnionFind; xem các câu lệnh bên dưới để theo dõi cách xử lý.
class UnionFind:
    # Ghi chú: Hàm __init__; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def __init__(self):
        # Ghi chú: Gán/cập nhật self.parent để lưu dữ liệu dùng ở bước tiếp theo.
        self.parent = {}

    # Ghi chú: Hàm find; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def find(self, item):
        self.parent.setdefault(item, item)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if self.parent[item] != item:
            # Ghi chú: Gán/cập nhật self.parent[item] để lưu dữ liệu dùng ở bước tiếp theo.
            self.parent[item] = self.find(self.parent[item])
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return self.parent[item]

    # Ghi chú: Hàm union; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def union(self, a, b):
        # Ghi chú: Gán/cập nhật (ra, rb) để lưu dữ liệu dùng ở bước tiếp theo.
        ra, rb = self.find(a), self.find(b)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if ra != rb:
            # Ghi chú: Gán/cập nhật self.parent[rb] để lưu dữ liệu dùng ở bước tiếp theo.
            self.parent[rb] = ra


# Ghi chú: Hàm edge_endpoint_key; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def edge_endpoint_key(way_id, role):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return f"{way_id}:{role}"


# Ghi chú: Hàm read_review; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def read_review(path, label):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not path.exists():
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise SystemExit(f"Missing {label}: {path}")
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        # Ghi chú: Gán/cập nhật rows để lưu dữ liệu dùng ở bước tiếp theo.
        rows = list(csv.DictReader(file))
    # Ghi chú: Gán/cập nhật unresolved để lưu dữ liệu dùng ở bước tiếp theo.
    unresolved = [str(index + 2) for index, row in enumerate(rows)
                  if row.get("confirmed_connected", "").strip().lower() not in ("yes", "no", "y", "n")]
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if unresolved:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise SystemExit(f"Mark every {label} row yes/no first. Unreviewed CSV lines: {', '.join(unresolved)}")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return rows


# Ghi chú: Hàm main; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def main():
    # Ghi chú: Gán/cập nhật old_graph để lưu dữ liệu dùng ở bước tiếp theo.
    old_graph = {}
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if GRAPH_JSON.exists():
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật old_graph để lưu dữ liệu dùng ở bước tiếp theo.
            old_graph = json.loads(GRAPH_JSON.read_text(encoding="utf-8")).get("nodes", {})
        except (OSError, json.JSONDecodeError):
            # Ghi chú: Gán/cập nhật old_graph để lưu dữ liệu dùng ở bước tiếp theo.
            old_graph = {}
    # Ghi chú: Gán/cập nhật ways để lưu dữ liệu dùng ở bước tiếp theo.
    ways = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for path in sorted(WAYS.glob("*.geojson")):
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật data để lưu dữ liệu dùng ở bước tiếp theo.
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skip {path.name}: {error}")
            continue
        # Ghi chú: Gán/cập nhật line_number để lưu dữ liệu dùng ở bước tiếp theo.
        line_number = 0
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for feature in data.get("features", []):
            # Ghi chú: Gán/cập nhật geometry để lưu dữ liệu dùng ở bước tiếp theo.
            geometry = feature.get("geometry") or {}
            # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
            coords = geometry.get("coordinates") or []
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if geometry.get("type") != "LineString" or len(coords) < 2:
                continue
            line_number += 1
            # Ghi chú: Gán/cập nhật way_id để lưu dữ liệu dùng ở bước tiếp theo.
            way_id = path.stem if line_number == 1 else f"{path.stem}_{line_number}"
            # Ghi chú: Gán/cập nhật ways[way_id] để lưu dữ liệu dùng ở bước tiếp theo.
            ways[way_id] = {"file": path.name, "coords": [[float(p[0]), float(p[1])] for p in coords]}

    # Ghi chú: Gán/cập nhật endpoint_rows để lưu dữ liệu dùng ở bước tiếp theo.
    endpoint_rows = read_review(ENDPOINTS_CSV, "nearby endpoint")
    # Ghi chú: Gán/cập nhật intersection_rows để lưu dữ liệu dùng ở bước tiếp theo.
    intersection_rows = read_review(INTERSECTIONS_CSV, "way intersection")
    # Ghi chú: Gán/cập nhật uf để lưu dữ liệu dùng ở bước tiếp theo.
    uf = UnionFind()
    # Ghi chú: Gán/cập nhật positions để lưu dữ liệu dùng ở bước tiếp theo.
    positions = {}
    # Ghi chú: Gán/cập nhật split_points để lưu dữ liệu dùng ở bước tiếp theo.
    split_points = {way_id: [] for way_id in ways}

    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for way_id, way in ways.items():
        # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
        coords = way["coords"]
        # Ghi chú: Gán/cập nhật (start_key, end_key) để lưu dữ liệu dùng ở bước tiếp theo.
        start_key, end_key = edge_endpoint_key(way_id, "start"), edge_endpoint_key(way_id, "end")
        # Ghi chú: Gán/cập nhật (positions[start_key], positions[end_key]) để lưu dữ liệu dùng ở bước tiếp theo.
        positions[start_key], positions[end_key] = coords[0], coords[-1]
        uf.find(start_key)
        uf.find(end_key)

    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for row in endpoint_rows:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if row["confirmed_connected"].strip().lower() not in ("yes", "y"):
            continue
        # Ghi chú: Gán/cập nhật first để lưu dữ liệu dùng ở bước tiếp theo.
        first = edge_endpoint_key(row["edge_1"], row["endpoint_1"])
        # Ghi chú: Gán/cập nhật second để lưu dữ liệu dùng ở bước tiếp theo.
        second = edge_endpoint_key(row["edge_2"], row["endpoint_2"])
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if first not in positions or second not in positions:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise SystemExit(f"Endpoint reference not found: {first} / {second}")
        uf.union(first, second)

    # Ghi chú: Gán/cập nhật accepted_intersections để lưu dữ liệu dùng ở bước tiếp theo.
    accepted_intersections = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for row_index, row in enumerate(intersection_rows, start=2):
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if row["confirmed_connected"].strip().lower() not in ("yes", "y"):
            continue
        # Ghi chú: Gán/cập nhật (first_id, second_id) để lưu dữ liệu dùng ở bước tiếp theo.
        first_id, second_id = row["way_1"], row["way_2"]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if first_id not in ways or second_id not in ways:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise SystemExit(f"Way reference missing on intersection CSV line {row_index}: {first_id}/{second_id}")
        # Ghi chú: Gán/cập nhật point để lưu dữ liệu dùng ở bước tiếp theo.
        point = [float(row["longitude"]), float(row["latitude"])]
        # Ghi chú: Gán/cập nhật token để lưu dữ liệu dùng ở bước tiếp theo.
        token = f"IX{row_index:03d}"
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for way_id in (first_id, second_id):
            # Ghi chú: Gán/cập nhật (offset, snapped, gap) để lưu dữ liệu dùng ở bước tiếp theo.
            offset, snapped, gap = project_onto_line(point, ways[way_id]["coords"])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if gap > 2.0:
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise SystemExit(f"Intersection line {row_index}: {way_id} is {gap:.2f} m from the reviewed point")
            # Ghi chú: Gán/cập nhật total để lưu dữ liệu dùng ở bước tiếp theo.
            total = line_length_m(ways[way_id]["coords"])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if offset <= 0.02:
                uf.union(token, edge_endpoint_key(way_id, "start"))
                # Ghi chú: Gán/cập nhật split_key để lưu dữ liệu dùng ở bước tiếp theo.
                split_key = edge_endpoint_key(way_id, "start")
                # Ghi chú: Gán/cập nhật snapped để lưu dữ liệu dùng ở bước tiếp theo.
                snapped = ways[way_id]["coords"][0]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            elif total - offset <= 0.02:
                uf.union(token, edge_endpoint_key(way_id, "end"))
                # Ghi chú: Gán/cập nhật split_key để lưu dữ liệu dùng ở bước tiếp theo.
                split_key = edge_endpoint_key(way_id, "end")
                # Ghi chú: Gán/cập nhật snapped để lưu dữ liệu dùng ở bước tiếp theo.
                snapped = ways[way_id]["coords"][-1]
            else:
                # Ghi chú: Gán/cập nhật split_key để lưu dữ liệu dùng ở bước tiếp theo.
                split_key = token
            # Ghi chú: Gán/cập nhật positions[token] để lưu dữ liệu dùng ở bước tiếp theo.
            positions[token] = point
            # Ghi chú: Gán/cập nhật positions[split_key] để lưu dữ liệu dùng ở bước tiếp theo.
            positions[split_key] = snapped
            split_points[way_id].append((offset, split_key, snapped))
        accepted_intersections.append((token, point))

    # Merge approved candidate points that represent the same physical junction.
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for index, (first_token, first_point) in enumerate(accepted_intersections):
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for second_token, second_point in accepted_intersections[index + 1:]:
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if distance_m(first_point, second_point) <= 0.5:
                uf.union(first_token, second_token)

    # Keep graph coordinates for every encountered vertex and approved split.
    # Ghi chú: Gán/cập nhật way_vertices để lưu dữ liệu dùng ở bước tiếp theo.
    way_vertices = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for way_id, way in ways.items():
        # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
        coords = way["coords"]
        # Ghi chú: Gán/cập nhật cumulative để lưu dữ liệu dùng ở bước tiếp theo.
        cumulative = [0.0]
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for a, b in zip(coords, coords[1:]):
            cumulative.append(cumulative[-1] + distance_m(a, b))
        # Ghi chú: Gán/cập nhật vertices để lưu dữ liệu dùng ở bước tiếp theo.
        vertices = []
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for index, point in enumerate(coords):
            # Ghi chú: Gán/cập nhật key để lưu dữ liệu dùng ở bước tiếp theo.
            key = edge_endpoint_key(way_id, "start") if index == 0 else (
                edge_endpoint_key(way_id, "end") if index == len(coords) - 1 else f"{way_id}:v{index}")
            # Ghi chú: Gán/cập nhật positions[key] để lưu dữ liệu dùng ở bước tiếp theo.
            positions[key] = point
            uf.find(key)
            vertices.append((cumulative[index], key, point))
        vertices.extend(split_points[way_id])
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for _offset, key, _point in vertices:
            uf.find(key)
        vertices.sort(key=lambda item: item[0])
        # Collapse duplicate vertices on the same way while retaining the
        # approved intersection token as the node identity.
        # Ghi chú: Gán/cập nhật compact để lưu dữ liệu dùng ở bước tiếp theo.
        compact = []
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for vertex in vertices:
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if compact and abs(vertex[0] - compact[-1][0]) < 0.01:
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if vertex[1].startswith("IX"):
                    uf.union(vertex[1], compact[-1][1])
                    # Ghi chú: Gán/cập nhật compact[-1] để lưu dữ liệu dùng ở bước tiếp theo.
                    compact[-1] = vertex
                continue
            compact.append(vertex)
        # Ghi chú: Gán/cập nhật way_vertices[way_id] để lưu dữ liệu dùng ở bước tiếp theo.
        way_vertices[way_id] = compact

    # Ghi chú: Gán/cập nhật groups để lưu dữ liệu dùng ở bước tiếp theo.
    groups = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for key in uf.parent:
        groups.setdefault(uf.find(key), []).append(key)
    # Ghi chú: Gán/cập nhật ordered_groups để lưu dữ liệu dùng ở bước tiếp theo.
    ordered_groups = sorted(groups.items(), key=lambda item: min(item[1]))
    # Ghi chú: Gán/cập nhật old_refs để lưu dữ liệu dùng ở bước tiếp theo.
    old_refs = {node_id: set(node.get("endpoint_refs", [])) for node_id, node in old_graph.items()}
    # Ghi chú: Gán/cập nhật used_old_ids để lưu dữ liệu dùng ở bước tiếp theo.
    used_old_ids = set()
    # Ghi chú: Gán/cập nhật node_id_by_root để lưu dữ liệu dùng ở bước tiếp theo.
    node_id_by_root = {}
    # Ghi chú: Gán/cập nhật nodes để lưu dữ liệu dùng ở bước tiếp theo.
    nodes = {}
    # Ghi chú: Gán/cập nhật next_node_number để lưu dữ liệu dùng ở bước tiếp theo.
    next_node_number = max((int(node_id[1:]) for node_id in old_graph
                            if node_id.startswith("N") and node_id[1:].isdigit()), default=0) + 1
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for root, members in ordered_groups:
        # Ghi chú: Gán/cập nhật member_set để lưu dữ liệu dùng ở bước tiếp theo.
        member_set = set(members)
        # Ghi chú: Gán/cập nhật matching_old_ids để lưu dữ liệu dùng ở bước tiếp theo.
        matching_old_ids = sorted(node_id for node_id, refs in old_refs.items() if refs & member_set)
        # Ghi chú: Gán/cập nhật node_id để lưu dữ liệu dùng ở bước tiếp theo.
        node_id = next((old_id for old_id in matching_old_ids if old_id not in used_old_ids), None)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if node_id is None:
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            while f"N{next_node_number:03d}" in used_old_ids or f"N{next_node_number:03d}" in old_graph:
                next_node_number += 1
            # Ghi chú: Gán/cập nhật node_id để lưu dữ liệu dùng ở bước tiếp theo.
            node_id = f"N{next_node_number:03d}"
            next_node_number += 1
        used_old_ids.add(node_id)
        # Ghi chú: Gán/cập nhật node_id_by_root[root] để lưu dữ liệu dùng ở bước tiếp theo.
        node_id_by_root[root] = node_id
        # Ghi chú: Gán/cập nhật known_coords để lưu dữ liệu dùng ở bước tiếp theo.
        known_coords = [positions[key] for key in members if key in positions]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not known_coords:
            continue
        # Ghi chú: Gán/cập nhật nodes[node_id] để lưu dữ liệu dùng ở bước tiếp theo.
        nodes[node_id] = {
            "coordinates": [round(sum(p[0] for p in known_coords) / len(known_coords), 7),
                            round(sum(p[1] for p in known_coords) / len(known_coords), 7)],
            "endpoint_refs": sorted(members),
        }

    # Ghi chú: Gán/cập nhật edges để lưu dữ liệu dùng ở bước tiếp theo.
    edges = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for way_id, vertices in way_vertices.items():
        # Ghi chú: Gán/cập nhật part để lưu dữ liệu dùng ở bước tiếp theo.
        part = 0
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for first, second in zip(vertices, vertices[1:]):
            # Ghi chú: Gán/cập nhật start_node để lưu dữ liệu dùng ở bước tiếp theo.
            start_node = node_id_by_root[uf.find(first[1])]
            # Ghi chú: Gán/cập nhật end_node để lưu dữ liệu dùng ở bước tiếp theo.
            end_node = node_id_by_root[uf.find(second[1])]
            # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
            coords = [first[2], second[2]]
            # Ghi chú: Gán/cập nhật weight để lưu dữ liệu dùng ở bước tiếp theo.
            weight = round(line_length_m(coords), 2)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if weight <= 0:
                continue
            part += 1
            edges.append({
                "edge_id": f"{way_id}_part{part:02d}", "way_id": way_id,
                "file": ways[way_id]["file"], "from": start_node, "to": end_node,
                "length_m": weight, "coordinates": coords,
            })

    # Ghi chú: Gán/cập nhật adjacency để lưu dữ liệu dùng ở bước tiếp theo.
    adjacency = {node_id: [] for node_id in nodes}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge in edges:
        adjacency[edge["from"]].append((edge["to"], edge["length_m"]))
        adjacency[edge["to"]].append((edge["from"], edge["length_m"]))
    # Map old IDs to current nodes so already-reviewed place access rows keep
    # pointing to the same physical gates after intersections are inserted.
    # Ghi chú: Gán/cập nhật old_to_new để lưu dữ liệu dùng ở bước tiếp theo.
    old_to_new = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for old_id, refs in old_refs.items():
        # Ghi chú: Gán/cập nhật candidates để lưu dữ liệu dùng ở bước tiếp theo.
        candidates = [(len(refs & set(members)), root) for root, members in groups.items() if refs & set(members)]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if candidates:
            # Ghi chú: Gán/cập nhật (_count, root) để lưu dữ liệu dùng ở bước tiếp theo.
            _count, root = max(candidates)
            # Ghi chú: Gán/cập nhật old_to_new[old_id] để lưu dữ liệu dùng ở bước tiếp theo.
            old_to_new[old_id] = node_id_by_root[root]

    # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
    graph = {"directed": False, "nodes": nodes, "edges": edges}
    GRAPH_JSON.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ghi chú: Gán/cập nhật report_rows để lưu dữ liệu dùng ở bước tiếp theo.
    report_rows = []
    # Ghi chú: Gán/cập nhật visited để lưu dữ liệu dùng ở bước tiếp theo.
    visited = set()
    # Ghi chú: Gán/cập nhật component_id để lưu dữ liệu dùng ở bước tiếp theo.
    component_id = 0
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node_id in adjacency:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if node_id in visited:
            continue
        component_id += 1
        # Ghi chú: Gán/cập nhật stack để lưu dữ liệu dùng ở bước tiếp theo.
        stack = [node_id]
        visited.add(node_id)
        # Ghi chú: Gán/cập nhật component_nodes để lưu dữ liệu dùng ở bước tiếp theo.
        component_nodes = []
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        while stack:
            # Ghi chú: Gán/cập nhật current để lưu dữ liệu dùng ở bước tiếp theo.
            current = stack.pop()
            component_nodes.append(current)
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for neighbor, _ in adjacency[current]:
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for reachable in component_nodes:
            report_rows.append({"node_id": reachable, "component": component_id,
                                "longitude": nodes[reachable]["coordinates"][0],
                                "latitude": nodes[reachable]["coordinates"][1],
                                "degree": len(adjacency[reachable])})

    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with REPORT_CSV.open("w", newline="", encoding="utf-8-sig") as file:
        # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
        writer = csv.DictWriter(file, fieldnames=["node_id", "component", "longitude", "latitude", "degree"])
        writer.writeheader()
        writer.writerows(report_rows)

    # Refresh gate rows with remapped IDs/components while preserving the
    # user's yes/no decisions. If multiple old junctions merged, a yes wins.
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if ACCESS_CSV.exists():
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật old_text để lưu dữ liệu dùng ở bước tiếp theo.
            old_text = ACCESS_CSV.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            # Ghi chú: Gán/cập nhật old_text để lưu dữ liệu dùng ở bước tiếp theo.
            old_text = ACCESS_CSV.read_text(encoding="cp1258")
        # Ghi chú: Gán/cập nhật access_rows để lưu dữ liệu dùng ở bước tiếp theo.
        access_rows = list(csv.DictReader(old_text.splitlines()))
        # Ghi chú: Gán/cập nhật component_by_node để lưu dữ liệu dùng ở bước tiếp theo.
        component_by_node = {row["node_id"]: row["component"] for row in report_rows}
        # Ghi chú: Gán/cập nhật refreshed để lưu dữ liệu dùng ở bước tiếp theo.
        refreshed = {}
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for row in access_rows:
            # Ghi chú: Gán/cập nhật old_id để lưu dữ liệu dùng ở bước tiếp theo.
            old_id = row.get("graph_node_candidate", "")
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật previous_coord để lưu dữ liệu dùng ở bước tiếp theo.
                previous_coord = [float(row["graph_node_lon"]), float(row["graph_node_lat"])]
            except (KeyError, TypeError, ValueError):
                # Ghi chú: Gán/cập nhật previous_coord để lưu dữ liệu dùng ở bước tiếp theo.
                previous_coord = None
            # Ghi chú: Gán/cập nhật new_id để lưu dữ liệu dùng ở bước tiếp theo.
            new_id = old_to_new.get(old_id, old_id)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if previous_coord:
                # Ghi chú: Gán/cập nhật nearest_id để lưu dữ liệu dùng ở bước tiếp theo.
                nearest_id = min(nodes, key=lambda node_id: distance_m(previous_coord, nodes[node_id]["coordinates"]))
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if distance_m(previous_coord, nodes[nearest_id]["coordinates"]) <= 2.0:
                    # Ghi chú: Gán/cập nhật new_id để lưu dữ liệu dùng ở bước tiếp theo.
                    new_id = nearest_id
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if new_id not in nodes:
                continue
            # Ghi chú: Gán/cập nhật row['graph_node_candidate'] để lưu dữ liệu dùng ở bước tiếp theo.
            row["graph_node_candidate"] = new_id
            # Ghi chú: Gán/cập nhật row['component'] để lưu dữ liệu dùng ở bước tiếp theo.
            row["component"] = component_by_node.get(new_id, "")
            # Ghi chú: Gán/cập nhật coord để lưu dữ liệu dùng ở bước tiếp theo.
            coord = nodes[new_id]["coordinates"]
            # Ghi chú: Gán/cập nhật (row['graph_node_lon'], row['graph_node_lat']) để lưu dữ liệu dùng ở bước tiếp theo.
            row["graph_node_lon"], row["graph_node_lat"] = coord
            # Ghi chú: Gán/cập nhật boundary để lưu dữ liệu dùng ở bước tiếp theo.
            boundary = [float(row["projected_boundary_lon"]), float(row["projected_boundary_lat"])]
            # Ghi chú: Gán/cập nhật row['distance_to_polygon_m'] để lưu dữ liệu dùng ở bước tiếp theo.
            row["distance_to_polygon_m"] = round(distance_m(coord, boundary), 2)
            # Ghi chú: Gán/cập nhật key để lưu dữ liệu dùng ở bước tiếp theo.
            key = (row.get("place_id", ""), new_id)
            # Ghi chú: Gán/cập nhật previous để lưu dữ liệu dùng ở bước tiếp theo.
            previous = refreshed.get(key)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if previous is None or (row.get("confirmed_access", "").strip().lower() == "yes"
                                    and previous.get("confirmed_access", "").strip().lower() != "yes"):
                # Ghi chú: Gán/cập nhật refreshed[key] để lưu dữ liệu dùng ở bước tiếp theo.
                refreshed[key] = row
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if access_rows:
            # Ghi chú: Gán/cập nhật fields để lưu dữ liệu dùng ở bước tiếp theo.
            fields = list(access_rows[0].keys())
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
                with ACCESS_CSV.open("w", newline="", encoding="utf-8-sig") as file:
                    # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
                    writer = csv.DictWriter(file, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(refreshed.values())
            except PermissionError:
                print("Could not refresh place access CSV (it may be open in Excel). Close it and rerun this script.")

    # Ghi chú: Gán/cập nhật degree_one để lưu dữ liệu dùng ở bước tiếp theo.
    degree_one = sum(1 for adjacent in adjacency.values() if len(adjacent) == 1)
    print(f"Built graph: {len(nodes)} graph nodes, {len(edges)} split edges")
    print(f"Approved interior connections applied: {len(accepted_intersections)}")
    print(f"Connected components: {component_id}")
    print(f"Dead ends (degree 1): {degree_one}")
    print(f"Graph file: {GRAPH_JSON}")
    print(f"Node/component review: {REPORT_CSV}")
    print("Preserved existing graph node IDs and refreshed place access references.")


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    main()
