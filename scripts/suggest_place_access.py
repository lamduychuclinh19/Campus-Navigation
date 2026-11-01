#!/usr/bin/env python3
"""Suggest, but do not assume, pedestrian access links from places to graph.

For each Polygon/MultiPolygon in data/nodes/*.geojson, list several nearby
routing graph nodes and the closest point on the polygon boundary. Review
each candidate against actual gates before using it for routing.

Run: python scripts/suggest_place_access.py
"""

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODES_DIR = ROOT / "data" / "nodes"
GRAPH_PATH = ROOT / "data" / "routing" / "graph.json"
PREVIOUS_OUTPUT_PATH = ROOT / "data" / "routing" / "place_access_candidates.csv"
OUTPUT_PATH = ROOT / "data" / "routing" / "place_access_candidates_multi.csv"
EARTH_RADIUS_M = 6_371_000.0
MAX_DISTANCE_M = 40.0
MAX_CANDIDATES_PER_PLACE = 6


def local_xy(point, origin_lat):
    """Approximate local metre coordinates for this small campus area."""
    lon, lat = point[:2]
    x = math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat))
    y = math.radians(lat) * EARTH_RADIUS_M
    return x, y


def nearest_point_on_segment(point, a, b, origin_lat):
    px, py = local_xy(point, origin_lat)
    ax, ay = local_xy(a, origin_lat)
    bx, by = local_xy(b, origin_lat)
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    x, y = ax + t * dx, ay + t * dy
    distance = math.hypot(px - x, py - y)
    lon = math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat))))
    lat = math.degrees(y / EARTH_RADIUS_M)
    return distance, [lon, lat]


def polygon_rings(geometry):
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return coords[:1]  # Outer ring; ignore holes when finding the boundary.
    if kind == "MultiPolygon":
        return [polygon[0] for polygon in coords if polygon]
    return []


def read_csv_rows(path):
    """Read UTF-8 CSV first, with a Windows Vietnamese encoding fallback."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1258")
    return list(csv.DictReader(text.splitlines()))


def main():
    if not GRAPH_PATH.exists():
        raise SystemExit("Graph not found. Run: python scripts/build_routing_graph.py")
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    with (ROOT / "data" / "routing" / "graph_nodes.csv").open("r", newline="", encoding="utf-8-sig") as file:
        component_by_node = {row["node_id"]: row["component"] for row in csv.DictReader(file)}

    graph_nodes = [
        (node_id, node["coordinates"], component_by_node.get(node_id, ""))
        for node_id, node in graph["nodes"].items()
    ]
    # Keep decisions already made by the user when refreshing suggestions.
    previous_decisions = {}
    for decision_file in (OUTPUT_PATH, PREVIOUS_OUTPUT_PATH):
        if decision_file.exists():
            try:
                prior_rows = read_csv_rows(decision_file)
            except (OSError, UnicodeDecodeError):
                continue
            for row in prior_rows:
                key = (row.get("place_id", ""), row.get("graph_node_candidate", ""))
                previous_decisions[key] = (row.get("confirmed_access", "REVIEW"), row.get("notes", ""))

    rows = []
    for path in sorted(NODES_DIR.glob("*.geojson")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skip {path.name}: {error}")
            continue

        polygon_index = 0
        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            rings = polygon_rings(geometry)
            if not rings:
                continue
            polygon_index += 1
            properties = feature.get("properties") or {}
            fallback_id = path.stem if polygon_index == 1 else f"{path.stem}_{polygon_index}"
            place_id = properties.get("id") or fallback_id

            nearest_by_node = {}
            for ring in rings:
                if len(ring) < 2:
                    continue
                origin_lat = sum(float(point[1]) for point in ring) / len(ring)
                for graph_node_id, graph_coord, component in graph_nodes:
                    nearest_distance = math.inf
                    nearest_coordinate = None
                    for a, b in zip(ring, ring[1:]):
                        distance, point = nearest_point_on_segment(graph_coord, a, b, origin_lat)
                        if distance < nearest_distance:
                            nearest_distance, nearest_coordinate = distance, point
                    if nearest_coordinate is not None and nearest_distance <= MAX_DISTANCE_M:
                        candidate = (nearest_distance, graph_node_id, graph_coord, component, nearest_coordinate)
                        if graph_node_id not in nearest_by_node or nearest_distance < nearest_by_node[graph_node_id][0]:
                            nearest_by_node[graph_node_id] = candidate

            candidates = sorted(nearest_by_node.values())[:MAX_CANDIDATES_PER_PLACE]
            if not candidates:
                continue
            for rank, (distance, graph_node_id, graph_coord, component, access_coord) in enumerate(candidates, start=1):
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

    fields = ["place_id", "file", "candidate_rank", "graph_node_candidate", "component", "distance_to_polygon_m",
              "graph_node_lon", "graph_node_lat", "projected_boundary_lon", "projected_boundary_lat",
              "confirmed_access", "notes"]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Access candidates: {len(rows)} across {len({row['place_id'] for row in rows})} places")
    print(f"Showing up to {MAX_CANDIDATES_PER_PLACE} graph nodes within {MAX_DISTANCE_M:g} m per place")
    print(f"Review file: {OUTPUT_PATH}")
    print("No access links were automatically added to the routing graph.")


if __name__ == "__main__":
    main()
