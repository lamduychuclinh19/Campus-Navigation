"""Evaluate edge-projection and graph-node GPS routing on one graph snapshot."""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import time

from building_obstacles import (
    CONFIRMED_INDOOR_PASSAGE_BUILDINGS,
    edge_building_intersection,
    first_building_intersection,
    filter_access_points,
    load_building_geometries,
)

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from gps_routing import (
    DATA, GRAPH_PATH, MAX_GPS_ACCURACY_METERS, MAX_SNAP_DISTANCE_METERS,
    RoutingError, dijkstra, get_places, projection_for_graph, read_access_rows,
    project_to_nearest_edge, route_from_gps, valid_lonlat,
)

# Deliberately uses the existing 50 m snap envelope for a comparable connector
# budget. This is an operational cap, not a campus-calibrated pedestrian limit.
# Ghi chú: Gán/cập nhật MAX_NODE_CONNECTOR_DISTANCE_METERS để lưu dữ liệu dùng ở bước tiếp theo.
MAX_NODE_CONNECTOR_DISTANCE_METERS = 50.0
# Ghi chú: Gán/cập nhật BUILDING_DIR để lưu dữ liệu dùng ở bước tiếp theo.
BUILDING_DIR = DATA / "nodes"
# Ghi chú: Gán/cập nhật EPSILON để lưu dữ liệu dùng ở bước tiếp theo.
EPSILON = 1e-8
# Source building rings are generally stored to six decimal places. This
# degree tolerance is about 5 cm on campus: it absorbs coordinate rounding at
# a wall while still treating metre-scale polygon interiors as obstructions.
# Ghi chú: Gán/cập nhật POINT_TOLERANCE_DEGREES để lưu dữ liệu dùng ở bước tiếp theo.
POINT_TOLERANCE_DEGREES = 5e-7


# Ghi chú: Hàm _load_building_geometries; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _load_building_geometries(directory=BUILDING_DIR):
    return load_building_geometries(directory)


# Ghi chú: Hàm _point_on_segment; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _point_on_segment(p, a, b, tolerance=POINT_TOLERANCE_DEGREES):
    # Ghi chú: Gán/cập nhật cross để lưu dữ liệu dùng ở bước tiếp theo.
    cross = (p[1]-a[1])*(b[0]-a[0])-(p[0]-a[0])*(b[1]-a[1])
    # Ghi chú: Gán/cập nhật segment_length để lưu dữ liệu dùng ở bước tiếp theo.
    segment_length = math.hypot(b[0]-a[0],b[1]-a[1])
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if segment_length == 0 or abs(cross) > tolerance*segment_length:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return False
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return (min(a[0],b[0])-tolerance <= p[0] <= max(a[0],b[0])+tolerance and
            min(a[1],b[1])-tolerance <= p[1] <= max(a[1],b[1])+tolerance)


# Ghi chú: Hàm _inside_ring; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _inside_ring(point, ring, tolerance=POINT_TOLERANCE_DEGREES):
    """Return whether a point is strictly inside a ring (boundary excluded)."""
    # Ghi chú: Gán/cập nhật inside để lưu dữ liệu dùng ở bước tiếp theo.
    inside = False
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for a, b in zip(ring, ring[1:]):
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if _point_on_segment(point, a, b, tolerance):
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return False
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if (a[1] > point[1]) != (b[1] > point[1]):
            # Ghi chú: Gán/cập nhật x để lưu dữ liệu dùng ở bước tiếp theo.
            x = (b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if point[0] < x:
                # Ghi chú: Gán/cập nhật inside để lưu dữ liệu dùng ở bước tiếp theo.
                inside = not inside
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return inside


# Ghi chú: Hàm _segment_intersection_parameters; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _segment_intersection_parameters(start, end, a, b):
    """Return parameters on start→end where two segments intersect."""
    # Ghi chú: Gán/cập nhật (rx, ry) để lưu dữ liệu dùng ở bước tiếp theo.
    rx, ry = end[0]-start[0], end[1]-start[1]
    # Ghi chú: Gán/cập nhật (sx, sy) để lưu dữ liệu dùng ở bước tiếp theo.
    sx, sy = b[0]-a[0], b[1]-a[1]
    # Ghi chú: Gán/cập nhật denominator để lưu dữ liệu dùng ở bước tiếp theo.
    denominator = rx*sy-ry*sx
    # Ghi chú: Gán/cập nhật (qx, qy) để lưu dữ liệu dùng ở bước tiếp theo.
    qx, qy = a[0]-start[0], a[1]-start[1]
    # Ghi chú: Gán/cập nhật cross_tolerance để lưu dữ liệu dùng ở bước tiếp theo.
    cross_tolerance = 1e-14
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if abs(denominator) > cross_tolerance:
        # Ghi chú: Gán/cập nhật t để lưu dữ liệu dùng ở bước tiếp theo.
        t = (qx*sy-qy*sx)/denominator
        # Ghi chú: Gán/cập nhật u để lưu dữ liệu dùng ở bước tiếp theo.
        u = (qx*ry-qy*rx)/denominator
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if -EPSILON <= t <= 1+EPSILON and -EPSILON <= u <= 1+EPSILON:
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return [max(0.0,min(1.0,t))]
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return []
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if abs(qx*ry-qy*rx) > cross_tolerance:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return []
    # Ghi chú: Gán/cập nhật length_squared để lưu dữ liệu dùng ở bước tiếp theo.
    length_squared = rx*rx+ry*ry
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if length_squared <= 1e-30:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return []
    # Ghi chú: Gán/cập nhật ta để lưu dữ liệu dùng ở bước tiếp theo.
    ta = (qx*rx+qy*ry)/length_squared
    # Ghi chú: Gán/cập nhật (q2x, q2y) để lưu dữ liệu dùng ở bước tiếp theo.
    q2x, q2y = b[0]-start[0], b[1]-start[1]
    # Ghi chú: Gán/cập nhật tb để lưu dữ liệu dùng ở bước tiếp theo.
    tb = (q2x*rx+q2y*ry)/length_squared
    # Ghi chú: Gán/cập nhật (low, high) để lưu dữ liệu dùng ở bước tiếp theo.
    low, high = max(0.0,min(ta,tb)), min(1.0,max(ta,tb))
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return [low,high] if low <= high+EPSILON else []


# Ghi chú: Hàm _inside_polygon; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _inside_polygon(point, rings, tolerance=POINT_TOLERANCE_DEGREES):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not rings or any(_point_on_segment(point,a,b,tolerance) for ring in rings for a,b in zip(ring,ring[1:])):
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return False
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return _inside_ring(point,rings[0],tolerance) and not any(_inside_ring(point,hole,tolerance) for hole in rings[1:])


# Ghi chú: Hàm _line_intersects_polygon; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _line_intersects_polygon(start, end, rings):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not rings:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return False
    # A zero-length connector on a polygon boundary merely touches the
    # footprint. Reject it only when the point is strictly inside the fill.
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if math.dist(start,end) <= 1e-14:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return _inside_polygon(start,rings)
    # Ghi chú: Gán/cập nhật parameters để lưu dữ liệu dùng ở bước tiếp theo.
    parameters = [0.0,1.0]
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for ring in rings:
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for a,b in zip(ring,ring[1:]):
            parameters.extend(_segment_intersection_parameters(start,end,a,b))
    # Ghi chú: Gán/cập nhật parameters để lưu dữ liệu dùng ở bước tiếp theo.
    parameters=sorted(set(parameters))
    # Test the open intervals between boundary crossings. Merely touching or
    # following a polygon boundary is not treated as travelling through it.
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for low,high in zip(parameters,parameters[1:]):
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if high-low <= 1e-12:
            continue
        # Ghi chú: Gán/cập nhật t để lưu dữ liệu dùng ở bước tiếp theo.
        t=(low+high)/2
        # Ghi chú: Gán/cập nhật sample để lưu dữ liệu dùng ở bước tiếp theo.
        sample=(start[0]+t*(end[0]-start[0]),start[1]+t*(end[1]-start[1]))
        # Interior samples need a much tighter tolerance than endpoints: do
        # not let the source-rounding allowance hide a real connector crossing.
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if _inside_polygon(sample,rings,tolerance=1e-10):
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return True
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return False


# Ghi chú: Hàm _connector_validation; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _connector_validation(start_lonlat, end_lonlat, buildings, allowed_building_ids=None):
    allowed_building_ids = allowed_building_ids or frozenset()
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for building_id, geometry in buildings:
        if building_id in allowed_building_ids:
            continue
        # Ghi chú: Gán/cập nhật (kind, coordinates) để lưu dữ liệu dùng ở bước tiếp theo.
        kind, coordinates = geometry["type"], geometry.get("coordinates", [])
        # Ghi chú: Gán/cập nhật polygons để lưu dữ liệu dùng ở bước tiếp theo.
        polygons = [coordinates] if kind == "Polygon" else coordinates
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for polygon in polygons:
            # Ghi chú: Gán/cập nhật rings để lưu dữ liệu dùng ở bước tiếp theo.
            rings = [[(float(x),float(y)) for x,y,*_ in ring] for ring in polygon if len(ring) >= 2]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if rings and _line_intersects_polygon(tuple(start_lonlat), tuple(end_lonlat), rings):
                # Ghi chú: Trả kết quả hiện tại về nơi gọi.
                return {"status":"INVALID", "reason":f"connector_intersects_building:{building_id}"}
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {"status":"UNVERIFIED", "reason":"No declared building intersection; pedestrian access is not field-verified and no restricted-area layer is available."}


# Ghi chú: Hàm _validate_payload; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _validate_payload(payload):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not isinstance(payload, dict):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Request JSON không hợp lệ.")
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
        raise RoutingError("Cần latitude, longitude và accuracy hợp lệ.")
    # Ghi chú: Gán/cập nhật source để lưu dữ liệu dùng ở bước tiếp theo.
    source = payload.get("location_source", "browser")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source not in ("browser", "map"):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("location_source phải là browser hoặc map.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not valid_lonlat(lon, lat) or (accuracy is not None and (not math.isfinite(accuracy) or accuracy < 0)):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Tọa độ GPS hoặc accuracy không hợp lệ.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source == "browser" and (accuracy is None or accuracy > MAX_GPS_ACCURACY_METERS):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError(f"GPS không đạt ngưỡng accuracy {MAX_GPS_ACCURACY_METERS:g} m.", 422, "poor_accuracy")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source == "map" and accuracy is not None:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Vị trí mô phỏng không có accuracy GPS; gửi accuracy=null.")
    # Ghi chú: Gán/cập nhật destination để lưu dữ liệu dùng ở bước tiếp theo.
    destination = str(payload.get("destination_place_id", "")).strip()
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return lat, lon, accuracy, source, destination


# Ghi chú: Hàm _nearest_node; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _nearest_node(graph, gps_lonlat, destination_nodes, transformer, buildings, max_distance):
    # Ghi chú: Gán/cập nhật gps_xy để lưu dữ liệu dùng ở bước tiếp theo.
    gps_xy = transformer.forward(gps_lonlat)
    # Ghi chú: Gán/cập nhật active để lưu dữ liệu dùng ở bước tiếp theo.
    active = {node_id: [] for node_id in graph.get("nodes", {})}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge in graph.get("edges", []):
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật weight để lưu dữ liệu dùng ở bước tiếp theo.
            weight = float(edge["length_m"])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if weight <= 0 or not math.isfinite(weight):
                continue
            if edge_building_intersection(edge, graph, buildings) is not None:
                continue
            # Ghi chú: Gán/cập nhật (u, v) để lưu dữ liệu dùng ở bước tiếp theo.
            u, v = edge["from"], edge["to"]
            active[u].append((v, weight, edge["edge_id"]))
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if not graph.get("directed", False):
                active[v].append((u, weight, edge["edge_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    # Ghi chú: Gán/cập nhật candidates để lưu dữ liệu dùng ở bước tiếp theo.
    candidates = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node_id, node in graph.get("nodes", {}).items():
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not active.get(node_id):
            continue
        # Ghi chú: Gán/cập nhật coord để lưu dữ liệu dùng ở bước tiếp theo.
        coord = node.get("coordinates")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(coord, list) or len(coord) < 2:
            continue
        # Ghi chú: Gán/cập nhật gap để lưu dữ liệu dùng ở bước tiếp theo.
        gap = math.dist(gps_xy, transformer.forward(coord))
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if gap <= max_distance:
            # Ghi chú: Gán/cập nhật validation để lưu dữ liệu dùng ở bước tiếp theo.
            validation = _connector_validation(
                gps_lonlat, coord, buildings,
            )
            candidates.append((validation["status"] == "INVALID", gap, node_id, coord, validation))
    candidates.sort(key=lambda item:(item[0], item[1], item[2]))
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not candidates:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return {"status":"FAILED", "code":"no_node_candidate", "error":f"No active graph node within {max_distance:g} m.", "validation":"UNVERIFIED"}
    # Ghi chú: Gán/cập nhật rejected để lưu dữ liệu dùng ở bước tiếp theo.
    rejected = [{"node_id":node_id,"connector_distance_meters":round(gap,2),"validation":validation["status"],"reason":validation["reason"]}
                for invalid,gap,node_id,_coord,validation in candidates if invalid]
    # Ghi chú: Gán/cập nhật adjacency để lưu dữ liệu dùng ở bước tiếp theo.
    adjacency = dict(active)
    # Ghi chú: Gán/cập nhật virtual để lưu dữ liệu dùng ở bước tiếp theo.
    virtual = "GPS_SOURCE_NODE"
    # Try viable node candidates in increasing distance; connectivity to any
    # confirmed destination gate is checked before one is selected.
    # Ghi chú: Gán/cập nhật routes để lưu dữ liệu dùng ở bước tiếp theo.
    routes = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for invalid, connector, node_id, coord, validation in candidates:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if invalid:
            continue
        # Ghi chú: Gán/cập nhật adjacency[virtual] để lưu dữ liệu dùng ở bước tiếp theo.
        adjacency[virtual] = [(node_id, connector, "GPS_CONNECTOR")]
        # Ghi chú: Gán/cập nhật (distances, previous, _) để lưu dữ liệu dùng ở bước tiếp theo.
        distances, previous, _ = dijkstra(adjacency, [(virtual, 0.0)])
        # Ghi chú: Gán/cập nhật reachable để lưu dữ liệu dùng ở bước tiếp theo.
        reachable = [(distances[a["node"]]+a["connector_m"], a) for a in destination_nodes if a["node"] in distances]
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not reachable:
            continue
        # Ghi chú: Gán/cập nhật (total, target) để lưu dữ liệu dùng ở bước tiếp theo.
        total, target = min(reachable, key=lambda item:item[0])
        # Ghi chú: Gán/cập nhật nodes để lưu dữ liệu dùng ở bước tiếp theo.
        nodes = [target["node"]]
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        while nodes[-1] != virtual and nodes[-1] in previous:
            nodes.append(previous[nodes[-1]][0])
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if nodes[-1] != virtual:
            continue
        nodes.reverse()
        # Ghi chú: Gán/cập nhật edge_ids để lưu dữ liệu dùng ở bước tiếp theo.
        edge_ids = []
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for current in nodes[1:]:
            edge_ids.append(previous[current][1])
        # Ghi chú: Gán/cập nhật graph_nodes để lưu dữ liệu dùng ở bước tiếp theo.
        graph_nodes = [n for n in nodes if n != virtual]
        # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
        coords = [list(gps_lonlat), list(coord)]
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for index in range(1, len(graph_nodes)):
            # Ghi chú: Gán/cập nhật edge để lưu dữ liệu dùng ở bước tiếp theo.
            edge = next((e for e in graph["edges"] if e["edge_id"] == edge_ids[index]), None)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if edge:
                # Ghi chú: Gán/cập nhật part để lưu dữ liệu dùng ở bước tiếp theo.
                part = list(edge.get("coordinates") or [graph["nodes"][edge["from"]]["coordinates"], graph["nodes"][edge["to"]]["coordinates"]])
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if edge["from"] != graph_nodes[index-1]:
                    part.reverse()
                coords.extend(part[1:])
        coords.append(target["boundary"])
        routes.append({"status":"SUCCESS", "validation":validation["status"], "validation_reason":validation["reason"],
                "gps_virtual_node":{"id":virtual,"coordinates":list(gps_lonlat)},
                "graph_node_id":node_id,"graph_node_coordinates":coord,"connector_distance_meters":round(connector,2),
                "destination_access_point_id":target["node"],"node_ids":graph_nodes,"edge_ids":edge_ids[1:],
                "coordinates":coords,"route_distance_meters":round(total-connector,2),"total_distance_meters":round(total,2),
                "rejected_node_candidates":rejected})
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if routes:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return min(routes,key=lambda item:(item["validation"]!="VERIFIED",item["total_distance_meters"],item["connector_distance_meters"]))
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {"status":"FAILED", "code":"no_route", "error":"No candidate node reaches a confirmed destination access point.", "validation":"UNVERIFIED"}


# Ghi chú: Hàm _edge_candidate; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _edge_candidate(payload, graph, access_rows, buildings, max_snap_distance_m=MAX_SNAP_DISTANCE_METERS):
    try:
        lat, lon, _accuracy, _source, _destination = _validate_payload(payload)
    except RoutingError as error:
        return {"status":"FAILED", "code":error.code, "error":str(error), "validation":"UNVERIFIED"}
    gps = [lon, lat]
    transformer = projection_for_graph(graph)
    blocked_edges = {
        edge.get("edge_id") for edge in graph.get("edges", [])
        if edge_building_intersection(edge, graph, buildings) is not None
    }
    excluded_edges = set()
    result = None
    last_error = None
    for _ in range(len(graph.get("edges", [])) + 1):
        nearest = project_to_nearest_edge(
            graph, gps, transformer, blocked_edges | excluded_edges,
        )
        if nearest is None:
            break
        snap_distance, candidate_edge, projection, _fraction = nearest
        if snap_distance > max_snap_distance_m:
            last_error = RoutingError(
                f"Snap distance {snap_distance:.1f} m exceeds {max_snap_distance_m:g} m.",
                422, "too_far_to_snap",
            )
            break
        connector_blocker = first_building_intersection(
            [gps, projection], buildings,
        )
        if connector_blocker is not None:
            excluded_edges.add(candidate_edge["edge_id"])
            last_error = RoutingError(
                f"GPS-to-route connector crosses building {connector_blocker}.",
                422, "blocked_gps_connector",
            )
            continue
        try:
            result = route_from_gps(
                payload, graph=graph, access_rows=access_rows,
                buildings=buildings, excluded_edge_ids=excluded_edges,
            )
            break
        except RoutingError as error:
            last_error = error
            if error.code in ("no_route", "blocked_gps_connector"):
                excluded_edges.add(candidate_edge["edge_id"])
                continue
            return {"status":"FAILED", "code":error.code, "error":str(error), "validation":"UNVERIFIED"}
    if result is None:
        error = last_error or RoutingError(
            "Không tìm thấy cạnh đi bộ hợp lệ trong đồ thị.", 422, "no_valid_edge",
        )
        return {"status":"FAILED", "code":error.code, "error":str(error), "validation":"UNVERIFIED"}
    # Ghi chú: Gán/cập nhật gps để lưu dữ liệu dùng ở bước tiếp theo.
    gps = [result["gps"]["longitude"], result["gps"]["latitude"]]
    # Ghi chú: Gán/cập nhật projection để lưu dữ liệu dùng ở bước tiếp theo.
    projection = [result["projection"]["longitude"], result["projection"]["latitude"]]
    # Ghi chú: Gán/cập nhật validation để lưu dữ liệu dùng ở bước tiếp theo.
    validation = _connector_validation(
        gps, projection, buildings,
    )
    # Ghi chú: Gán/cập nhật edge_id để lưu dữ liệu dùng ở bước tiếp theo.
    edge_id = result["projection"]["edge_id"]
    # Existing route API includes the destination boundary connector in its
    # distance. Subtract GPS snap to expose the same decomposition as method B.
    # Ghi chú: Gán/cập nhật total để lưu dữ liệu dùng ở bước tiếp theo.
    total = float(result["route"]["distance_meters"])
    # Ghi chú: Gán/cập nhật connector để lưu dữ liệu dùng ở bước tiếp theo.
    connector = float(result["projection"]["distance_meters"])
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if connector > max_snap_distance_m:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return {"status":"FAILED", "code":"too_far_to_snap", "error":f"Snap distance {connector:.1f} m exceeds {max_snap_distance_m:g} m.", "validation":"UNVERIFIED"}
    # Ghi chú: Gán/cập nhật edge_lookup để lưu dữ liệu dùng ở bước tiếp theo.
    edge_lookup = {e["edge_id"]:e for e in graph.get("edges", [])}
    # Ghi chú: Gán/cập nhật edge để lưu dữ liệu dùng ở bước tiếp theo.
    edge = edge_lookup.get(edge_id, {})
    # Ghi chú: Gán/cập nhật route_edges để lưu dữ liệu dùng ở bước tiếp theo.
    route_edges = list(dict.fromkeys(e.split(":gps-")[0] for e in result["route"].get("edge_ids", [])))
    # Ghi chú: Gán/cập nhật route_nodes để lưu dữ liệu dùng ở bước tiếp theo.
    route_nodes = result["route"].get("node_ids", [])
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {"status":"SUCCESS", "validation":validation["status"], "validation_reason":validation["reason"],
            "gps_virtual_node":{"id":result["virtual_node"]["id"],"coordinates":projection},
            "edge_id":edge_id,"t":result["projection"]["t"],"projection_coordinates":projection,
            "connector_distance_meters":round(connector,2),"destination_access_point_id":result["destination"]["access_point_id"],
            "node_ids":route_nodes,"edge_ids":route_edges,"coordinates":result["route"]["coordinates"],
            "route_distance_meters":round(max(0,total-connector),2),"total_distance_meters":round(total,2)}


def _edge_projection_node_continuation(payload, graph, node_candidate, buildings,
                                       max_snap_distance_m=MAX_SNAP_DISTANCE_METERS):
    """Snap with Nearest Edge, then join a viable Nearest Node continuation."""
    if node_candidate.get("status") != "SUCCESS":
        return None
    try:
        gps = [float(payload["longitude"]), float(payload["latitude"])]
        transformer = projection_for_graph(graph)
        blocked_edges = {
            edge.get("edge_id") for edge in graph.get("edges", [])
            if edge_building_intersection(edge, graph, buildings) is not None
        }
        nearest = project_to_nearest_edge(graph, gps, transformer, blocked_edges)
        if nearest is None:
            return None
        snap_distance, edge, projection, fraction = nearest
        if snap_distance > max_snap_distance_m:
            return None

        node_id = node_candidate.get("graph_node_id")
        node_coordinate = graph.get("nodes", {}).get(node_id, {}).get("coordinates")
        node_route_coordinates = node_candidate.get("coordinates") or []
        if not node_coordinate or len(node_route_coordinates) < 2:
            return None

        gps_validation = _connector_validation(
            gps, projection, buildings,
        )
        join_validation = _connector_validation(
            projection, node_coordinate, buildings,
        )
        if gps_validation["status"] == "INVALID" or join_validation["status"] == "INVALID":
            return None
        join_distance = math.dist(transformer.forward(projection), transformer.forward(node_coordinate))
        if join_distance > MAX_NODE_CONNECTOR_DISTANCE_METERS:
            return None

        connector_distance = snap_distance + join_distance
        route_distance = float(node_candidate.get("route_distance_meters", 0.0)) + connector_distance
        coordinates = [gps, projection, list(node_coordinate), *node_route_coordinates[2:]]
        return {
            "status": "SUCCESS",
            "validation": "UNVERIFIED",
            "validation_reason": "Nearest-edge projection joined to the nearest-node route; connector walkability is not field-verified.",
            "routing_variant": "edge_projection_then_nearest_node_continuation",
            "gps_virtual_node": {"id": "GPS_SOURCE", "coordinates": gps},
            "edge_id": edge["edge_id"],
            "t": fraction,
            "projection_coordinates": projection,
            "graph_node_id": node_id,
            "graph_node_coordinates": list(node_coordinate),
            "destination_access_point_id": node_candidate.get("destination_access_point_id"),
            "node_ids": list(node_candidate.get("node_ids", [])),
            "edge_ids": list(node_candidate.get("edge_ids", [])),
            "coordinates": coordinates,
            "connector_distance_meters": round(connector_distance, 2),
            "route_distance_meters": round(route_distance, 2),
            "total_distance_meters": round(route_distance, 2),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


# Ghi chú: Hàm evaluate_gps_routes; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def evaluate_gps_routes(payload, graph=None, access_rows=None, buildings=None,
                        max_snap_distance_m=MAX_SNAP_DISTANCE_METERS,
                        max_node_distance_m=MAX_NODE_CONNECTOR_DISTANCE_METERS):
    """Run both routing approaches against one immutable graph/access snapshot."""
    # Ghi chú: Gán/cập nhật (lat, lon, accuracy, source, destination) để lưu dữ liệu dùng ở bước tiếp theo.
    lat, lon, accuracy, source, destination = _validate_payload(payload)
    # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
    graph = graph if graph is not None else json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    # Ghi chú: Gán/cập nhật access_rows để lưu dữ liệu dùng ở bước tiếp theo.
    access_rows = read_access_rows() if access_rows is None else access_rows
    # Ghi chú: Gán/cập nhật buildings để lưu dữ liệu dùng ở bước tiếp theo.
    buildings = _load_building_geometries() if buildings is None else buildings
    # Drop access connectors that cross building interiors before either GPS
    # candidate is allowed to route to the destination.
    places = filter_access_points(get_places(graph, access_rows), graph, buildings)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if destination not in places:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise RoutingError("Địa điểm đích không tồn tại hoặc chưa có cổng tiếp cận được xác nhận.", 404, "unknown_destination")
    if not places[destination]:
        raise RoutingError("All confirmed destination access connectors cross known building footprints.", 422, "blocked_access")
    # Ghi chú: Gán/cập nhật places_for_destination để lưu dữ liệu dùng ở bước tiếp theo.
    places_for_destination = places[destination]
    # Ghi chú: Gán/cập nhật transformer để lưu dữ liệu dùng ở bước tiếp theo.
    transformer = projection_for_graph(graph)
    # Ghi chú: Gán/cập nhật gps để lưu dữ liệu dùng ở bước tiếp theo.
    gps = [lon,lat]
    # Ghi chú: Gán/cập nhật edge_payload để lưu dữ liệu dùng ở bước tiếp theo.
    edge_payload = {"latitude":lat,"longitude":lon,"accuracy":accuracy,"location_source":source,"destination_place_id":destination}
    # Ghi chú: Gán/cập nhật started để lưu dữ liệu dùng ở bước tiếp theo.
    started = time.perf_counter()
    # Ghi chú: Gán/cập nhật edge để lưu dữ liệu dùng ở bước tiếp theo.
    edge = _edge_candidate(edge_payload, graph, access_rows, buildings, max_snap_distance_m)
    # Ghi chú: Gán/cập nhật edge['computation_time_ms'] để lưu dữ liệu dùng ở bước tiếp theo.
    edge["computation_time_ms"] = round((time.perf_counter()-started)*1000, 3)
    # Ghi chú: Gán/cập nhật started để lưu dữ liệu dùng ở bước tiếp theo.
    started = time.perf_counter()
    # Include the same confirmed-access extraction performed internally by
    # route_from_gps so per-method times include comparable routing setup.
    # Ghi chú: Gán/cập nhật node_places để lưu dữ liệu dùng ở bước tiếp theo.
    node_places = places
    # Ghi chú: Gán/cập nhật node để lưu dữ liệu dùng ở bước tiếp theo.
    node = _nearest_node(graph,gps,node_places.get(destination,[]),transformer,buildings,max_node_distance_m)
    # Ghi chú: Gán/cập nhật node['computation_time_ms'] để lưu dữ liệu dùng ở bước tiếp theo.
    node["computation_time_ms"] = round((time.perf_counter()-started)*1000, 3)
    if edge.get("status") == "FAILED" and edge.get("code") == "no_route" and node.get("status") == "SUCCESS":
        continuation = _edge_projection_node_continuation(
            edge_payload, graph, node, buildings, max_snap_distance_m,
        )
        if continuation is not None:
            continuation["computation_time_ms"] = edge.get("computation_time_ms", 0.0)
            edge = continuation
    # Ghi chú: Gán/cập nhật candidates để lưu dữ liệu dùng ở bước tiếp theo.
    candidates = {"nearest_edge":edge,"nearest_node":node}
    # Ghi chú: Gán/cập nhật viable để lưu dữ liệu dùng ở bước tiếp theo.
    viable = [(name,item) for name,item in candidates.items() if item.get("status")=="SUCCESS" and item.get("validation")!="INVALID"]
    # Ghi chú: Gán/cập nhật (selected, reason) để lưu dữ liệu dùng ở bước tiếp theo.
    selected, reason = None, "Both candidates failed routing or intersect known buildings."
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if viable:
        viable.sort(key=lambda pair:(pair[1]["validation"]!="VERIFIED",pair[1]["total_distance_meters"],pair[1]["connector_distance_meters"]))
        # Ghi chú: Gán/cập nhật selected để lưu dữ liệu dùng ở bước tiếp theo.
        selected = viable[0][0]
        # Ghi chú: Gán/cập nhật both_unverified để lưu dữ liệu dùng ở bước tiếp theo.
        both_unverified = len(viable)==2 and all(item["validation"]=="UNVERIFIED" for _,item in viable)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if len(viable)==1:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Only candidate without a confirmed geographic violation has a route; connector walkability may remain unverified."
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        elif both_unverified and viable[0][1]["total_distance_meters"] < viable[1][1]["total_distance_meters"]:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Both candidates are UNVERIFIED; selected shorter total distance for comparison only. Pedestrian access is not field-verified."
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        elif both_unverified and viable[0][1]["connector_distance_meters"] < viable[1][1]["connector_distance_meters"]:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Both candidates are UNVERIFIED and total distance tied; selected shorter connector for comparison only. Pedestrian access is not field-verified."
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        elif both_unverified:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Both candidates are UNVERIFIED and their costs tie; nearest_edge is a stable tie-break only. Pedestrian access is not field-verified."
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        elif viable[0][1]["validation"] != viable[1][1]["validation"]:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Selected the candidate with stronger geographic validation."
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        elif viable[0][1]["total_distance_meters"] < viable[1][1]["total_distance_meters"]:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Both candidates have the same validation level; selected shorter total distance."
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        elif viable[0][1]["connector_distance_meters"] < viable[1][1]["connector_distance_meters"]:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Total distances tied; selected the shorter connector."
        else:
            # Ghi chú: Gán/cập nhật reason để lưu dữ liệu dùng ở bước tiếp theo.
            reason = "Validation, total distance, and connector distance tied; chose nearest_edge as stable tie-break."
    # Ghi chú: Gán/cập nhật selected_route để lưu dữ liệu dùng ở bước tiếp theo.
    selected_route = None
    # Ghi chú: Gán/cập nhật status để lưu dữ liệu dùng ở bước tiếp theo.
    status = "NO_VALID_ROUTE"
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if selected:
        # Ghi chú: Gán/cập nhật chosen để lưu dữ liệu dùng ở bước tiếp theo.
        chosen = candidates[selected]
        # Ghi chú: Gán/cập nhật selected_route để lưu dữ liệu dùng ở bước tiếp theo.
        selected_route = {"method":selected,"coordinates":chosen["coordinates"],"node_ids":chosen.get("node_ids",[]),"edge_ids":chosen.get("edge_ids",[]),"distance_meters":chosen["total_distance_meters"],"destination_access_point_id":chosen["destination_access_point_id"]}
        # Ghi chú: Gán/cập nhật status để lưu dữ liệu dùng ở bước tiếp theo.
        status = "SUCCESS"
    # Ghi chú: Gán/cập nhật warning để lưu dữ liệu dùng ở bước tiếp theo.
    warning = ("Selected route is UNVERIFIED; do not treat it as a field-verified safe walking route."
               if selected and candidates[selected].get("validation")=="UNVERIFIED" else None)
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {"success":status=="SUCCESS","evaluation":{"status":status,"selected_method":selected,"selection_reason":reason,"warning":warning,
            "thresholds":{"max_snap_distance_meters":max_snap_distance_m,"max_node_connector_distance_meters":max_node_distance_m,
                          "max_gps_accuracy_meters":MAX_GPS_ACCURACY_METERS}},
            "gps":{"latitude":lat,"longitude":lon,"accuracy_meters":accuracy,"location_source":source},
            "candidates":candidates,"selected_route":selected_route}
