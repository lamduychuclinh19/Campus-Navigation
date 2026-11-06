"""Find a shortest walking route between places using confirmed access links.

Run, for example:
    python scripts/route_between_places.py B KTH

Access links marked yes in place_access_candidates_multi.csv are treated as
candidate entrances. Place polygons are not used as graph shortcuts: Dijkstra
runs on the walkway graph, seeded from all confirmed origin gates, and chooses
the best confirmed destination gate.
"""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import argparse
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
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import sys

from building_obstacles import (
    CONFIRMED_INDOOR_PASSAGE_BUILDINGS,
    edge_building_intersection,
    filter_access_points,
    first_building_intersection,
    load_building_geometries,
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
# Ghi chú: Gán/cập nhật OUTPUT_PATH để lưu dữ liệu dùng ở bước tiếp theo.
OUTPUT_PATH = ROUTING / "route_result.geojson"
# Ghi chú: Gán/cập nhật EARTH_RADIUS_M để lưu dữ liệu dùng ở bước tiếp theo.
EARTH_RADIUS_M = 6_371_000.0
# Ghi chú: Gán/cập nhật DEFAULT_MAX_SNAP_DISTANCE_M để lưu dữ liệu dùng ở bước tiếp theo.
DEFAULT_MAX_SNAP_DISTANCE_M = 30.0


# Ghi chú: Hàm read_access_rows; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def read_access_rows(path):
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Gán/cập nhật content để lưu dữ liệu dùng ở bước tiếp theo.
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Ghi chú: Gán/cập nhật content để lưu dữ liệu dùng ở bước tiếp theo.
        content = path.read_text(encoding="cp1258")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return list(csv.DictReader(content.splitlines()))


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


# Ghi chú: Hàm build_adjacency; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def build_adjacency(graph, excluded_edge_ids=None):
    # Ghi chú: Gán/cập nhật adjacency để lưu dữ liệu dùng ở bước tiếp theo.
    adjacency = {node_id: [] for node_id in graph["nodes"]}
    excluded_edge_ids = excluded_edge_ids or set()
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge in graph["edges"]:
        if edge.get("edge_id") in excluded_edge_ids:
            continue
        adjacency[edge["from"]].append((edge["to"], edge["length_m"], edge["edge_id"]))
        adjacency[edge["to"]].append((edge["from"], edge["length_m"], edge["edge_id"]))
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return adjacency


# Ghi chú: Hàm nearest_point_on_segment; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def nearest_point_on_segment(point, a, b):
    """Snap an [lon, lat] position to an edge segment; return gap, fraction, point."""
    # Ghi chú: Gán/cập nhật origin_lat để lưu dữ liệu dùng ở bước tiếp theo.
    origin_lat = (point[1] + a[1] + b[1]) / 3

    # Ghi chú: Hàm to_xy; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def to_xy(coord):
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return (math.radians(coord[0]) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat)),
                math.radians(coord[1]) * EARTH_RADIUS_M)

    # Ghi chú: Gán/cập nhật (px, py) để lưu dữ liệu dùng ở bước tiếp theo.
    px, py = to_xy(point)
    # Ghi chú: Gán/cập nhật (ax, ay) để lưu dữ liệu dùng ở bước tiếp theo.
    ax, ay = to_xy(a)
    # Ghi chú: Gán/cập nhật (bx, by) để lưu dữ liệu dùng ở bước tiếp theo.
    bx, by = to_xy(b)
    # Ghi chú: Gán/cập nhật (dx, dy) để lưu dữ liệu dùng ở bước tiếp theo.
    dx, dy = bx - ax, by - ay
    # Ghi chú: Gán/cập nhật denom để lưu dữ liệu dùng ở bước tiếp theo.
    denom = dx * dx + dy * dy
    # Ghi chú: Gán/cập nhật fraction để lưu dữ liệu dùng ở bước tiếp theo.
    fraction = 0.0 if denom == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    # Ghi chú: Gán/cập nhật (x, y) để lưu dữ liệu dùng ở bước tiếp theo.
    x, y = ax + fraction * dx, ay + fraction * dy
    # Ghi chú: Gán/cập nhật snapped để lưu dữ liệu dùng ở bước tiếp theo.
    snapped = [
        math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat)))),
        math.degrees(y / EARTH_RADIUS_M),
    ]
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return distance_m(point, snapped), fraction, snapped


# Ghi chú: Hàm main; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def main():
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    # Ghi chú: Gán/cập nhật parser để lưu dữ liệu dùng ở bước tiếp theo.
    parser = argparse.ArgumentParser(description="Run Dijkstra between two places.")
    parser.add_argument("start", nargs="?", help="Start place_id, e.g. B")
    parser.add_argument("destination", nargs="?", help="Destination place_id, e.g. KTH")
    parser.add_argument("--start-coordinate", nargs=2, type=float, metavar=("LAT", "LON"),
                        help="Start from GPS or a map-picked coordinate (latitude longitude)")
    parser.add_argument("--max-snap-distance", type=float, default=DEFAULT_MAX_SNAP_DISTANCE_M,
                        help=f"Maximum allowed GPS/map-point gap to a walkway (default: {DEFAULT_MAX_SNAP_DISTANCE_M:g} m)")
    parser.add_argument("--start-gate", help="Use this graph node as the specific start gate, e.g. N007")
    parser.add_argument("--destination-gate", help="Use this graph node as the specific destination gate")
    # Ghi chú: Gán/cập nhật args để lưu dữ liệu dùng ở bước tiếp theo.
    args = parser.parse_args()

    # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    buildings = load_building_geometries(DATA / "nodes")
    blocked_edge_ids = {
        edge.get("edge_id") for edge in graph.get("edges", [])
        if edge_building_intersection(edge, graph, buildings) is not None
    }
    # Ghi chú: Gán/cập nhật rows để lưu dữ liệu dùng ở bước tiếp theo.
    rows = read_access_rows(ACCESS_PATH)
    # Ghi chú: Gán/cập nhật places để lưu dữ liệu dùng ở bước tiếp theo.
    places = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for row in rows:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if row.get("confirmed_access", "").strip().lower() == "yes":
            # Ghi chú: Gán/cập nhật node_id để lưu dữ liệu dùng ở bước tiếp theo.
            node_id = row.get("graph_node_candidate", "").strip()
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if node_id not in graph["nodes"]:
                continue
            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật boundary để lưu dữ liệu dùng ở bước tiếp theo.
                boundary = [float(row["projected_boundary_lon"]), float(row["projected_boundary_lat"])]
                # Ghi chú: Gán/cập nhật graph_coord để lưu dữ liệu dùng ở bước tiếp theo.
                graph_coord = graph["nodes"][node_id]["coordinates"]
            except (KeyError, TypeError, ValueError):
                continue
            # Ghi chú: Gán/cập nhật connector_length để lưu dữ liệu dùng ở bước tiếp theo.
            connector_length = distance_m(boundary, graph_coord)
            # Ghi chú: Gán/cập nhật place_id để lưu dữ liệu dùng ở bước tiếp theo.
            place_id = row.get("place_id", "").strip()
            places.setdefault(place_id, []).append({
                "node": node_id,
                "boundary": boundary,
                "connector_m": connector_length,
            })
    places = filter_access_points(places, graph, buildings)

    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not args.start or (not args.destination and not args.start_coordinate):
        print("Places with at least one confirmed access:")
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for place_id, access in sorted(places.items()):
            # Ghi chú: Gán/cập nhật gates để lưu dữ liệu dùng ở bước tiếp theo.
            gates = ", ".join(sorted({item["node"] for item in access}))
            print(f"  {place_id}: {gates}")
        print("Usage: python scripts/route_between_places.py START_ID DESTINATION_ID [--start-gate NODE] [--destination-gate NODE]")
        print("   or: python scripts/route_between_places.py DESTINATION_ID --start-coordinate LAT LON")
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return 0

    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if args.start_coordinate:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if args.start_gate:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise SystemExit("Use either --start-coordinate or --start-gate, not both.")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if args.destination:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise SystemExit("With --start-coordinate, pass the destination as the first positional ID only.")
        # Ghi chú: Gán/cập nhật start để lưu dữ liệu dùng ở bước tiếp theo.
        start = None
        # Ghi chú: Gán/cập nhật destination để lưu dữ liệu dùng ở bước tiếp theo.
        destination = args.start
        # Ghi chú: Gán/cập nhật start_coordinate để lưu dữ liệu dùng ở bước tiếp theo.
        start_coordinate = [args.start_coordinate[1], args.start_coordinate[0]]
    else:
        # Ghi chú: Gán/cập nhật (start, destination) để lưu dữ liệu dùng ở bước tiếp theo.
        start, destination = args.start, args.destination
        # Ghi chú: Gán/cập nhật start_coordinate để lưu dữ liệu dùng ở bước tiếp theo.
        start_coordinate = None

    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not destination or destination not in places or (start is not None and start not in places):
        print(f"Place IDs with confirmed access: {', '.join(sorted(places))}")
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise SystemExit("Unknown destination, or it has no confirmed access marked yes.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if start is not None and start == destination:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise SystemExit("Start and destination must be different places.")

    # Ghi chú: Gán/cập nhật start_accesses để lưu dữ liệu dùng ở bước tiếp theo.
    start_accesses = places[start] if start is not None else []
    # Ghi chú: Gán/cập nhật destination_accesses để lưu dữ liệu dùng ở bước tiếp theo.
    destination_accesses = places[destination]
    if not destination_accesses:
        raise SystemExit("All confirmed destination access connectors cross known building footprints.")
    if start is not None and not start_accesses:
        raise SystemExit("All confirmed start access connectors cross known building footprints.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if args.start_gate:
        # Ghi chú: Gán/cập nhật start_accesses để lưu dữ liệu dùng ở bước tiếp theo.
        start_accesses = [access for access in start_accesses if access["node"] == args.start_gate]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not start_accesses:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise SystemExit(f"{args.start_gate} is not a confirmed access gate for {start}.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if args.destination_gate:
        # Ghi chú: Gán/cập nhật destination_accesses để lưu dữ liệu dùng ở bước tiếp theo.
        destination_accesses = [access for access in destination_accesses if access["node"] == args.destination_gate]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not destination_accesses:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise SystemExit(f"{args.destination_gate} is not a confirmed access gate for {destination}.")

    # Ghi chú: Gán/cập nhật adjacency để lưu dữ liệu dùng ở bước tiếp theo.
    adjacency = build_adjacency(graph, blocked_edge_ids)
    # Ghi chú: Gán/cập nhật distances để lưu dữ liệu dùng ở bước tiếp theo.
    distances = {}
    # Ghi chú: Gán/cập nhật previous để lưu dữ liệu dùng ở bước tiếp theo.
    previous = {}
    # Ghi chú: Gán/cập nhật queue để lưu dữ liệu dùng ở bước tiếp theo.
    queue = []
    # Ghi chú: Gán/cập nhật origin_by_node để lưu dữ liệu dùng ở bước tiếp theo.
    origin_by_node = {}
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if start_coordinate is None:
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for access in start_accesses:
            # Ghi chú: Gán/cập nhật node để lưu dữ liệu dùng ở bước tiếp theo.
            node = access["node"]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if access["connector_m"] < distances.get(node, math.inf):
                # Ghi chú: Gán/cập nhật distances[node] để lưu dữ liệu dùng ở bước tiếp theo.
                distances[node] = access["connector_m"]
                # Ghi chú: Gán/cập nhật origin_by_node[node] để lưu dữ liệu dùng ở bước tiếp theo.
                origin_by_node[node] = {"kind": "place", "access": access}
                previous.pop(node, None)
                heapq.heappush(queue, (access["connector_m"], node))
    else:
        # Ghi chú: Gán/cập nhật snap_candidates để lưu dữ liệu dùng ở bước tiếp theo.
        snap_candidates = []
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for edge in graph["edges"]:
            if edge.get("edge_id") in blocked_edge_ids:
                continue
            # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
            coordinates = edge.get("coordinates") or []
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if len(coordinates) < 2:
                continue
            # Ghi chú: Gán/cập nhật (gap, fraction, snapped) để lưu dữ liệu dùng ở bước tiếp theo.
            gap, fraction, snapped = nearest_point_on_segment(start_coordinate, coordinates[0], coordinates[-1])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if gap > args.max_snap_distance:
                continue
            if first_building_intersection(
                [start_coordinate, snapped], buildings,
                allowed_building_ids=CONFIRMED_INDOOR_PASSAGE_BUILDINGS,
            ) is not None:
                continue
            # Ghi chú: Gán/cập nhật partial_length để lưu dữ liệu dùng ở bước tiếp theo.
            partial_length = edge["length_m"] * fraction
            snap_candidates.append((gap, edge, fraction, snapped, partial_length))

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not snap_candidates:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise SystemExit(f"No walkway within {args.max_snap_distance:g} m of the selected start point; choose a point closer to a mapped path.")

        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for gap, edge, fraction, snapped, partial_length in snap_candidates:
            # Ghi chú: Gán/cập nhật total_edge_length để lưu dữ liệu dùng ở bước tiếp theo.
            total_edge_length = edge["length_m"]
            # Ghi chú: Gán/cập nhật starts để lưu dữ liệu dùng ở bước tiếp theo.
            starts = (
                (edge["from"], partial_length, [snapped, edge["coordinates"][0]]),
                (edge["to"], total_edge_length - partial_length, [snapped, edge["coordinates"][-1]]),
            )
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for node, along_length, partial_coords in starts:
                # Ghi chú: Gán/cập nhật seed_cost để lưu dữ liệu dùng ở bước tiếp theo.
                seed_cost = gap + along_length
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if seed_cost < distances.get(node, math.inf):
                    # Ghi chú: Gán/cập nhật distances[node] để lưu dữ liệu dùng ở bước tiếp theo.
                    distances[node] = seed_cost
                    # Ghi chú: Gán/cập nhật origin_by_node[node] để lưu dữ liệu dùng ở bước tiếp theo.
                    origin_by_node[node] = {
                        "kind": "coordinate", "coordinate": start_coordinate,
                        "snap": snapped, "snap_gap_m": gap,
                        "edge_id": edge["edge_id"], "partial_coords": partial_coords,
                    }
                    previous.pop(node, None)
                    heapq.heappush(queue, (seed_cost, node))

    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    while queue:
        # Ghi chú: Gán/cập nhật (current_distance, node) để lưu dữ liệu dùng ở bước tiếp theo.
        current_distance, node = heapq.heappop(queue)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if current_distance != distances.get(node):
            continue
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for neighbor, weight, edge_id in adjacency[node]:
            # Ghi chú: Gán/cập nhật candidate để lưu dữ liệu dùng ở bước tiếp theo.
            candidate = current_distance + weight
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if candidate < distances.get(neighbor, math.inf):
                # Ghi chú: Gán/cập nhật distances[neighbor] để lưu dữ liệu dùng ở bước tiếp theo.
                distances[neighbor] = candidate
                # Ghi chú: Gán/cập nhật previous[neighbor] để lưu dữ liệu dùng ở bước tiếp theo.
                previous[neighbor] = (node, edge_id)
                # Ghi chú: Gán/cập nhật origin_by_node[neighbor] để lưu dữ liệu dùng ở bước tiếp theo.
                origin_by_node[neighbor] = origin_by_node[node]
                heapq.heappush(queue, (candidate, neighbor))

    # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
    best = None
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for access in destination_accesses:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if access["node"] not in distances:
            continue
        # Ghi chú: Gán/cập nhật total để lưu dữ liệu dùng ở bước tiếp theo.
        total = distances[access["node"]] + access["connector_m"]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if best is None or total < best[0]:
            # Ghi chú: Gán/cập nhật best để lưu dữ liệu dùng ở bước tiếp theo.
            best = (total, access)

    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if best is None:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if OUTPUT_PATH.exists():
            OUTPUT_PATH.unlink()
        # Ghi chú: Gán/cập nhật components để lưu dữ liệu dùng ở bước tiếp theo.
        components = {}
        # Ghi chú: Gán/cập nhật component_file để lưu dữ liệu dùng ở bước tiếp theo.
        component_file = ROUTING / "graph_nodes.csv"
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if component_file.exists():
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for row in csv.DictReader(component_file.open("r", newline="", encoding="utf-8-sig")):
                # Ghi chú: Gán/cập nhật components[row['node_id']] để lưu dữ liệu dùng ở bước tiếp theo.
                components[row["node_id"]] = row["component"]
        # Ghi chú: Gán/cập nhật start_components để lưu dữ liệu dùng ở bước tiếp theo.
        start_components = sorted({components.get(access["node"], "?") for access in start_accesses}) if start is not None else []
        # Ghi chú: Gán/cập nhật destination_components để lưu dữ liệu dùng ở bước tiếp theo.
        destination_components = sorted({components.get(access["node"], "?") for access in places[destination]})
        print("No route: no confirmed start gate can reach any confirmed destination gate on the current graph.")
        # Ghi chú: Gán/cập nhật start_label để lưu dữ liệu dùng ở bước tiếp theo.
        start_label = "GPS/map point" if start is None else start
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if start is None:
            # Ghi chú: Gán/cập nhật nearby_components để lưu dữ liệu dùng ở bước tiếp theo.
            nearby_components = sorted({
                components.get(access["node"], "?") for access in places[destination]
                if access["node"] in distances
            })
            print(f"Start point: {start_coordinate[1]:.7f}, {start_coordinate[0]:.7f}; snap limit {args.max_snap_distance:g} m")
            print(f"Destination-reachable components from start: {', '.join(nearby_components) or 'none'}")
        else:
            print(f"{start_label} access nodes/components: " + ", ".join(
                f"{access['node']}/C{components.get(access['node'], '?')}" for access in start_accesses))
        print(f"{destination} access nodes/components: " + ", ".join(
            f"{access['node']}/C{components.get(access['node'], '?')}" for access in destination_accesses))
        print(f"Start components: {', '.join(start_components)}; destination components: {', '.join(destination_components)}")
        print("The graph has disconnected components; inspect graph_nodes.csv and connect real walkway intersections.")
        print("Removed any old route_result.geojson so the map cannot show a stale route.")
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return 2

    # Ghi chú: Gán/cập nhật (total_length, target_access) để lưu dữ liệu dùng ở bước tiếp theo.
    total_length, target_access = best
    # Ghi chú: Gán/cập nhật target_node để lưu dữ liệu dùng ở bước tiếp theo.
    target_node = target_access["node"]
    # Ghi chú: Gán/cập nhật route_nodes để lưu dữ liệu dùng ở bước tiếp theo.
    route_nodes = [target_node]
    # Ghi chú: Gán/cập nhật route_edges để lưu dữ liệu dùng ở bước tiếp theo.
    route_edges = []
    # Ghi chú: Gán/cập nhật cursor để lưu dữ liệu dùng ở bước tiếp theo.
    cursor = target_node
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    while cursor in previous:
        # Ghi chú: Gán/cập nhật (parent, edge_id) để lưu dữ liệu dùng ở bước tiếp theo.
        parent, edge_id = previous[cursor]
        route_edges.append(edge_id)
        route_nodes.append(parent)
        # Ghi chú: Gán/cập nhật cursor để lưu dữ liệu dùng ở bước tiếp theo.
        cursor = parent
    route_nodes.reverse()
    route_edges.reverse()
    # Ghi chú: Gán/cập nhật start_origin để lưu dữ liệu dùng ở bước tiếp theo.
    start_origin = origin_by_node[route_nodes[0]]

    # Ghi chú: Gán/cập nhật edge_lookup để lưu dữ liệu dùng ở bước tiếp theo.
    edge_lookup = {edge["edge_id"]: edge for edge in graph["edges"]}
    # Ghi chú: Gán/cập nhật line_features để lưu dữ liệu dùng ở bước tiếp theo.
    line_features = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for index, edge_id in enumerate(route_edges):
        # Ghi chú: Gán/cập nhật edge để lưu dữ liệu dùng ở bước tiếp theo.
        edge = edge_lookup[edge_id]
        # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
        coordinates = edge.get("coordinates")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not coordinates:
            # Ghi chú: Gán/cập nhật source để lưu dữ liệu dùng ở bước tiếp theo.
            source = DATA / "ways" / edge["file"]
            # Ghi chú: Gán/cập nhật geojson để lưu dữ liệu dùng ở bước tiếp theo.
            geojson = json.loads(source.read_text(encoding="utf-8"))
            # Ghi chú: Gán/cập nhật feature để lưu dữ liệu dùng ở bước tiếp theo.
            feature = next((feature for feature in geojson.get("features", [])
                            if feature.get("geometry", {}).get("type") == "LineString"
                            and len(feature.get("geometry", {}).get("coordinates", [])) >= 2), None)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if feature is None:
                continue
            # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
            coordinates = feature["geometry"]["coordinates"]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not coordinates:
            continue
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if edge["from"] != route_nodes[index]:
            # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
            coordinates = list(reversed(coordinates))
        line_features.append({
            "type": "Feature",
            "properties": {"edge_id": edge_id, "way_id": edge.get("way_id", edge_id), "kind": "walkway"},
            "geometry": {"type": "LineString", "coordinates": coordinates},
        })

    # Ghi chú: Gán/cập nhật target_graph_coord để lưu dữ liệu dùng ở bước tiếp theo.
    target_graph_coord = graph["nodes"][target_access["node"]]["coordinates"]
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if start_origin["kind"] == "place":
        # Ghi chú: Gán/cập nhật start_access để lưu dữ liệu dùng ở bước tiếp theo.
        start_access = start_origin["access"]
        # Ghi chú: Gán/cập nhật origin_graph_coord để lưu dữ liệu dùng ở bước tiếp theo.
        origin_graph_coord = graph["nodes"][start_access["node"]]["coordinates"]
        line_features.insert(0, {
            "type": "Feature", "properties": {"kind": "access_connector", "place_id": start},
            "geometry": {"type": "LineString", "coordinates": [start_access["boundary"], origin_graph_coord]},
        })
    else:
        line_features.insert(0, {
            "type": "Feature", "properties": {"kind": "gps_connector", "snap_gap_m": round(start_origin["snap_gap_m"], 1)},
            "geometry": {"type": "LineString", "coordinates": [start_origin["coordinate"], start_origin["snap"]]},
        })
        # Ghi chú: Gán/cập nhật partial_coords để lưu dữ liệu dùng ở bước tiếp theo.
        partial_coords = start_origin["partial_coords"]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if len(partial_coords) >= 2 and distance_m(partial_coords[0], partial_coords[-1]) > 0.01:
            line_features.insert(1, {
                "type": "Feature", "properties": {"kind": "walkway", "edge_id": start_origin["edge_id"]},
                "geometry": {"type": "LineString", "coordinates": partial_coords},
            })
    line_features.append({
        "type": "Feature", "properties": {"kind": "access_connector", "place_id": destination},
        "geometry": {"type": "LineString", "coordinates": [target_graph_coord, target_access["boundary"]]},
    })
    OUTPUT_PATH.write_text(json.dumps({"type": "FeatureCollection", "features": line_features},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    # Ghi chú: Gán/cập nhật start_label để lưu dữ liệu dùng ở bước tiếp theo.
    start_label = start if start is not None else "GPS/map point"
    print(f"Shortest route {start_label} to {destination}: {total_length:.1f} m")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if start_origin["kind"] == "place":
        print(f"Start access: {start_origin['access']['node']}; destination access: {target_access['node']}")
    else:
        print(f"Start point snaps to {start_origin['edge_id']} ({start_origin['snap_gap_m']:.1f} m from mapped path); destination access: {target_access['node']}")
    print(f"Walkway edges: {' → '.join(route_edges) if route_edges else '(none; same graph node)'}")
    print(f"Route GeoJSON: {OUTPUT_PATH}")
    print("Review connector lines: they use straight-line distance from graph node to polygon boundary.")


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    main()
