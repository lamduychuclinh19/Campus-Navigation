"""Evaluate edge-projection and graph-node GPS routing on one graph snapshot."""

import json
import math
from pathlib import Path
import time

from gps_routing import (
    DATA, GRAPH_PATH, MAX_GPS_ACCURACY_METERS, MAX_SNAP_DISTANCE_METERS,
    RoutingError, dijkstra, get_places, projection_for_graph, read_access_rows,
    route_from_gps, valid_lonlat,
)

# Deliberately uses the existing 50 m snap envelope for a comparable connector
# budget. This is an operational cap, not a campus-calibrated pedestrian limit.
MAX_NODE_CONNECTOR_DISTANCE_METERS = 50.0
BUILDING_DIR = DATA / "nodes"
EPSILON = 1e-8
# Source building rings are generally stored to six decimal places. This
# degree tolerance is about 5 cm on campus: it absorbs coordinate rounding at
# a wall while still treating metre-scale polygon interiors as obstructions.
POINT_TOLERANCE_DEGREES = 5e-7


def _load_building_geometries(directory=BUILDING_DIR):
    geometries = []
    for path in sorted(Path(directory).glob("*.geojson")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for feature in data.get("features", []):
                geometry = feature.get("geometry") or {}
                if geometry.get("type") in ("Polygon", "MultiPolygon"):
                    geometries.append((path.stem, geometry))
        except (OSError, ValueError, TypeError):
            continue
    return geometries


def _point_on_segment(p, a, b, tolerance=POINT_TOLERANCE_DEGREES):
    cross = (p[1]-a[1])*(b[0]-a[0])-(p[0]-a[0])*(b[1]-a[1])
    segment_length = math.hypot(b[0]-a[0],b[1]-a[1])
    if segment_length == 0 or abs(cross) > tolerance*segment_length:
        return False
    return (min(a[0],b[0])-tolerance <= p[0] <= max(a[0],b[0])+tolerance and
            min(a[1],b[1])-tolerance <= p[1] <= max(a[1],b[1])+tolerance)


def _inside_ring(point, ring, tolerance=POINT_TOLERANCE_DEGREES):
    """Return whether a point is strictly inside a ring (boundary excluded)."""
    inside = False
    for a, b in zip(ring, ring[1:]):
        if _point_on_segment(point, a, b, tolerance):
            return False
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = (b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0]
            if point[0] < x:
                inside = not inside
    return inside


def _segment_intersection_parameters(start, end, a, b):
    """Return parameters on start→end where two segments intersect."""
    rx, ry = end[0]-start[0], end[1]-start[1]
    sx, sy = b[0]-a[0], b[1]-a[1]
    denominator = rx*sy-ry*sx
    qx, qy = a[0]-start[0], a[1]-start[1]
    cross_tolerance = 1e-14
    if abs(denominator) > cross_tolerance:
        t = (qx*sy-qy*sx)/denominator
        u = (qx*ry-qy*rx)/denominator
        if -EPSILON <= t <= 1+EPSILON and -EPSILON <= u <= 1+EPSILON:
            return [max(0.0,min(1.0,t))]
        return []
    if abs(qx*ry-qy*rx) > cross_tolerance:
        return []
    length_squared = rx*rx+ry*ry
    if length_squared <= 1e-30:
        return []
    ta = (qx*rx+qy*ry)/length_squared
    q2x, q2y = b[0]-start[0], b[1]-start[1]
    tb = (q2x*rx+q2y*ry)/length_squared
    low, high = max(0.0,min(ta,tb)), min(1.0,max(ta,tb))
    return [low,high] if low <= high+EPSILON else []


def _inside_polygon(point, rings, tolerance=POINT_TOLERANCE_DEGREES):
    if not rings or any(_point_on_segment(point,a,b,tolerance) for ring in rings for a,b in zip(ring,ring[1:])):
        return False
    return _inside_ring(point,rings[0],tolerance) and not any(_inside_ring(point,hole,tolerance) for hole in rings[1:])


def _line_intersects_polygon(start, end, rings):
    if not rings:
        return False
    # A zero-length connector on a polygon boundary merely touches the
    # footprint. Reject it only when the point is strictly inside the fill.
    if math.dist(start,end) <= 1e-14:
        return _inside_polygon(start,rings)
    parameters = [0.0,1.0]
    for ring in rings:
        for a,b in zip(ring,ring[1:]):
            parameters.extend(_segment_intersection_parameters(start,end,a,b))
    parameters=sorted(set(parameters))
    # Test the open intervals between boundary crossings. Merely touching or
    # following a polygon boundary is not treated as travelling through it.
    for low,high in zip(parameters,parameters[1:]):
        if high-low <= 1e-12:
            continue
        t=(low+high)/2
        sample=(start[0]+t*(end[0]-start[0]),start[1]+t*(end[1]-start[1]))
        # Interior samples need a much tighter tolerance than endpoints: do
        # not let the source-rounding allowance hide a real connector crossing.
        if _inside_polygon(sample,rings,tolerance=1e-10):
            return True
    return False


def _connector_validation(start_lonlat, end_lonlat, buildings):
    for building_id, geometry in buildings:
        kind, coordinates = geometry["type"], geometry.get("coordinates", [])
        polygons = [coordinates] if kind == "Polygon" else coordinates
        for polygon in polygons:
            rings = [[(float(x),float(y)) for x,y,*_ in ring] for ring in polygon if len(ring) >= 2]
            if rings and _line_intersects_polygon(tuple(start_lonlat), tuple(end_lonlat), rings):
                return {"status":"INVALID", "reason":f"connector_intersects_building:{building_id}"}
    return {"status":"UNVERIFIED", "reason":"No declared building intersection; pedestrian access is not field-verified and no restricted-area layer is available."}


def _validate_payload(payload):
    if not isinstance(payload, dict):
        raise RoutingError("Request JSON không hợp lệ.")
    try:
        lat, lon = float(payload["latitude"]), float(payload["longitude"])
        raw_accuracy = payload.get("accuracy")
        accuracy = None if raw_accuracy is None else float(raw_accuracy)
    except (KeyError, TypeError, ValueError):
        raise RoutingError("Cần latitude, longitude và accuracy hợp lệ.")
    source = payload.get("location_source", "browser")
    if source not in ("browser", "map"):
        raise RoutingError("location_source phải là browser hoặc map.")
    if not valid_lonlat(lon, lat) or (accuracy is not None and (not math.isfinite(accuracy) or accuracy < 0)):
        raise RoutingError("Tọa độ GPS hoặc accuracy không hợp lệ.")
    if source == "browser" and (accuracy is None or accuracy > MAX_GPS_ACCURACY_METERS):
        raise RoutingError(f"GPS không đạt ngưỡng accuracy {MAX_GPS_ACCURACY_METERS:g} m.", 422, "poor_accuracy")
    if source == "map" and accuracy is not None:
        raise RoutingError("Vị trí mô phỏng không có accuracy GPS; gửi accuracy=null.")
    destination = str(payload.get("destination_place_id", "")).strip()
    return lat, lon, accuracy, source, destination


def _nearest_node(graph, gps_lonlat, destination_nodes, transformer, buildings, max_distance):
    gps_xy = transformer.forward(gps_lonlat)
    active = {node_id: [] for node_id in graph.get("nodes", {})}
    for edge in graph.get("edges", []):
        try:
            weight = float(edge["length_m"])
            if weight <= 0 or not math.isfinite(weight):
                continue
            u, v = edge["from"], edge["to"]
            active[u].append((v, weight, edge["edge_id"]))
            if not graph.get("directed", False):
                active[v].append((u, weight, edge["edge_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    candidates = []
    for node_id, node in graph.get("nodes", {}).items():
        if not active.get(node_id):
            continue
        coord = node.get("coordinates")
        if not isinstance(coord, list) or len(coord) < 2:
            continue
        gap = math.dist(gps_xy, transformer.forward(coord))
        if gap <= max_distance:
            validation = _connector_validation(gps_lonlat, coord, buildings)
            candidates.append((validation["status"] == "INVALID", gap, node_id, coord, validation))
    candidates.sort(key=lambda item:(item[0], item[1], item[2]))
    if not candidates:
        return {"status":"FAILED", "code":"no_node_candidate", "error":f"No active graph node within {max_distance:g} m.", "validation":"UNVERIFIED"}
    rejected = [{"node_id":node_id,"connector_distance_meters":round(gap,2),"validation":validation["status"],"reason":validation["reason"]}
                for invalid,gap,node_id,_coord,validation in candidates if invalid]
    adjacency = dict(active)
    virtual = "GPS_SOURCE_NODE"
    # Try viable node candidates in increasing distance; connectivity to any
    # confirmed destination gate is checked before one is selected.
    routes = []
    for invalid, connector, node_id, coord, validation in candidates:
        if invalid:
            continue
        adjacency[virtual] = [(node_id, connector, "GPS_CONNECTOR")]
        distances, previous, _ = dijkstra(adjacency, [(virtual, 0.0)])
        reachable = [(distances[a["node"]]+a["connector_m"], a) for a in destination_nodes if a["node"] in distances]
        if not reachable:
            continue
        total, target = min(reachable, key=lambda item:item[0])
        nodes = [target["node"]]
        while nodes[-1] != virtual and nodes[-1] in previous:
            nodes.append(previous[nodes[-1]][0])
        if nodes[-1] != virtual:
            continue
        nodes.reverse()
        edge_ids = []
        for current in nodes[1:]:
            edge_ids.append(previous[current][1])
        graph_nodes = [n for n in nodes if n != virtual]
        coords = [list(gps_lonlat), list(coord)]
        for index in range(1, len(graph_nodes)):
            edge = next((e for e in graph["edges"] if e["edge_id"] == edge_ids[index]), None)
            if edge:
                part = list(edge.get("coordinates") or [graph["nodes"][edge["from"]]["coordinates"], graph["nodes"][edge["to"]]["coordinates"]])
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
    if routes:
        return min(routes,key=lambda item:(item["validation"]!="VERIFIED",item["total_distance_meters"],item["connector_distance_meters"]))
    return {"status":"FAILED", "code":"no_route", "error":"No candidate node reaches a confirmed destination access point.", "validation":"UNVERIFIED"}


def _edge_candidate(payload, graph, access_rows, buildings, max_snap_distance_m=MAX_SNAP_DISTANCE_METERS):
    try:
        result = route_from_gps(payload, graph=graph, access_rows=access_rows)
    except RoutingError as error:
        return {"status":"FAILED", "code":error.code, "error":str(error), "validation":"UNVERIFIED"}
    gps = [result["gps"]["longitude"], result["gps"]["latitude"]]
    projection = [result["projection"]["longitude"], result["projection"]["latitude"]]
    validation = _connector_validation(gps, projection, buildings)
    edge_id = result["projection"]["edge_id"]
    # Existing route API includes the destination boundary connector in its
    # distance. Subtract GPS snap to expose the same decomposition as method B.
    total = float(result["route"]["distance_meters"])
    connector = float(result["projection"]["distance_meters"])
    if connector > max_snap_distance_m:
        return {"status":"FAILED", "code":"too_far_to_snap", "error":f"Snap distance {connector:.1f} m exceeds {max_snap_distance_m:g} m.", "validation":"UNVERIFIED"}
    edge_lookup = {e["edge_id"]:e for e in graph.get("edges", [])}
    edge = edge_lookup.get(edge_id, {})
    route_edges = list(dict.fromkeys(e.split(":gps-")[0] for e in result["route"].get("edge_ids", [])))
    route_nodes = result["route"].get("node_ids", [])
    return {"status":"SUCCESS", "validation":validation["status"], "validation_reason":validation["reason"],
            "gps_virtual_node":{"id":result["virtual_node"]["id"],"coordinates":projection},
            "edge_id":edge_id,"t":result["projection"]["t"],"projection_coordinates":projection,
            "connector_distance_meters":round(connector,2),"destination_access_point_id":result["destination"]["access_point_id"],
            "node_ids":route_nodes,"edge_ids":route_edges,"coordinates":result["route"]["coordinates"],
            "route_distance_meters":round(max(0,total-connector),2),"total_distance_meters":round(total,2)}


def evaluate_gps_routes(payload, graph=None, access_rows=None, buildings=None,
                        max_snap_distance_m=MAX_SNAP_DISTANCE_METERS,
                        max_node_distance_m=MAX_NODE_CONNECTOR_DISTANCE_METERS):
    """Run both routing approaches against one immutable graph/access snapshot."""
    lat, lon, accuracy, source, destination = _validate_payload(payload)
    graph = graph if graph is not None else json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    access_rows = read_access_rows() if access_rows is None else access_rows
    places = get_places(graph, access_rows)
    if destination not in places:
        raise RoutingError("Địa điểm đích không tồn tại hoặc chưa có cổng tiếp cận được xác nhận.", 404, "unknown_destination")
    places_for_destination = places[destination]
    buildings = _load_building_geometries() if buildings is None else buildings
    transformer = projection_for_graph(graph)
    gps = [lon,lat]
    edge_payload = {"latitude":lat,"longitude":lon,"accuracy":accuracy,"location_source":source,"destination_place_id":destination}
    started = time.perf_counter()
    edge = _edge_candidate(edge_payload, graph, access_rows, buildings, max_snap_distance_m)
    edge["computation_time_ms"] = round((time.perf_counter()-started)*1000, 3)
    started = time.perf_counter()
    # Include the same confirmed-access extraction performed internally by
    # route_from_gps so per-method times include comparable routing setup.
    node_places = get_places(graph, access_rows)
    node = _nearest_node(graph,gps,node_places.get(destination,[]),transformer,buildings,max_node_distance_m)
    node["computation_time_ms"] = round((time.perf_counter()-started)*1000, 3)
    candidates = {"nearest_edge":edge,"nearest_node":node}
    viable = [(name,item) for name,item in candidates.items() if item.get("status")=="SUCCESS" and item.get("validation")!="INVALID"]
    selected, reason = None, "Both candidates failed routing or intersect known buildings."
    if viable:
        viable.sort(key=lambda pair:(pair[1]["validation"]!="VERIFIED",pair[1]["total_distance_meters"],pair[1]["connector_distance_meters"]))
        selected = viable[0][0]
        both_unverified = len(viable)==2 and all(item["validation"]=="UNVERIFIED" for _,item in viable)
        if len(viable)==1:
            reason = "Only candidate without a confirmed geographic violation has a route; connector walkability may remain unverified."
        elif both_unverified and viable[0][1]["total_distance_meters"] < viable[1][1]["total_distance_meters"]:
            reason = "Both candidates are UNVERIFIED; selected shorter total distance for comparison only. Pedestrian access is not field-verified."
        elif both_unverified and viable[0][1]["connector_distance_meters"] < viable[1][1]["connector_distance_meters"]:
            reason = "Both candidates are UNVERIFIED and total distance tied; selected shorter connector for comparison only. Pedestrian access is not field-verified."
        elif both_unverified:
            reason = "Both candidates are UNVERIFIED and their costs tie; nearest_edge is a stable tie-break only. Pedestrian access is not field-verified."
        elif viable[0][1]["validation"] != viable[1][1]["validation"]:
            reason = "Selected the candidate with stronger geographic validation."
        elif viable[0][1]["total_distance_meters"] < viable[1][1]["total_distance_meters"]:
            reason = "Both candidates have the same validation level; selected shorter total distance."
        elif viable[0][1]["connector_distance_meters"] < viable[1][1]["connector_distance_meters"]:
            reason = "Total distances tied; selected the shorter connector."
        else:
            reason = "Validation, total distance, and connector distance tied; chose nearest_edge as stable tie-break."
    selected_route = None
    status = "NO_VALID_ROUTE"
    if selected:
        chosen = candidates[selected]
        selected_route = {"method":selected,"coordinates":chosen["coordinates"],"node_ids":chosen.get("node_ids",[]),"edge_ids":chosen.get("edge_ids",[]),"distance_meters":chosen["total_distance_meters"],"destination_access_point_id":chosen["destination_access_point_id"]}
        status = "SUCCESS"
    warning = ("Selected route is UNVERIFIED; do not treat it as a field-verified safe walking route."
               if selected and candidates[selected].get("validation")=="UNVERIFIED" else None)
    return {"success":status=="SUCCESS","evaluation":{"status":status,"selected_method":selected,"selection_reason":reason,"warning":warning,
            "thresholds":{"max_snap_distance_meters":max_snap_distance_m,"max_node_connector_distance_meters":max_node_distance_m,
                          "max_gps_accuracy_meters":MAX_GPS_ACCURACY_METERS}},
            "gps":{"latitude":lat,"longitude":lon,"accuracy_meters":accuracy,"location_source":source},
            "candidates":candidates,"selected_route":selected_route}
