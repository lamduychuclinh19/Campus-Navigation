#!/usr/bin/env python3
"""Audit campus GeoJSON and prepare human-reviewable Dijkstra edge data.

This script never edits source GeoJSON and never guesses which building a
walkway connects to. It reports likely endpoint matches and creates an edge
CSV template for manually confirming routing connections.

Run from any directory:
    python scripts/prepare_routing_data.py
"""

import csv
import json
import math
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WAYS_DIR = PROJECT_ROOT / "data" / "ways"
NODES_DIR = PROJECT_ROOT / "data" / "nodes"
OUTPUT_DIR = PROJECT_ROOT / "data" / "routing"
ENDPOINTS_CSV = OUTPUT_DIR / "way_endpoints.csv"
MATCHES_CSV = OUTPUT_DIR / "nearby_endpoints.csv"
EDGES_CSV = OUTPUT_DIR / "edge_connections.csv"
SNAP_DISTANCE_M = 2.0
EARTH_RADIUS_M = 6_371_000.0


def distance_m(a, b):
    """Haversine distance between GeoJSON [longitude, latitude] points."""
    lon1, lat1 = map(math.radians, a[:2])
    lon2, lat2 = map(math.radians, b[:2])
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def length_m(coordinates):
    return sum(distance_m(a, b) for a, b in zip(coordinates, coordinates[1:]))


def read_feature_collection(path):
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("expected a GeoJSON FeatureCollection")
    return data["features"]


def get_way_records():
    records = []
    for path in sorted(WAYS_DIR.glob("*.geojson")):
        try:
            features = read_feature_collection(path)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"Skip {path.name}: {error}")
            continue
        line_number = 0
        for feature in features:
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "LineString":
                continue
            coords = geometry.get("coordinates") or []
            if len(coords) < 2:
                continue
            line_number += 1
            edge_id = path.stem if line_number == 1 else f"{path.stem}_{line_number}"
            records.append({
                "edge_id": edge_id,
                "file": path.name,
                "start_lon": float(coords[0][0]),
                "start_lat": float(coords[0][1]),
                "end_lon": float(coords[-1][0]),
                "end_lat": float(coords[-1][1]),
                "length_m": round(length_m(coords), 2),
                "coordinate_count": len(coords),
            })
    return records


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records = get_way_records()

    endpoint_rows = []
    endpoints = []
    for record in records:
        for role in ("start", "end"):
            lon = record[f"{role}_lon"]
            lat = record[f"{role}_lat"]
            endpoint_rows.append({
                "edge_id": record["edge_id"], "file": record["file"], "endpoint": role,
                "longitude": lon, "latitude": lat, "length_m": record["length_m"],
            })
            endpoints.append((record["edge_id"], record["file"], role, [lon, lat]))

    matches = []
    for index, first in enumerate(endpoints):
        for second in endpoints[index + 1:]:
            if first[0] == second[0]:
                continue
            gap = distance_m(first[3], second[3])
            if gap <= SNAP_DISTANCE_M:
                matches.append({
                    "edge_1": first[0], "file_1": first[1], "endpoint_1": first[2],
                    "edge_2": second[0], "file_2": second[1], "endpoint_2": second[2],
                    "gap_m": round(gap, 3), "confirmed_connected": "REVIEW",
                })

    write_csv(ENDPOINTS_CSV, endpoint_rows,
              ["edge_id", "file", "endpoint", "longitude", "latitude", "length_m"])
    write_csv(MATCHES_CSV, matches,
              ["edge_1", "file_1", "endpoint_1", "edge_2", "file_2", "endpoint_2", "gap_m", "confirmed_connected"])

    # Keep existing manual decisions if the template already exists.
    if not EDGES_CSV.exists():
        template = [{
            "edge_id": row["edge_id"], "file": row["file"],
            "from_node": "", "to_node": "", "length_m": row["length_m"],
            "include_in_routing": "no", "notes": "Fill node IDs only after verifying endpoints",
        } for row in records]
        write_csv(EDGES_CSV, template,
                  ["edge_id", "file", "from_node", "to_node", "length_m", "include_in_routing", "notes"])

    try:
        node_file_count = sum(1 for _ in NODES_DIR.glob("*.geojson"))
    except OSError:
        node_file_count = 0

    print(f"Node GeoJSON files: {node_file_count}")
    print(f"Valid way LineStrings: {len(records)}")
    print(f"Way endpoints: {len(endpoint_rows)}")
    print(f"Endpoint pairs within {SNAP_DISTANCE_M:.1f} m (candidates, not proof): {len(matches)}")
    print(f"Created/updated report: {ENDPOINTS_CSV}")
    print(f"Created/updated report: {MATCHES_CSV}")
    print(f"Edge review template: {EDGES_CSV}")
    print("Source GeoJSON files were not modified.")


if __name__ == "__main__":
    main()
