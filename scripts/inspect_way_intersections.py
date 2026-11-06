"""Find likely connections where walkway LineStrings meet in their interiors.

This creates a review CSV only; detected crossings are not assumed walkable.
Run: python scripts/inspect_way_intersections.py
"""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import csv
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path


# Ghi chú: Gán/cập nhật ROOT để lưu dữ liệu dùng ở bước tiếp theo.
ROOT = Path(__file__).resolve().parents[1]
# Ghi chú: Gán/cập nhật WAYS_DIR để lưu dữ liệu dùng ở bước tiếp theo.
WAYS_DIR = ROOT / "data" / "ways"
# Ghi chú: Gán/cập nhật OUTPUT để lưu dữ liệu dùng ở bước tiếp theo.
OUTPUT = ROOT / "data" / "routing" / "way_intersections.csv"
# Ghi chú: Gán/cập nhật OUTPUT_GEOJSON để lưu dữ liệu dùng ở bước tiếp theo.
OUTPUT_GEOJSON = ROOT / "data" / "routing" / "way_intersections.geojson"
# Ghi chú: Gán/cập nhật ORIGIN_LAT để lưu dữ liệu dùng ở bước tiếp theo.
ORIGIN_LAT = 10.76
# Ghi chú: Gán/cập nhật EARTH_RADIUS_M để lưu dữ liệu dùng ở bước tiếp theo.
EARTH_RADIUS_M = 6_371_000.0
# Ghi chú: Gán/cập nhật NEAR_METRES để lưu dữ liệu dùng ở bước tiếp theo.
NEAR_METRES = 1.5


# Ghi chú: Hàm xy; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def xy(point):
    # Ghi chú: Gán/cập nhật (lon, lat) để lưu dữ liệu dùng ở bước tiếp theo.
    lon, lat = point[:2]
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return (math.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(ORIGIN_LAT)),
            math.radians(lat) * EARTH_RADIUS_M)


# Ghi chú: Hàm lonlat; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def lonlat(point):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return (math.degrees(point[0] / (EARTH_RADIUS_M * math.cos(math.radians(ORIGIN_LAT)))),
            math.degrees(point[1] / EARTH_RADIUS_M))


# Ghi chú: Hàm cross; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def cross(a, b):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return a[0] * b[1] - a[1] * b[0]


# Ghi chú: Hàm subtract; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def subtract(a, b):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return a[0] - b[0], a[1] - b[1]


# Ghi chú: Hàm segment_intersection; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def segment_intersection(a, b, c, d):
    """Return the intersection point and segment fractions, if they cross."""
    # Ghi chú: Gán/cập nhật (r, s) để lưu dữ liệu dùng ở bước tiếp theo.
    r, s = subtract(b, a), subtract(d, c)
    # Ghi chú: Gán/cập nhật denominator để lưu dữ liệu dùng ở bước tiếp theo.
    denominator = cross(r, s)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if abs(denominator) < 1e-9:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return None
    # Ghi chú: Gán/cập nhật t để lưu dữ liệu dùng ở bước tiếp theo.
    t = cross(subtract(c, a), s) / denominator
    # Ghi chú: Gán/cập nhật u để lưu dữ liệu dùng ở bước tiếp theo.
    u = cross(subtract(c, a), r) / denominator
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if -1e-8 <= t <= 1 + 1e-8 and -1e-8 <= u <= 1 + 1e-8:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return (a[0] + t * r[0], a[1] + t * r[1]), t, u
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return None


# Ghi chú: Hàm point_segment_distance; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def point_segment_distance(p, a, b):
    # Ghi chú: Gán/cập nhật direction để lưu dữ liệu dùng ở bước tiếp theo.
    direction = subtract(b, a)
    # Ghi chú: Gán/cập nhật denom để lưu dữ liệu dùng ở bước tiếp theo.
    denom = direction[0] ** 2 + direction[1] ** 2
    # Ghi chú: Gán/cập nhật fraction để lưu dữ liệu dùng ở bước tiếp theo.
    fraction = 0 if denom == 0 else max(0, min(1, ((p[0] - a[0]) * direction[0] + (p[1] - a[1]) * direction[1]) / denom))
    # Ghi chú: Gán/cập nhật closest để lưu dữ liệu dùng ở bước tiếp theo.
    closest = (a[0] + fraction * direction[0], a[1] + fraction * direction[1])
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return math.hypot(p[0] - closest[0], p[1] - closest[1]), fraction, closest


# Ghi chú: Hàm load_lines; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def load_lines():
    # Ghi chú: Gán/cập nhật lines để lưu dữ liệu dùng ở bước tiếp theo.
    lines = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for path in sorted(WAYS_DIR.glob("*.geojson")):
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật data để lưu dữ liệu dùng ở bước tiếp theo.
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skip {path.name}: {error}")
            continue
        # Ghi chú: Gán/cập nhật line_index để lưu dữ liệu dùng ở bước tiếp theo.
        line_index = 0
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for feature in data.get("features", []):
            # Ghi chú: Gán/cập nhật geometry để lưu dữ liệu dùng ở bước tiếp theo.
            geometry = feature.get("geometry") or {}
            # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
            coords = geometry.get("coordinates") or []
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if geometry.get("type") != "LineString" or len(coords) < 2:
                continue
            line_index += 1
            lines.append({
                "id": path.stem if line_index == 1 else f"{path.stem}_{line_index}",
                "file": path.name,
                "coords": [xy(point) for point in coords],
            })
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return lines


# Ghi chú: Hàm main; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def main():
    # Ghi chú: Gán/cập nhật lines để lưu dữ liệu dùng ở bước tiếp theo.
    lines = load_lines()
    previous_rows = []
    if OUTPUT.exists():
        try:
            with OUTPUT.open("r", newline="", encoding="utf-8-sig") as file:
                previous_rows = list(csv.DictReader(file))
        except (OSError, UnicodeDecodeError, csv.Error):
            previous_rows = []
    # Ghi chú: Gán/cập nhật found để lưu dữ liệu dùng ở bước tiếp theo.
    found = {}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for i, first in enumerate(lines):
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for second in lines[i + 1:]:
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for ai, (a, b) in enumerate(zip(first["coords"], first["coords"][1:])):
                # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
                for bi, (c, d) in enumerate(zip(second["coords"], second["coords"][1:])):
                    # Ghi chú: Gán/cập nhật hit để lưu dữ liệu dùng ở bước tiếp theo.
                    hit = segment_intersection(a, b, c, d)
                    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                    if hit:
                        # Ghi chú: Gán/cập nhật (point, t, u) để lưu dữ liệu dùng ở bước tiếp theo.
                        point, t, u = hit
                        # Ghi chú: Gán/cập nhật first_interior để lưu dữ liệu dùng ở bước tiếp theo.
                        first_interior = 1e-5 < t < 1 - 1e-5 or 1e-5 < (ai + t) / (len(first["coords"]) - 1) < 1 - 1e-5
                        # Ghi chú: Gán/cập nhật second_interior để lưu dữ liệu dùng ở bước tiếp theo.
                        second_interior = 1e-5 < u < 1 - 1e-5 or 1e-5 < (bi + u) / (len(second["coords"]) - 1) < 1 - 1e-5
                        # Ghi chú: Gán/cập nhật kind để lưu dữ liệu dùng ở bước tiếp theo.
                        kind = "crossing" if first_interior and second_interior else "endpoint_to_interior"
                        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                        if not (first_interior or second_interior):
                            continue
                        # Ghi chú: Gán/cập nhật (x, y) để lưu dữ liệu dùng ở bước tiếp theo.
                        x, y = lonlat(point)
                        # Ghi chú: Gán/cập nhật key để lưu dữ liệu dùng ở bước tiếp theo.
                        key = (first["id"], second["id"], round(x, 6), round(y, 6))
                        # Ghi chú: Gán/cập nhật found[key] để lưu dữ liệu dùng ở bước tiếp theo.
                        found[key] = {
                            "way_1": first["id"], "file_1": first["file"],
                            "way_2": second["id"], "file_2": second["file"],
                            "connection_type": kind,
                            "longitude": round(x, 7), "latitude": round(y, 7),
                            "gap_m": 0.0, "confirmed_connected": "REVIEW",
                        }

                    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
                    for endpoint_name, endpoint, target_a, target_b, target_segment, endpoint_is_first in (
                        ("start", first["coords"][0], c, d, bi, True),
                        ("end", first["coords"][-1], c, d, bi, True),
                        ("start", second["coords"][0], a, b, ai, False),
                        ("end", second["coords"][-1], a, b, ai, False),
                    ):
                        # Ghi chú: Gán/cập nhật (distance, fraction, closest) để lưu dữ liệu dùng ở bước tiếp theo.
                        distance, fraction, closest = point_segment_distance(endpoint, target_a, target_b)
                        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                        if distance > NEAR_METRES or not 1e-5 < fraction < 1 - 1e-5:
                            continue
                        # Ghi chú: Gán/cập nhật (x, y) để lưu dữ liệu dùng ở bước tiếp theo.
                        x, y = lonlat(closest)
                        # Ghi chú: Gán/cập nhật key để lưu dữ liệu dùng ở bước tiếp theo.
                        key = (first["id"], second["id"], round(x, 6), round(y, 6))
                        found.setdefault(key, {
                            "way_1": first["id"], "file_1": first["file"],
                            "way_2": second["id"], "file_2": second["file"],
                            "connection_type": "endpoint_near_interior",
                            "longitude": round(x, 7), "latitude": round(y, 7),
                            "gap_m": round(distance, 3), "confirmed_connected": "REVIEW",
                        })

    # Keep reviewed decisions only when the same pair of ways still meets
    # within 0.5 m of the reviewed junction. Changed/new junctions need review.
    for row in found.values():
        way_pair = tuple(sorted((row["way_1"], row["way_2"])))
        point_xy = xy([float(row["longitude"]), float(row["latitude"])])
        previous = []
        for old in previous_rows:
            old_pair = tuple(sorted((old.get("way_1", ""), old.get("way_2", ""))))
            decision = old.get("confirmed_connected", "").strip().lower()
            if old_pair != way_pair or decision not in ("yes", "no", "y", "n"):
                continue
            try:
                old_xy = xy([float(old["longitude"]), float(old["latitude"])])
                gap = math.hypot(point_xy[0] - old_xy[0], point_xy[1] - old_xy[1])
            except (KeyError, TypeError, ValueError):
                continue
            if gap <= 0.5:
                previous.append((gap, decision))
        if previous:
            row["confirmed_connected"] = min(previous)[1]

    # Ghi chú: Gán/cập nhật fields để lưu dữ liệu dùng ở bước tiếp theo.
    fields = ["way_1", "file_1", "way_2", "file_2", "connection_type",
              "longitude", "latitude", "gap_m", "confirmed_connected"]
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as file:
        # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(found.values(), key=lambda row: (row["way_1"], row["way_2"], row["longitude"], row["latitude"])))
    # Ghi chú: Gán/cập nhật features để lưu dữ liệu dùng ở bước tiếp theo.
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


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    main()
