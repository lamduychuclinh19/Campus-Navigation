#!/usr/bin/env python3
"""Find a shortest walking route between places using confirmed access links.

Run, for example:
    python scripts/route_between_places.py B KTH

Access links marked yes in place_access_candidates_multi.csv are treated as
candidate entrances. Place polygons are not used as graph shortcuts: Dijkstra
runs on the walkway graph, seeded from all confirmed origin gates, and chooses
the best confirmed destination gate.
"""

import argparse
import csv
import heapq
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ROUTING = DATA / "routing"
GRAPH_PATH = ROUTING / "graph.json"
ACCESS_PATH = ROUTING / "place_access_candidates_multi.csv"
OUTPUT_PATH = ROUTING / "route_result.geojson"
EARTH_RADIUS_M = 6_371_000.0


def read_access_rows(path):
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = path.read_text(encoding="cp1258")
    return list(csv.DictReader(content.splitlines()))


def distance_m(a, b):
    lon1, lat1 = map(math.radians, a[:2])
    lon2, lat2 = map(math.radians, b[:2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def build_adjacency(graph):
    adjacency = {node_id: [] for node_id in graph["nodes"]}
    for edge in graph["edges"]:
        adjacency[edge["from"]].append((edge["to"], edge["length_m"], edge["edge_id"]))
        adjacency[edge["to"]].append((edge["from"], edge["length_m"], edge["edge_id"]))
    return adjacency


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Run Dijkstra between two places.")
    parser.add_argument("start", nargs="?", help="Start place_id, e.g. B")
    parser.add_argument("destination", nargs="?", help="Destination place_id, e.g. KTH")
    parser.add_argument("--start-gate", help="Use this graph node as the specific start gate, e.g. N007")
    parser.add_argument("--destination-gate", help="Use this graph node as the specific destination gate")
    args = parser.parse_args()

    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    rows = read_access_rows(ACCESS_PATH)
    places = {}
    for row in rows:
        if row.get("confirmed_access", "").strip().lower() == "yes":
            node_id = row.get("graph_node_candidate", "").strip()
            if node_id not in graph["nodes"]:
                continue
            try:
                boundary = [float(row["projected_boundary_lon"]), float(row["projected_boundary_lat"])]
                graph_coord = graph["nodes"][node_id]["coordinates"]
            except (KeyError, TypeError, ValueError):
                continue
            connector_length = distance_m(boundary, graph_coord)
            place_id = row.get("place_id", "").strip()
            places.setdefault(place_id, []).append({
                "node": node_id,
                "boundary": boundary,
                "connector_m": connector_length,
            })

    if not args.start or not args.destination:
        print("Places with at least one confirmed access:")
        for place_id, access in sorted(places.items()):
            gates = ", ".join(sorted({item["node"] for item in access}))
            print(f"  {place_id}: {gates}")
        print("Usage: python scripts/route_between_places.py START_ID DESTINATION_ID [--start-gate NODE] [--destination-gate NODE]")
        return 0

    start, destination = args.start, args.destination
    if start not in places or destination not in places:
        print(f"Place IDs with confirmed access: {', '.join(sorted(places))}")
        raise SystemExit("Unknown place, or it has no confirmed access marked yes.")
    if start == destination:
        raise SystemExit("Start and destination must be different places.")

    start_accesses = places[start]
    destination_accesses = places[destination]
    if args.start_gate:
        start_accesses = [access for access in start_accesses if access["node"] == args.start_gate]
        if not start_accesses:
            raise SystemExit(f"{args.start_gate} is not a confirmed access gate for {start}.")
    if args.destination_gate:
        destination_accesses = [access for access in destination_accesses if access["node"] == args.destination_gate]
        if not destination_accesses:
            raise SystemExit(f"{args.destination_gate} is not a confirmed access gate for {destination}.")

    adjacency = build_adjacency(graph)
    distances = {}
    previous = {}
    queue = []
    origin_by_node = {}
    for access in start_accesses:
        node = access["node"]
        if access["connector_m"] < distances.get(node, math.inf):
            distances[node] = access["connector_m"]
            origin_by_node[node] = access
            previous.pop(node, None)
            heapq.heappush(queue, (access["connector_m"], node))

    while queue:
        current_distance, node = heapq.heappop(queue)
        if current_distance != distances.get(node):
            continue
        for neighbor, weight, edge_id in adjacency[node]:
            candidate = current_distance + weight
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                previous[neighbor] = (node, edge_id)
                origin_by_node[neighbor] = origin_by_node[node]
                heapq.heappush(queue, (candidate, neighbor))

    best = None
    for access in destination_accesses:
        if access["node"] not in distances:
            continue
        total = distances[access["node"]] + access["connector_m"]
        if best is None or total < best[0]:
            best = (total, access)

    if best is None:
        if OUTPUT_PATH.exists():
            OUTPUT_PATH.unlink()
        components = {}
        component_file = ROUTING / "graph_nodes.csv"
        if component_file.exists():
            for row in csv.DictReader(component_file.open("r", newline="", encoding="utf-8-sig")):
                components[row["node_id"]] = row["component"]
        start_components = sorted({components.get(access["node"], "?") for access in places[start]})
        destination_components = sorted({components.get(access["node"], "?") for access in places[destination]})
        print("No route: no confirmed start gate can reach any confirmed destination gate on the current graph.")
        print(f"{start} access nodes/components: " + ", ".join(
            f"{access['node']}/C{components.get(access['node'], '?')}" for access in start_accesses))
        print(f"{destination} access nodes/components: " + ", ".join(
            f"{access['node']}/C{components.get(access['node'], '?')}" for access in destination_accesses))
        print(f"Start components: {', '.join(start_components)}; destination components: {', '.join(destination_components)}")
        print("The graph has disconnected components; inspect graph_nodes.csv and connect real walkway intersections.")
        print("Removed any old route_result.geojson so the map cannot show a stale route.")
        return 2

    total_length, target_access = best
    target_node = target_access["node"]
    route_nodes = [target_node]
    route_edges = []
    cursor = target_node
    while cursor in previous:
        parent, edge_id = previous[cursor]
        route_edges.append(edge_id)
        route_nodes.append(parent)
        cursor = parent
    route_nodes.reverse()
    route_edges.reverse()
    start_access = origin_by_node[route_nodes[0]]

    edge_lookup = {edge["edge_id"]: edge for edge in graph["edges"]}
    line_features = []
    for index, edge_id in enumerate(route_edges):
        edge = edge_lookup[edge_id]
        coordinates = edge.get("coordinates")
        if not coordinates:
            source = DATA / "ways" / edge["file"]
            geojson = json.loads(source.read_text(encoding="utf-8"))
            feature = next((feature for feature in geojson.get("features", [])
                            if feature.get("geometry", {}).get("type") == "LineString"
                            and len(feature.get("geometry", {}).get("coordinates", [])) >= 2), None)
            if feature is None:
                continue
            coordinates = feature["geometry"]["coordinates"]
        if not coordinates:
            continue
        if edge["from"] != route_nodes[index]:
            coordinates = list(reversed(coordinates))
        line_features.append({
            "type": "Feature",
            "properties": {"edge_id": edge_id, "way_id": edge.get("way_id", edge_id), "kind": "walkway"},
            "geometry": {"type": "LineString", "coordinates": coordinates},
        })

    origin_graph_coord = graph["nodes"][start_access["node"]]["coordinates"]
    target_graph_coord = graph["nodes"][target_access["node"]]["coordinates"]
    line_features.insert(0, {
        "type": "Feature", "properties": {"kind": "access_connector", "place_id": start},
        "geometry": {"type": "LineString", "coordinates": [start_access["boundary"], origin_graph_coord]},
    })
    line_features.append({
        "type": "Feature", "properties": {"kind": "access_connector", "place_id": destination},
        "geometry": {"type": "LineString", "coordinates": [target_graph_coord, target_access["boundary"]]},
    })
    OUTPUT_PATH.write_text(json.dumps({"type": "FeatureCollection", "features": line_features},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Shortest route {start} to {destination}: {total_length:.1f} m")
    print(f"Start access: {start_access['node']}; destination access: {target_access['node']}")
    print(f"Walkway edges: {' → '.join(route_edges) if route_edges else '(none; same graph node)'}")
    print(f"Route GeoJSON: {OUTPUT_PATH}")
    print("Review connector lines: they use straight-line distance from graph node to polygon boundary.")


if __name__ == "__main__":
    main()
