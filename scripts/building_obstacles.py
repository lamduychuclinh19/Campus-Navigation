"""Geometry checks for route segments against known building footprints.

Boundary contact is allowed. A segment is blocked only when some open part of
it lies inside the filled portion of a building polygon (holes stay traversable).
"""

import json
import math
from pathlib import Path


POINT_TOLERANCE_DEGREES = 5e-7
# The project owner confirmed these mapped corridors pass through the named
# footprints. The exception is used for mapped graph edges and the GPS-to-path
# connector; building access connectors remain subject to the full check.
CONFIRMED_INDOOR_PASSAGE_BUILDINGS = frozenset({"B", "C", "Cantin", "KLF"})


def load_building_geometries(directory):
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


def _point_on_segment(point, start, end, tolerance=POINT_TOLERANCE_DEGREES):
    cross = ((point[1] - start[1]) * (end[0] - start[0])
             - (point[0] - start[0]) * (end[1] - start[1]))
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length == 0 or abs(cross) > tolerance * length:
        return False
    return (min(start[0], end[0]) - tolerance <= point[0] <= max(start[0], end[0]) + tolerance
            and min(start[1], end[1]) - tolerance <= point[1] <= max(start[1], end[1]) + tolerance)


def _inside_ring(point, ring, tolerance=POINT_TOLERANCE_DEGREES):
    inside = False
    for start, end in zip(ring, ring[1:]):
        if _point_on_segment(point, start, end, tolerance):
            return False
        if (start[1] > point[1]) != (end[1] > point[1]):
            crossing_x = ((end[0] - start[0]) * (point[1] - start[1])
                          / (end[1] - start[1]) + start[0])
            if point[0] < crossing_x:
                inside = not inside
    return inside


def _inside_polygon(point, rings):
    if not rings or any(_point_on_segment(point, a, b)
                        for ring in rings for a, b in zip(ring, ring[1:])):
        return False
    return (_inside_ring(point, rings[0])
            and not any(_inside_ring(point, hole) for hole in rings[1:]))


def _intersection_parameters(start, end, a, b):
    rx, ry = end[0] - start[0], end[1] - start[1]
    sx, sy = b[0] - a[0], b[1] - a[1]
    denominator = rx * sy - ry * sx
    qx, qy = a[0] - start[0], a[1] - start[1]
    eps = 1e-14
    if abs(denominator) > eps:
        t = (qx * sy - qy * sx) / denominator
        u = (qx * ry - qy * rx) / denominator
        return [max(0.0, min(1.0, t))] if -eps <= t <= 1 + eps and -eps <= u <= 1 + eps else []
    if abs(qx * ry - qy * rx) > eps:
        return []
    length_squared = rx * rx + ry * ry
    if length_squared <= 1e-30:
        return []
    first = (qx * rx + qy * ry) / length_squared
    second = ((b[0] - start[0]) * rx + (b[1] - start[1]) * ry) / length_squared
    low, high = max(0.0, min(first, second)), min(1.0, max(first, second))
    return [low, high] if low <= high + eps else []


def _segment_crosses_polygon_interior(start, end, rings):
    if not rings:
        return False
    if math.dist(start, end) <= 1e-14:
        return _inside_polygon(start, rings)
    parameters = [0.0, 1.0]
    for ring in rings:
        for a, b in zip(ring, ring[1:]):
            parameters.extend(_intersection_parameters(start, end, a, b))
    parameters = sorted(set(parameters))
    for low, high in zip(parameters, parameters[1:]):
        if high - low <= 1e-12:
            continue
        fraction = (low + high) / 2
        sample = (start[0] + fraction * (end[0] - start[0]),
                  start[1] + fraction * (end[1] - start[1]))
        if _inside_polygon(sample, rings):
            return True
    return False


def first_building_intersection(line_coordinates, buildings, allowed_building_ids=None):
    """Return the first blocking building ID, or None for a clear polyline."""
    if len(line_coordinates) < 2:
        return None
    allowed_building_ids = allowed_building_ids or frozenset()
    points = [(float(point[0]), float(point[1])) for point in line_coordinates]
    for building_id, geometry in buildings:
        if building_id in allowed_building_ids:
            continue
        coordinates = geometry.get("coordinates", [])
        polygons = [coordinates] if geometry.get("type") == "Polygon" else coordinates
        for polygon in polygons:
            rings = [[(float(point[0]), float(point[1])) for point in ring]
                     for ring in polygon if len(ring) >= 2]
            if any(_segment_crosses_polygon_interior(start, end, rings)
                   for start, end in zip(points, points[1:])):
                return building_id
    return None


def edge_building_intersection(
    edge, graph, buildings,
    allowed_building_ids=CONFIRMED_INDOOR_PASSAGE_BUILDINGS,
):
    coordinates = edge.get("coordinates")
    if not coordinates:
        coordinates = [graph["nodes"][edge["from"]]["coordinates"],
                       graph["nodes"][edge["to"]]["coordinates"]]
    return first_building_intersection(coordinates, buildings, allowed_building_ids)


def filter_access_points(places, graph, buildings):
    """Drop confirmed access connectors that cross a known building interior."""
    filtered = {}
    for place_id, accesses in places.items():
        kept = []
        for access in accesses:
            node = graph.get("nodes", {}).get(access.get("node"), {})
            coordinate = node.get("coordinates")
            boundary = access.get("boundary")
            if not coordinate or not boundary:
                continue
            if first_building_intersection([boundary, coordinate], buildings) is None:
                kept.append(access)
        filtered[place_id] = kept
    return filtered
