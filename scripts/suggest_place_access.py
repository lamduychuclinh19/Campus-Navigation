"""Suggest, but do not assume, pedestrian access links from places to graph.

For each Polygon/MultiPolygon in data/nodes/*.geojson, list several nearby
routing graph nodes and the closest point on the polygon boundary. Review
each candidate against actual gates before using it for routing.

Run: python scripts/suggest_place_access.py
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
# Ghi chú: Gán/cập nhật NODES_DIR để lưu dữ liệu dùng ở bước tiếp theo.
NODES_DIR = ROOT / "data" / "nodes"
# Ghi chú: Gán/cập nhật GRAPH_PATH để lưu dữ liệu dùng ở bước tiếp theo.
GRAPH_PATH = ROOT / "data" / "routing" / "graph.json"
# Ghi chú: Gán/cập nhật PREVIOUS_OUTPUT_PATH để lưu dữ liệu dùng ở bước tiếp theo.
PREVIOUS_OUTPUT_PATH = ROOT / "data" / "routing" / "place_access_candidates.csv"
# Ghi chú: Gán/cập nhật OUTPUT_PATH để lưu dữ liệu dùng ở bước tiếp theo.
OUTPUT_PATH = ROOT / "data" / "routing" / "place_access_candidates_multi.csv"
# Ghi chú: Gán/cập nhật EARTH_RADIUS_M để lưu dữ liệu dùng ở bước tiếp theo.
EARTH_RADIUS_M = 6_371_000.0
# Ghi chú: Gán/cập nhật MAX_DISTANCE_M để lưu dữ liệu dùng ở bước tiếp theo.
MAX_DISTANCE_M = 40.0
# Ghi chú: Gán/cập nhật MAX_CANDIDATES_PER_PLACE để lưu dữ liệu dùng ở bước tiếp theo.
MAX_CANDIDATES_PER_PLACE = 6


# Ghi chú: Hàm local_xy; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def local_xy(point, origin_lat):
    """Approximate local metre coordinates for this small campus area."""
    # Ghi chú: Gán/cập nhật (lon, lat) để lưu dữ liệu dùng ở bước tiếp theo.
    lon, lat = point[:2]
    # Ghi chú: Gán/cập nhật x để lưu dữ liệu dùng ở bước tiếp theo.
    x = math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat))
    # Ghi chú: Gán/cập nhật y để lưu dữ liệu dùng ở bước tiếp theo.
    y = math.radians(lat) * EARTH_RADIUS_M
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return x, y


# Ghi chú: Hàm nearest_point_on_segment; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def nearest_point_on_segment(point, a, b, origin_lat):
    # Ghi chú: Gán/cập nhật (px, py) để lưu dữ liệu dùng ở bước tiếp theo.
    px, py = local_xy(point, origin_lat)
    # Ghi chú: Gán/cập nhật (ax, ay) để lưu dữ liệu dùng ở bước tiếp theo.
    ax, ay = local_xy(a, origin_lat)
    # Ghi chú: Gán/cập nhật (bx, by) để lưu dữ liệu dùng ở bước tiếp theo.
    bx, by = local_xy(b, origin_lat)
    # Ghi chú: Gán/cập nhật (dx, dy) để lưu dữ liệu dùng ở bước tiếp theo.
    dx, dy = bx - ax, by - ay
    # Ghi chú: Gán/cập nhật denom để lưu dữ liệu dùng ở bước tiếp theo.
    denom = dx * dx + dy * dy
    # Ghi chú: Gán/cập nhật t để lưu dữ liệu dùng ở bước tiếp theo.
    t = 0.0 if denom == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    # Ghi chú: Gán/cập nhật (x, y) để lưu dữ liệu dùng ở bước tiếp theo.
    x, y = ax + t * dx, ay + t * dy
    # Ghi chú: Gán/cập nhật distance để lưu dữ liệu dùng ở bước tiếp theo.
    distance = math.hypot(px - x, py - y)
    # Ghi chú: Gán/cập nhật lon để lưu dữ liệu dùng ở bước tiếp theo.
    lon = math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat))))
    # Ghi chú: Gán/cập nhật lat để lưu dữ liệu dùng ở bước tiếp theo.
    lat = math.degrees(y / EARTH_RADIUS_M)
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return distance, [lon, lat]


# Ghi chú: Hàm polygon_rings; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def polygon_rings(geometry):
    # Ghi chú: Gán/cập nhật kind để lưu dữ liệu dùng ở bước tiếp theo.
    kind = geometry.get("type")
    # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
    coords = geometry.get("coordinates") or []
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if kind == "Polygon":
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return coords[:1]  # Outer ring; ignore holes when finding the boundary.
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if kind == "MultiPolygon":
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return [polygon[0] for polygon in coords if polygon]
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return []


# Ghi chú: Hàm read_csv_rows; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def read_csv_rows(path):
    """Read UTF-8 CSV first, with a Windows Vietnamese encoding fallback."""
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Gán/cập nhật text để lưu dữ liệu dùng ở bước tiếp theo.
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Ghi chú: Gán/cập nhật text để lưu dữ liệu dùng ở bước tiếp theo.
        text = path.read_text(encoding="cp1258")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return list(csv.DictReader(text.splitlines()))


# Ghi chú: Hàm main; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def main():
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not GRAPH_PATH.exists():
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise SystemExit("Graph not found. Run: python scripts/build_routing_graph.py")
    # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with (ROOT / "data" / "routing" / "graph_nodes.csv").open("r", newline="", encoding="utf-8-sig") as file:
        # Ghi chú: Gán/cập nhật component_by_node để lưu dữ liệu dùng ở bước tiếp theo.
        component_by_node = {row["node_id"]: row["component"] for row in csv.DictReader(file)}

    # Ghi chú: Gán/cập nhật graph_nodes để lưu dữ liệu dùng ở bước tiếp theo.
    graph_nodes = [
        (node_id, node["coordinates"], component_by_node.get(node_id, ""))
        for node_id, node in graph["nodes"].items()
    ]
    # Ghi chú: Gán/cập nhật previous_decisions để lưu dữ liệu dùng ở bước tiếp theo.
    previous_decisions = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for decision_file in (OUTPUT_PATH, PREVIOUS_OUTPUT_PATH):
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if decision_file.exists():
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật prior_rows để lưu dữ liệu dùng ở bước tiếp theo.
                prior_rows = read_csv_rows(decision_file)
            except (OSError, UnicodeDecodeError):
                continue
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for row in prior_rows:
                # Ghi chú: Gán/cập nhật key để lưu dữ liệu dùng ở bước tiếp theo.
                key = (row.get("place_id", ""), row.get("graph_node_candidate", ""))
                # Ghi chú: Gán/cập nhật previous_decisions[key] để lưu dữ liệu dùng ở bước tiếp theo.
                previous_decisions[key] = (row.get("confirmed_access", "REVIEW"), row.get("notes", ""))

    # Ghi chú: Gán/cập nhật rows để lưu dữ liệu dùng ở bước tiếp theo.
    rows = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for path in sorted(NODES_DIR.glob("*.geojson")):
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật data để lưu dữ liệu dùng ở bước tiếp theo.
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skip {path.name}: {error}")
            continue

        # Ghi chú: Gán/cập nhật polygon_index để lưu dữ liệu dùng ở bước tiếp theo.
        polygon_index = 0
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for feature in data.get("features", []):
            # Ghi chú: Gán/cập nhật geometry để lưu dữ liệu dùng ở bước tiếp theo.
            geometry = feature.get("geometry") or {}
            # Ghi chú: Gán/cập nhật rings để lưu dữ liệu dùng ở bước tiếp theo.
            rings = polygon_rings(geometry)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if not rings:
                continue
            polygon_index += 1
            # Ghi chú: Gán/cập nhật properties để lưu dữ liệu dùng ở bước tiếp theo.
            properties = feature.get("properties") or {}
            # Ghi chú: Gán/cập nhật fallback_id để lưu dữ liệu dùng ở bước tiếp theo.
            fallback_id = path.stem if polygon_index == 1 else f"{path.stem}_{polygon_index}"
            # Ghi chú: Gán/cập nhật place_id để lưu dữ liệu dùng ở bước tiếp theo.
            place_id = properties.get("id") or fallback_id

            # Ghi chú: Gán/cập nhật nearest_by_node để lưu dữ liệu dùng ở bước tiếp theo.
            nearest_by_node = {}
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for ring in rings:
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if len(ring) < 2:
                    continue
                # Ghi chú: Gán/cập nhật origin_lat để lưu dữ liệu dùng ở bước tiếp theo.
                origin_lat = sum(float(point[1]) for point in ring) / len(ring)
                # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
                for graph_node_id, graph_coord, component in graph_nodes:
                    # Ghi chú: Gán/cập nhật nearest_distance để lưu dữ liệu dùng ở bước tiếp theo.
                    nearest_distance = math.inf
                    # Ghi chú: Gán/cập nhật nearest_coordinate để lưu dữ liệu dùng ở bước tiếp theo.
                    nearest_coordinate = None
                    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
                    for a, b in zip(ring, ring[1:]):
                        # Ghi chú: Gán/cập nhật (distance, point) để lưu dữ liệu dùng ở bước tiếp theo.
                        distance, point = nearest_point_on_segment(graph_coord, a, b, origin_lat)
                        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                        if distance < nearest_distance:
                            # Ghi chú: Gán/cập nhật (nearest_distance, nearest_coordinate) để lưu dữ liệu dùng ở bước tiếp theo.
                            nearest_distance, nearest_coordinate = distance, point
                    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                    if nearest_coordinate is not None and nearest_distance <= MAX_DISTANCE_M:
                        # Ghi chú: Gán/cập nhật candidate để lưu dữ liệu dùng ở bước tiếp theo.
                        candidate = (nearest_distance, graph_node_id, graph_coord, component, nearest_coordinate)
                        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                        if graph_node_id not in nearest_by_node or nearest_distance < nearest_by_node[graph_node_id][0]:
                            # Ghi chú: Gán/cập nhật nearest_by_node[graph_node_id] để lưu dữ liệu dùng ở bước tiếp theo.
                            nearest_by_node[graph_node_id] = candidate

            # Ghi chú: Gán/cập nhật candidates để lưu dữ liệu dùng ở bước tiếp theo.
            candidates = sorted(nearest_by_node.values())[:MAX_CANDIDATES_PER_PLACE]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if not candidates:
                continue
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for rank, (distance, graph_node_id, graph_coord, component, access_coord) in enumerate(candidates, start=1):
                # Ghi chú: Gán/cập nhật (decision, notes) để lưu dữ liệu dùng ở bước tiếp theo.
                decision, notes = previous_decisions.get(
                    (place_id, graph_node_id),
                    ("REVIEW", "Check whether this graph node connects to a real pedestrian gate."),
                )
                rows.append({
                    "place_id": place_id,
                    "file": path.name,
                    "candidate_rank": rank,
                    "graph_node_candidate": graph_node_id,
                    "component": component,
                    "distance_to_polygon_m": round(distance, 2),
                    "graph_node_lon": graph_coord[0],
                    "graph_node_lat": graph_coord[1],
                    "projected_boundary_lon": round(access_coord[0], 7),
                    "projected_boundary_lat": round(access_coord[1], 7),
                    "confirmed_access": decision,
                    "notes": notes,
                })

    # Ghi chú: Gán/cập nhật fields để lưu dữ liệu dùng ở bước tiếp theo.
    fields = ["place_id", "file", "candidate_rank", "graph_node_candidate", "component", "distance_to_polygon_m",
              "graph_node_lon", "graph_node_lat", "projected_boundary_lon", "projected_boundary_lat",
              "confirmed_access", "notes"]
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Access candidates: {len(rows)} across {len({row['place_id'] for row in rows})} places")
    print(f"Showing up to {MAX_CANDIDATES_PER_PLACE} graph nodes within {MAX_DISTANCE_M:g} m per place")
    print(f"Review file: {OUTPUT_PATH}")
    print("No access links were automatically added to the routing graph.")


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    main()
