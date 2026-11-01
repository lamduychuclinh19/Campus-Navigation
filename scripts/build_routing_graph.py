#!/usr/bin/env python3
"""Build the Dijkstra graph from GeoJSON and user-reviewed connections.

Run: python scripts/build_routing_graph.py
Requires all rows in nearby_endpoints.csv and way_intersections.csv to be
marked yes/no. Source GeoJSON and review CSVs are never modified.
"""

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WAYS = DATA / "ways"
ROUTING = DATA / "routing"
ENDPOINTS_CSV = ROUTING / "nearby_endpoints.csv"
INTERSECTIONS_CSV = ROUTING / "way_intersections.csv"
GRAPH_JSON = ROUTING / "graph.json"
REPORT_CSV = ROUTING / "graph_nodes.csv"
ACCESS_CSV = ROUTING / "place_access_candidates_multi.csv"
EARTH_RADIUS_M = 6_371_000.0


def distance_m(a, b):
    lon1, lat1 = map(math.radians, a[:2])
    lon2, lat2 = map(math.radians, b[:2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def line_length_m(coords):
    return sum(distance_m(a, b) for a, b in zip(coords, coords[1:]))


def local_xy(point, origin_lat):
    lon, lat = point[:2]
    return (math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(origin_lat)),
            math.radians(lat) * EARTH_RADIUS_M)


def project_onto_line(point, coords):
    """Return along-line distance and snapped point for a coordinate."""
    origin_lat = sum(float(item[1]) for item in coords) / len(coords)
    p = local_xy(point, origin_lat)
    cumulative = 0.0
    best = None
    for index, (a_geo, b_geo) in enumerate(zip(coords, coords[1:])):
        a, b = local_xy(a_geo, origin_lat), local_xy(b_geo, origin_lat)
        dx, dy = b[0] - a[0], b[1] - a[1]
        segment_length = math.hypot(dx, dy)
        denom = dx * dx + dy * dy
        t = 0.0 if denom == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
        snapped_xy = (a[0] + t * dx, a[1] + t * dy)
        gap = math.hypot(p[0] - snapped_xy[0], p[1] - snapped_xy[1])
        snapped = [
            math.degrees(snapped_xy[0] / (EARTH_RADIUS_M * math.cos(math.radians(origin_lat)))),
            math.degrees(snapped_xy[1] / EARTH_RADIUS_M),
        ]
        candidate = (gap, cumulative + segment_length * t, snapped)
        if best is None or candidate[0] < best[0]:
            best = candidate
        cumulative += segment_length
    return best[1], best[2], best[0]


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def edge_endpoint_key(way_id, role):
    return f"{way_id}:{role}"


def read_review(path, label):
    if not path.exists():
        raise SystemExit(f"Missing {label}: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    unresolved = [str(index + 2) for index, row in enumerate(rows)
                  if row.get("confirmed_connected", "").strip().lower() not in ("yes", "no", "y", "n")]
    if unresolved:
        raise SystemExit(f"Mark every {label} row yes/no first. Unreviewed CSV lines: {', '.join(unresolved)}")
    return rows


def main():
    old_graph = {}
    if GRAPH_JSON.exists():
        try:
            old_graph = json.loads(GRAPH_JSON.read_text(encoding="utf-8")).get("nodes", {})
        except (OSError, json.JSONDecodeError):
            old_graph = {}
    ways = {}
    for path in sorted(WAYS.glob("*.geojson")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skip {path.name}: {error}")
            continue
        line_number = 0
        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates") or []
            if geometry.get("type") != "LineString" or len(coords) < 2:
                continue
            line_number += 1
            way_id = path.stem if line_number == 1 else f"{path.stem}_{line_number}"
            ways[way_id] = {"file": path.name, "coords": [[float(p[0]), float(p[1])] for p in coords]}

    endpoint_rows = read_review(ENDPOINTS_CSV, "nearby endpoint")
    intersection_rows = read_review(INTERSECTIONS_CSV, "way intersection")
    uf = UnionFind()
    positions = {}
    split_points = {way_id: [] for way_id in ways}

    for way_id, way in ways.items():
        coords = way["coords"]
        start_key, end_key = edge_endpoint_key(way_id, "start"), edge_endpoint_key(way_id, "end")
        positions[start_key], positions[end_key] = coords[0], coords[-1]
        uf.find(start_key)
        uf.find(end_key)

    for row in endpoint_rows:
        if row["confirmed_connected"].strip().lower() not in ("yes", "y"):
            continue
        first = edge_endpoint_key(row["edge_1"], row["endpoint_1"])
        second = edge_endpoint_key(row["edge_2"], row["endpoint_2"])
        if first not in positions or second not in positions:
            raise SystemExit(f"Endpoint reference not found: {first} / {second}")
        uf.union(first, second)

    accepted_intersections = []
    for row_index, row in enumerate(intersection_rows, start=2):
        if row["confirmed_connected"].strip().lower() not in ("yes", "y"):
            continue
        first_id, second_id = row["way_1"], row["way_2"]
        if first_id not in ways or second_id not in ways:
            raise SystemExit(f"Way reference missing on intersection CSV line {row_index}: {first_id}/{second_id}")
        point = [float(row["longitude"]), float(row["latitude"])]
        token = f"IX{row_index:03d}"
        for way_id in (first_id, second_id):
            offset, snapped, gap = project_onto_line(point, ways[way_id]["coords"])
            if gap > 2.0:
                raise SystemExit(f"Intersection line {row_index}: {way_id} is {gap:.2f} m from the reviewed point")
            total = line_length_m(ways[way_id]["coords"])
            if offset <= 0.02:
                uf.union(token, edge_endpoint_key(way_id, "start"))
                split_key = edge_endpoint_key(way_id, "start")
                snapped = ways[way_id]["coords"][0]
            elif total - offset <= 0.02:
                uf.union(token, edge_endpoint_key(way_id, "end"))
                split_key = edge_endpoint_key(way_id, "end")
                snapped = ways[way_id]["coords"][-1]
            else:
                split_key = token
            positions[token] = point
            positions[split_key] = snapped
            split_points[way_id].append((offset, split_key, snapped))
        accepted_intersections.append((token, point))

    # Merge approved candidate points that represent the same physical junction.
    for index, (first_token, first_point) in enumerate(accepted_intersections):
        for second_token, second_point in accepted_intersections[index + 1:]:
            if distance_m(first_point, second_point) <= 0.5:
                uf.union(first_token, second_token)

    # Keep graph coordinates for every encountered vertex and approved split.
    way_vertices = {}
    for way_id, way in ways.items():
        coords = way["coords"]
        cumulative = [0.0]
        for a, b in zip(coords, coords[1:]):
            cumulative.append(cumulative[-1] + distance_m(a, b))
        vertices = []
        for index, point in enumerate(coords):
            key = edge_endpoint_key(way_id, "start") if index == 0 else (
                edge_endpoint_key(way_id, "end") if index == len(coords) - 1 else f"{way_id}:v{index}")
            positions[key] = point
            uf.find(key)
            vertices.append((cumulative[index], key, point))
        vertices.extend(split_points[way_id])
        for _offset, key, _point in vertices:
            uf.find(key)
        vertices.sort(key=lambda item: item[0])
        # Collapse duplicate vertices on the same way while retaining the
        # approved intersection token as the node identity.
        compact = []
        for vertex in vertices:
            if compact and abs(vertex[0] - compact[-1][0]) < 0.01:
                if vertex[1].startswith("IX"):
                    uf.union(vertex[1], compact[-1][1])
                    compact[-1] = vertex
                continue
            compact.append(vertex)
        way_vertices[way_id] = compact

    groups = {}
    for key in uf.parent:
        groups.setdefault(uf.find(key), []).append(key)
    ordered_groups = sorted(groups.items(), key=lambda item: min(item[1]))
    old_refs = {node_id: set(node.get("endpoint_refs", [])) for node_id, node in old_graph.items()}
    used_old_ids = set()
    node_id_by_root = {}
    nodes = {}
    next_node_number = max((int(node_id[1:]) for node_id in old_graph
                            if node_id.startswith("N") and node_id[1:].isdigit()), default=0) + 1
    for root, members in ordered_groups:
        member_set = set(members)
        matching_old_ids = sorted(node_id for node_id, refs in old_refs.items() if refs & member_set)
        node_id = next((old_id for old_id in matching_old_ids if old_id not in used_old_ids), None)
        if node_id is None:
            while f"N{next_node_number:03d}" in used_old_ids or f"N{next_node_number:03d}" in old_graph:
                next_node_number += 1
            node_id = f"N{next_node_number:03d}"
            next_node_number += 1
        used_old_ids.add(node_id)
        node_id_by_root[root] = node_id
        known_coords = [positions[key] for key in members if key in positions]
        if not known_coords:
            continue
        nodes[node_id] = {
            "coordinates": [round(sum(p[0] for p in known_coords) / len(known_coords), 7),
                            round(sum(p[1] for p in known_coords) / len(known_coords), 7)],
            "endpoint_refs": sorted(members),
        }

    edges = []
    for way_id, vertices in way_vertices.items():
        part = 0
        for first, second in zip(vertices, vertices[1:]):
            start_node = node_id_by_root[uf.find(first[1])]
            end_node = node_id_by_root[uf.find(second[1])]
            coords = [first[2], second[2]]
            weight = round(line_length_m(coords), 2)
            if weight <= 0:
                continue
            part += 1
            edges.append({
                "edge_id": f"{way_id}_part{part:02d}", "way_id": way_id,
                "file": ways[way_id]["file"], "from": start_node, "to": end_node,
                "length_m": weight, "coordinates": coords,
            })

    adjacency = {node_id: [] for node_id in nodes}
    for edge in edges:
        adjacency[edge["from"]].append((edge["to"], edge["length_m"]))
        adjacency[edge["to"]].append((edge["from"], edge["length_m"]))
    # Map old IDs to current nodes so already-reviewed place access rows keep
    # pointing to the same physical gates after intersections are inserted.
    old_to_new = {}
    for old_id, refs in old_refs.items():
        candidates = [(len(refs & set(members)), root) for root, members in groups.items() if refs & set(members)]
        if candidates:
            _count, root = max(candidates)
            old_to_new[old_id] = node_id_by_root[root]

    graph = {"directed": False, "nodes": nodes, "edges": edges}
    GRAPH_JSON.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    report_rows = []
    visited = set()
    component_id = 0
    for node_id in adjacency:
        if node_id in visited:
            continue
        component_id += 1
        stack = [node_id]
        visited.add(node_id)
        component_nodes = []
        while stack:
            current = stack.pop()
            component_nodes.append(current)
            for neighbor, _ in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        for reachable in component_nodes:
            report_rows.append({"node_id": reachable, "component": component_id,
                                "longitude": nodes[reachable]["coordinates"][0],
                                "latitude": nodes[reachable]["coordinates"][1],
                                "degree": len(adjacency[reachable])})

    with REPORT_CSV.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["node_id", "component", "longitude", "latitude", "degree"])
        writer.writeheader()
        writer.writerows(report_rows)

    # Refresh gate rows with remapped IDs/components while preserving the
    # user's yes/no decisions. If multiple old junctions merged, a yes wins.
    if ACCESS_CSV.exists():
        try:
            old_text = ACCESS_CSV.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            old_text = ACCESS_CSV.read_text(encoding="cp1258")
        access_rows = list(csv.DictReader(old_text.splitlines()))
        component_by_node = {row["node_id"]: row["component"] for row in report_rows}
        refreshed = {}
        for row in access_rows:
            old_id = row.get("graph_node_candidate", "")
            try:
                previous_coord = [float(row["graph_node_lon"]), float(row["graph_node_lat"])]
            except (KeyError, TypeError, ValueError):
                previous_coord = None
            new_id = old_to_new.get(old_id, old_id)
            if previous_coord:
                nearest_id = min(nodes, key=lambda node_id: distance_m(previous_coord, nodes[node_id]["coordinates"]))
                if distance_m(previous_coord, nodes[nearest_id]["coordinates"]) <= 2.0:
                    new_id = nearest_id
            if new_id not in nodes:
                continue
            row["graph_node_candidate"] = new_id
            row["component"] = component_by_node.get(new_id, "")
            coord = nodes[new_id]["coordinates"]
            row["graph_node_lon"], row["graph_node_lat"] = coord
            boundary = [float(row["projected_boundary_lon"]), float(row["projected_boundary_lat"])]
            row["distance_to_polygon_m"] = round(distance_m(coord, boundary), 2)
            key = (row.get("place_id", ""), new_id)
            previous = refreshed.get(key)
            if previous is None or (row.get("confirmed_access", "").strip().lower() == "yes"
                                    and previous.get("confirmed_access", "").strip().lower() != "yes"):
                refreshed[key] = row
        if access_rows:
            fields = list(access_rows[0].keys())
            try:
                with ACCESS_CSV.open("w", newline="", encoding="utf-8-sig") as file:
                    writer = csv.DictWriter(file, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(refreshed.values())
            except PermissionError:
                print("Could not refresh place access CSV (it may be open in Excel). Close it and rerun this script.")

    degree_one = sum(1 for adjacent in adjacency.values() if len(adjacent) == 1)
    print(f"Built graph: {len(nodes)} graph nodes, {len(edges)} split edges")
    print(f"Approved interior connections applied: {len(accepted_intersections)}")
    print(f"Connected components: {component_id}")
    print(f"Dead ends (degree 1): {degree_one}")
    print(f"Graph file: {GRAPH_JSON}")
    print(f"Node/component review: {REPORT_CSV}")
    print("Preserved existing graph node IDs and refreshed place access references.")


if __name__ == "__main__":
    main()
