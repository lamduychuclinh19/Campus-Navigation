#!/usr/bin/env python3
"""
Inspect a GeoJSON file for the Campus Navigation System project.

What it does:
- Counts geometry types and highway tags.
- Lists LineString features and useful OSM properties.
- Reports features with layer tags.
- Calculates approximate line lengths using the haversine formula.
- Finds line endpoints that are exactly shared by multiple lines.
- Writes CSV reports beside the input file.

This is a diagnostic tool only. It does NOT decide whether a road is safe or
valid for pedestrian routing, and it does not modify the source GeoJSON.

Usage:
    python inspect_geojson.py path/to/sgu_walkways_candidate.geojson
"""

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


def haversine_m(point_a, point_b):
    """Approximate distance in metres between [longitude, latitude] points."""
    lon1, lat1 = point_a[:2]
    lon2, lat2 = point_b[:2]
    earth_radius_m = 6_371_000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * earth_radius_m * math.asin(math.sqrt(min(1.0, a)))


def line_length_m(coordinates):
    """Sum segment lengths in a LineString."""
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return 0.0
    return sum(
        haversine_m(coordinates[index], coordinates[index + 1])
        for index in range(len(coordinates) - 1)
    )


def coord_key(point, precision=7):
    """Rounded endpoint key, useful for detecting likely shared endpoints."""
    return (round(float(point[0]), precision), round(float(point[1]), precision))


def safe_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def main():
    parser = argparse.ArgumentParser(
        description="Inspect GeoJSON roads and buildings without modifying the source file."
    )
    parser.add_argument("geojson_file", help="Path to the input .geojson file")
    args = parser.parse_args()

    input_path = Path(args.geojson_file).expanduser()
    if not input_path.is_file():
        print(f"ERROR: File not found: {input_path}", file=sys.stderr)
        print("Tip: drag the GeoJSON file into the terminal to get its full path.", file=sys.stderr)
        return 2

    try:
        with input_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: Cannot read file: {exc}", file=sys.stderr)
        return 2

    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        print("ERROR: Expected a GeoJSON FeatureCollection with a 'features' list.", file=sys.stderr)
        return 2

    features = data["features"]
    geometry_counts = Counter()
    highway_counts = Counter()
    layer_counts = Counter()
    line_rows = []
    endpoint_to_lines = defaultdict(list)
    missing_geometry = 0
    invalid_lines = 0
    bbox_values = []

    for index, feature in enumerate(features):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        geometry_type = geometry.get("type", "MISSING")
        coordinates = geometry.get("coordinates")
        geometry_counts[geometry_type] += 1

        highway = properties.get("highway")
        if highway is not None:
            highway_counts[str(highway)] += 1

        layer = properties.get("layer")
        if layer is not None:
            layer_counts[str(layer)] += 1

        if geometry_type == "MISSING" or coordinates is None:
            missing_geometry += 1
            continue

        if geometry_type == "LineString":
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                invalid_lines += 1
                continue

            try:
                length = line_length_m(coordinates)
                start = coord_key(coordinates[0])
                end = coord_key(coordinates[-1])
                for point in coordinates:
                    if isinstance(point, list) and len(point) >= 2:
                        bbox_values.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError, IndexError):
                invalid_lines += 1
                continue

            osm_id = properties.get("@id") or feature.get("id") or ""
            row = {
                "feature_index": index,
                "osm_id": osm_id,
                "name": properties.get("name", ""),
                "highway": highway or "",
                "layer": layer if layer is not None else "",
                "access": properties.get("access", ""),
                "foot": properties.get("foot", ""),
                "motor_vehicle": properties.get("motor_vehicle", ""),
                "service": properties.get("service", ""),
                "oneway": properties.get("oneway", ""),
                "coordinate_count": len(coordinates),
                "approx_length_m": round(length, 2),
                "start_lon": coordinates[0][0],
                "start_lat": coordinates[0][1],
                "end_lon": coordinates[-1][0],
                "end_lat": coordinates[-1][1],
            }
            line_rows.append(row)
            endpoint_to_lines[start].append((osm_id, "start", row["highway"]))
            endpoint_to_lines[end].append((osm_id, "end", row["highway"]))

    print("\n=== GEOJSON INSPECTION REPORT ===")
    print(f"Input file: {input_path.resolve()}")
    print(f"Total features: {len(features)}")

    print("\nGeometry types:")
    if geometry_counts:
        for geometry_type, count in geometry_counts.most_common():
            print(f"  {geometry_type}: {count}")
    else:
        print("  No geometry types found.")

    print("\nHighway tags:")
    if highway_counts:
        for highway, count in highway_counts.most_common():
            print(f"  {highway}: {count}")
    else:
        print("  No highway tags found.")

    print("\nLayer tags:")
    if layer_counts:
        for layer, count in sorted(layer_counts.items()):
            print(f"  layer={layer}: {count}")
    else:
        print("  No layer tags found.")

    print("\nLineString checks:")
    print(f"  Valid LineStrings analyzed: {len(line_rows)}")
    print(f"  Invalid/too-short LineStrings: {invalid_lines}")
    print(f"  Features missing geometry/coordinates: {missing_geometry}")
    if line_rows:
        lengths = [row["approx_length_m"] for row in line_rows]
        print(f"  Approximate total length (sum of LineStrings): {sum(lengths):.2f} m")
        print(f"  Shortest LineString: {min(lengths):.2f} m")
        print(f"  Longest LineString: {max(lengths):.2f} m")

    shared_endpoints = {
        point: items for point, items in endpoint_to_lines.items() if len(items) > 1
    }
    print("\nEndpoint connectivity (exact/rounded endpoint matches only):")
    print(f"  Unique line endpoints: {len(endpoint_to_lines)}")
    print(f"  Endpoint locations shared by 2+ line ends: {len(shared_endpoints)}")
    print("  IMPORTANT: shared endpoints are only clues; this does not prove a walkable connection.")
    print("  Lines may also connect at an interior vertex, and barriers may prevent access.")

    output_csv = input_path.with_name(input_path.stem + "_lines_report.csv")
    if line_rows:
        fieldnames = list(line_rows[0].keys())
        with output_csv.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(line_rows)
        print(f"\nLine details CSV written to: {output_csv}")

    endpoints_csv = input_path.with_name(input_path.stem + "_shared_endpoints.csv")
    with endpoints_csv.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["longitude", "latitude", "line_count", "line_ids_and_roles"])
        for (lon, lat), items in sorted(shared_endpoints.items()):
            descriptions = "; ".join(
                f"{osm_id} ({role}, highway={highway})"
                for osm_id, role, highway in items
            )
            writer.writerow([lon, lat, len(items), descriptions])
    print(f"Shared endpoint CSV written to: {endpoints_csv}")

    if bbox_values:
        lons = [point[0] for point in bbox_values]
        lats = [point[1] for point in bbox_values]
        print("\nLine coordinate bounds:")
        print(f"  Longitude: {min(lons):.7f} to {max(lons):.7f}")
        print(f"  Latitude:  {min(lats):.7f} to {max(lats):.7f}")

    print("\nNext step:")
    print("  Review the CSV and map together. Do not automatically accept/reject roads")
    print("  based only on the 'highway' tag or geometric length.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
