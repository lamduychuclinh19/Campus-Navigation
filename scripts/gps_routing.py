"""GPS snapping and shortest routing over the reviewed campus graph.

All internal projection and edge measurements use a local spherical AEQD
projection centered on the mean graph-node coordinate. GeoJSON coordinates
remain WGS84 [longitude, latitude].
"""

import csv
import heapq
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ROUTING = DATA / "routing"
GRAPH_PATH = ROUTING / "graph.json"
ACCESS_PATH = ROUTING / "place_access_candidates_multi.csv"
MAX_SNAP_DISTANCE_METERS = 50.0
MAX_GPS_ACCURACY_METERS = 50.0
EARTH_RADIUS_M = 6_371_000.0
ENDPOINT_EPSILON = 1e-6


class RoutingError(ValueError):
    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        self.status = status
        self.code = code


def read_access_rows(path=ACCESS_PATH):
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = path.read_text(encoding="cp1258")
    return list(csv.DictReader(content.splitlines()))


def valid_lonlat(lon, lat):
    return math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90


class LocalAEQD:
    """Spherical azimuthal-equidistant transform for the small campus area."""

    def __init__(self, lon0, lat0):
        self.lon0 = math.radians(lon0)
        self.lat0 = math.radians(lat0)
        self.sin_lat0 = math.sin(self.lat0)
        self.cos_lat0 = math.cos(self.lat0)

    def forward(self, coordinate):
        lon, lat = map(float, coordinate[:2])
        lon, lat = math.radians(lon), math.radians(lat)
        delta_lon = lon - self.lon0
        cos_c = max(-1.0, min(1.0, self.sin_lat0 * math.sin(lat) + self.cos_lat0 * math.cos(lat) * math.cos(delta_lon)))
        c = math.acos(cos_c)
        k = 1.0 if c < 1e-12 else c / math.sin(c)
        return (EARTH_RADIUS_M * k * math.cos(lat) * math.sin(delta_lon),
                EARTH_RADIUS_M * k * (self.cos_lat0 * math.sin(lat) - self.sin_lat0 * math.cos(lat) * math.cos(delta_lon)))

    def inverse(self, point):
        x, y = point
        rho = math.hypot(x, y)
        if rho < 1e-12:
            return [math.degrees(self.lon0), math.degrees(self.lat0)]
        c = rho / EARTH_RADIUS_M
        lat = math.asin(math.cos(c) * self.sin_lat0 + y * math.sin(c) * self.cos_lat0 / rho)
        lon = self.lon0 + math.atan2(x * math.sin(c), rho * self.cos_lat0 * math.cos(c) - y * self.sin_lat0 * math.sin(c))
        return [math.degrees(lon), math.degrees(lat)]


def projection_for_graph(graph):
    coords = [node["coordinates"] for node in graph.get("nodes", {}).values()]
    if not coords:
        raise RoutingError("Đồ thị không có node hợp lệ.", 500, "invalid_graph")
    return LocalAEQD(sum(float(p[0]) for p in coords) / len(coords),
                     sum(float(p[1]) for p in coords) / len(coords))


def project_point_to_segment(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    denom = dx * dx + dy * dy
    if denom <= 1e-18:
        return (start[0], start[1]), 0.0, math.hypot(point[0] - start[0], point[1] - start[1])
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denom))
    projected = (start[0] + t * dx, start[1] + t * dy)
    return projected, t, math.hypot(point[0] - projected[0], point[1] - projected[1])


def project_to_nearest_edge(graph, point_lonlat, transformer=None):
    transformer = transformer or projection_for_graph(graph)
    point = transformer.forward(point_lonlat)
    best = None
    for edge in graph.get("edges", []):
        try:
            coordinates = edge.get("coordinates") or [graph["nodes"][edge["from"]]["coordinates"], graph["nodes"][edge["to"]]["coordinates"]]
            if len(coordinates) < 2 or not math.isfinite(float(edge["length_m"])) or float(edge["length_m"]) <= 0:
                continue
            projected_coords = [transformer.forward(c) for c in coordinates]
            segment_lengths = [math.dist(a, b) for a, b in zip(projected_coords, projected_coords[1:])]
            total_geometry = sum(segment_lengths)
            if total_geometry <= 1e-9:
                continue
            offset = 0.0
            for i, (a, b) in enumerate(zip(projected_coords, projected_coords[1:])):
                projected, t, gap = project_point_to_segment(point, a, b)
                along_geometry = offset + t * segment_lengths[i]
                fraction = along_geometry / total_geometry
                candidate = (gap, edge, transformer.inverse(projected), fraction)
                if best is None or gap < best[0]:
                    best = candidate
                offset += segment_lengths[i]
        except (KeyError, TypeError, ValueError, IndexError, OverflowError):
            continue
    return best


def get_places(graph, rows=None):
    rows = read_access_rows() if rows is None else rows
    places = {}
    for row in rows:
        if row.get("confirmed_access", "").strip().lower() != "yes":
            continue
        node = row.get("graph_node_candidate", "").strip()
        place = row.get("place_id", "").strip()
        if node not in graph.get("nodes", {}) or not place:
            continue
        try:
            boundary = [float(row["projected_boundary_lon"]), float(row["projected_boundary_lat"])]
            if not valid_lonlat(*boundary):
                continue
            node_coord = graph["nodes"][node]["coordinates"]
            transformer = projection_for_graph(graph)
            connector = math.dist(transformer.forward(boundary), transformer.forward(node_coord))
        except (KeyError, TypeError, ValueError):
            continue
        places.setdefault(place, []).append({"node": node, "boundary": boundary, "connector_m": connector})
    return places


def dijkstra(adjacency, starts):
    distances, previous, origin = {}, {}, {}
    queue = []
    for node, distance in starts:
        if distance < distances.get(node, math.inf):
            distances[node] = distance
            origin[node] = node
            heapq.heappush(queue, (distance, node))
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != distances.get(node):
            continue
        for neighbor, weight, edge_id in adjacency.get(node, []):
            candidate = cost + weight
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                previous[neighbor] = (node, edge_id)
                origin[neighbor] = origin[node]
                heapq.heappush(queue, (candidate, neighbor))
    return distances, previous, origin


def route_from_gps(payload, graph=None, access_rows=None):
    if not isinstance(payload, dict):
        raise RoutingError("Request JSON không hợp lệ.")
    source = payload.get("location_source", "browser")
    if source not in ("browser", "map"):
        raise RoutingError("location_source phải là browser hoặc map.")
    try:
        lat, lon = float(payload["latitude"]), float(payload["longitude"])
        raw_accuracy = payload.get("accuracy")
        accuracy = None if raw_accuracy is None else float(raw_accuracy)
    except (KeyError, TypeError, ValueError):
        raise RoutingError("Cần latitude, longitude và accuracy hợp lệ (accuracy có thể null cho vị trí chọn trên bản đồ).")
    if not valid_lonlat(lon, lat) or (accuracy is not None and (not math.isfinite(accuracy) or accuracy < 0)):
        raise RoutingError("Tọa độ GPS hoặc accuracy không hợp lệ.")
    if source == "browser" and accuracy is None:
        raise RoutingError("GPS trình duyệt cần có accuracy.")
    if source == "map" and accuracy is not None:
        raise RoutingError("Vị trí chọn trên bản đồ không có accuracy GPS; gửi accuracy=null.")
    if source == "browser" and accuracy > MAX_GPS_ACCURACY_METERS:
        raise RoutingError(f"GPS chưa đủ chính xác ({accuracy:.1f} m). Hãy định vị lại; ngưỡng là {MAX_GPS_ACCURACY_METERS:g} m.", 422, "poor_accuracy")
    destination = str(payload.get("destination_place_id", "")).strip()
    graph = graph if graph is not None else json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    places = get_places(graph, read_access_rows() if access_rows is None else access_rows)
    if destination not in places:
        raise RoutingError("Địa điểm đích không tồn tại hoặc chưa có cổng tiếp cận được xác nhận.", 404, "unknown_destination")
    transformer = projection_for_graph(graph)
    nearest = project_to_nearest_edge(graph, [lon, lat], transformer)
    if nearest is None:
        raise RoutingError("Không tìm thấy cạnh đi bộ hợp lệ trong đồ thị.", 422, "no_valid_edge")
    snap_distance, edge, projected_lonlat, fraction = nearest
    if snap_distance > MAX_SNAP_DISTANCE_METERS:
        raise RoutingError(f"Không có lối đi trong phạm vi {MAX_SNAP_DISTANCE_METERS:g} m (gần nhất {snap_distance:.1f} m).", 422, "too_far_to_snap")

    virtual_id = "GPS_SOURCE"
    split_interior = ENDPOINT_EPSILON < fraction < 1 - ENDPOINT_EPSILON
    adjacency = {node_id: [] for node_id in graph["nodes"]}
    for current in graph["edges"]:
        if current["edge_id"] == edge["edge_id"] and split_interior:
            continue
        try:
            weight = float(current["length_m"])
            if weight < 0 or not math.isfinite(weight):
                continue
            adjacency[current["from"]].append((current["to"], weight, current["edge_id"]))
            if not graph.get("directed", False):
                adjacency[current["to"]].append((current["from"], weight, current["edge_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    u, v, length = edge["from"], edge["to"], float(edge["length_m"])
    if fraction <= ENDPOINT_EPSILON:
        virtual_id = u
        projected_lonlat = graph["nodes"][u]["coordinates"]
        starts = [(virtual_id, 0.0)]
    elif fraction >= 1 - ENDPOINT_EPSILON:
        virtual_id = v
        projected_lonlat = graph["nodes"][v]["coordinates"]
        starts = [(virtual_id, 0.0)]
    else:
        forward_weight = fraction * length
        reverse_weight = (1 - fraction) * length
        adjacency[virtual_id] = []
        adjacency[u].append((virtual_id, forward_weight, f"{edge['edge_id']}:gps-a"))
        adjacency[virtual_id].append((v, reverse_weight, f"{edge['edge_id']}:gps-b"))
        if not graph.get("directed", False):
            adjacency[virtual_id].append((u, forward_weight, f"{edge['edge_id']}:gps-a"))
            adjacency[v].append((virtual_id, reverse_weight, f"{edge['edge_id']}:gps-b"))
        starts = [(virtual_id, 0.0)]

    distances, previous, _origin = dijkstra(adjacency, starts)
    best = None
    for access in places[destination]:
        node = access["node"]
        if node in distances:
            total = distances[node] + access["connector_m"]
            if best is None or total < best[0]:
                best = total, access
    if best is None:
        raise RoutingError("Không có đường đi từ vị trí GPS đến các cổng đã xác nhận của địa điểm.", 404, "no_route")
    total, target = best
    route_nodes = [target["node"]]
    cursor = target["node"]
    while cursor != virtual_id and cursor in previous:
        cursor = previous[cursor][0]
        route_nodes.append(cursor)
    route_nodes.reverse()
    route_edge_ids = [previous[node][1] for node in route_nodes[1:] if node in previous]
    edge_by_id = {item["edge_id"]: item for item in graph["edges"]}
    route_coordinates = [projected_lonlat]
    cursor = virtual_id
    for next_node in route_nodes[1:]:
        prev_node, used_id = previous[next_node]
        if prev_node != cursor:
            break
        if used_id.endswith(":gps-a") or used_id.endswith(":gps-b"):
            # The virtual split is represented by the projected point followed by graph node.
            route_coordinates.append(graph["nodes"][next_node]["coordinates"])
        else:
            used_edge = edge_by_id[used_id]
            coords = list(used_edge.get("coordinates") or [graph["nodes"][prev_node]["coordinates"], graph["nodes"][next_node]["coordinates"]])
            if used_edge["from"] != prev_node:
                coords.reverse()
            route_coordinates.extend(coords[1:])
        cursor = next_node
    route_coordinates.append(target["boundary"])
    return {
        "success": True,
        "route": {"node_ids": route_nodes, "edge_ids": route_edge_ids, "coordinates": route_coordinates, "distance_meters": round(total, 2)},
        "gps": {"latitude": lat, "longitude": lon, "accuracy_meters": accuracy, "location_source": source},
        "projection": {"latitude": projected_lonlat[1], "longitude": projected_lonlat[0],
                       "distance_meters": round(snap_distance, 2), "edge_id": edge["edge_id"], "t": fraction},
        "virtual_node": {"id": virtual_id},
        "destination": {"place_id": destination, "access_point_id": target["node"]},
    }


def route_between_places(payload, graph=None, access_rows=None):
    graph = graph if graph is not None else json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    places = get_places(graph, read_access_rows() if access_rows is None else access_rows)
    start, destination = str(payload.get("start_place_id", "")), str(payload.get("destination_place_id", ""))
    if start not in places or destination not in places:
        raise RoutingError("Địa điểm xuất phát hoặc đích không tồn tại/chưa có cổng đã xác nhận.", 404, "unknown_place")
    if start == destination:
        raise RoutingError("Xuất phát và đích phải là hai địa điểm khác nhau.")
    adjacency = {node_id: [] for node_id in graph["nodes"]}
    for edge in graph["edges"]:
        weight = float(edge["length_m"])
        adjacency[edge["from"]].append((edge["to"], weight, edge["edge_id"]))
        if not graph.get("directed", False):
            adjacency[edge["to"]].append((edge["from"], weight, edge["edge_id"]))
    starts = [(access["node"], access["connector_m"]) for access in places[start]]
    distances, previous, _ = dijkstra(adjacency, starts)
    winner = min(((distances[a["node"]] + a["connector_m"], a) for a in places[destination] if a["node"] in distances), default=None)
    if winner is None:
        raise RoutingError("Không có đường giữa các cổng đã xác nhận.", 404, "no_route")
    total, target = winner
    nodes = [target["node"]]
    while nodes[-1] in previous:
        nodes.append(previous[nodes[-1]][0])
    nodes.reverse()
    edge_lookup = {edge["edge_id"]: edge for edge in graph["edges"]}
    coordinates = []
    for node_index, node in enumerate(nodes):
        coord = graph["nodes"][node]["coordinates"]
        if not coordinates:
            coordinates.append(coord)
        if node_index + 1 < len(nodes):
            next_node = nodes[node_index + 1]
            edge_id = previous[next_node][1]
            edge = edge_lookup[edge_id]
            edge_coords = list(edge.get("coordinates") or [coord, graph["nodes"][next_node]["coordinates"]])
            if edge["from"] != node:
                edge_coords.reverse()
            coordinates.extend(edge_coords[1:])
    start_access = min(places[start], key=lambda access: access["connector_m"] if access["node"] == nodes[0] else math.inf)
    coordinates.insert(0, start_access["boundary"])
    coordinates.append(target["boundary"])
    return {"success": True, "route": {"node_ids": nodes, "coordinates": coordinates, "distance_meters": round(total, 2)}, "destination": {"place_id": destination, "access_point_id": target["node"]}}
