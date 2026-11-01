#!/usr/bin/env python3
"""Find likely connections where walkway LineStrings meet in their interiors.

This creates a review CSV only; detected crossings are not assumed walkable.
Run: python scripts/inspect_way_intersections.py
"""

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WAYS_DIR = ROOT / "data" / "ways"
OUTPUT = ROOT / "data" / "routing" / "way_intersections.csv"
OUTPUT_GEOJSON = ROOT / "data" / "routing" / "way_intersections.geojson"
ORIGIN_LAT = 10.76
EARTH_RADIUS_M = 6_371_000.0
NEAR_METRES = 1.5


def xy(point):
    lon, lat = point[:2]
    return (math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(ORIGIN_LAT)),
            math.radians(lat) * EARTH_RADIUS_M)


def lonlat(point):
    return (math.degrees(point[0] / (EARTH_RADIUS_M * math.cos(math.radians(ORIGIN_LAT)))),
            math.degrees(point[1] / EARTH_RADIUS_M))


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def subtract(a, b):
    return a[0] - b[0], a[1] - b[1]


def segment_intersection(a, b, c, d):
    """Return the intersection point and segment fractions, if they cross."""
    r, s = subtract(b, a), subtract(d, c)
    denominator = cross(r, s)
    if abs(denominator) < 1e-9:
        return None
    t = cross(subtract(c, a), s) / denominator
    u = cross(subtract(c, a), r) / denominator
    if -1e-8 <= t <= 1 + 1e-8 and -1e-8 <= u <= 1 + 1e-8:
        return (a[0] + t * r[0], a[1] + t * r[1]), t, u
    return None


def point_segment_distance(p, a, b):
    direction = subtract(b, a)
    denom = direction[0] ** 2 + direction[1] ** 2
    fraction = 0 if denom == 0 else max(0, min(1, ((p[0] - a[0]) * direction[0] + (p[1] - a[1]) * direction[1]) / denom))
    closest = (a[0] + fraction * direction[0], a[1] + fraction * direction[1])
    return math.hypot(p[0] - closest[0], p[1] - closest[1]), fraction, closest


def load_lines():
    lines = []
    for path in sorted(WAYS_DIR.glob("*.geojson")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skip {path.name}: {error}")
            continue
        line_index = 0
        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates") or []
            if geometry.get("type") != "LineString" or len(coords) < 2:
                continue
            line_index += 1
            lines.append({
                "id": path.stem if line_index == 1 else f"{path.stem}_{line_index}",
                "file": path.name,
                "coords": [xy(point) for point in coords],
            })
    return lines


def main():
    lines = load_lines()
    found = {}
    for i, first in enumerate(lines):
        for second in lines[i + 1:]:
            for ai, (a, b) in enumerate(zip(first["coords"], first["coords"][1:])):
                for bi, (c, d) in enumerate(zip(second["coords"], second["coords"][1:])):
                    hit = segment_intersection(a, b, c, d)
                    if hit:
                        point, t, u = hit
                        # Skip a meeting where both are ordinary line endpoints;
                        # those were already listed in nearby_endpoints.csv.
                        first_interior = 1e-5 < t < 1 - 1e-5 or 1e-5 < (ai + t) / (len(first["coords"]) - 1) < 1 - 1e-5
                        second_interior = 1e-5 < u < 1 - 1e-5 or 1e-5 < (bi + u) / (len(second["coords"]) - 1) < 1 - 1e-5
                        kind = "crossing" if first_interior and second_interior else "endpoint_to_interior"
                        if not (first_interior or second_interior):
                            continue
                        x, y = lonlat(point)
                        key = (first["id"], second["id"], round(x, 6), round(y, 6))
                        found[key] = {
                            "way_1": first["id"], "file_1": first["file"],
                            "way_2": second["id"], "file_2": second["file"],
                            "connection_type": kind,
                            "longitude": round(x, 7), "latitude": round(y, 7),
                            "gap_m": 0.0, "confirmed_connected": "REVIEW",
                        }

                    # Also catch a digitized endpoint that nearly touches the
                    # interior of a different path without exactly intersecting.
                    for endpoint_name, endpoint, target_a, target_b, target_segment, endpoint_is_first in (
                        ("start", first["coords"][0], c, d, bi, True),
                        ("end", first["coords"][-1], c, d, bi, True),
                        ("start", second["coords"][0], a, b, ai, False),
                        ("end", second["coords"][-1], a, b, ai, False),
                    ):
                        distance, fraction, closest = point_segment_distance(endpoint, target_a, target_b)
                        if distance > NEAR_METRES or not 1e-5 < fraction < 1 - 1e-5:
                            continue
                        x, y = lonlat(closest)
                        key = (first["id"], second["id"], round(x, 6), round(y, 6))
                        found.setdefault(key, {
                            "way_1": first["id"], "file_1": first["file"],
                            "way_2": second["id"], "file_2": second["file"],
                            "connection_type": "endpoint_near_interior",
                            "longitude": round(x, 7), "latitude": round(y, 7),
                            "gap_m": round(distance, 3), "confirmed_connected": "REVIEW",
                        })

    fields = ["way_1", "file_1", "way_2", "file_2", "connection_type",
              "longitude", "latitude", "gap_m", "confirmed_connected"]
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(found.values(), key=lambda row: (row["way_1"], row["way_2"], row["longitude"], row["latitude"])))
    features = [{
        "type": "Feature",
        "properties": {key: value for key, value in row.items() if key not in ("longitude", "latitude")},
        "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
    } for row in found.values()]
    OUTPUT_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Way lines inspected: {len(lines)}")
    print(f"Interior meeting candidates: {len(found)}")
    print(f"Review before connecting: {OUTPUT}")
    print(f"Map markers: {OUTPUT_GEOJSON}")
    print("Detected intersections are clues only; check walkability and vertical separation first.")


if __name__ == "__main__":
    main()
