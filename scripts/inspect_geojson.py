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

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import argparse
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import csv
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import sys
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from collections import Counter, defaultdict
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path


# Ghi chú: Hàm haversine_m; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def haversine_m(point_a, point_b):
    """Approximate distance in metres between [longitude, latitude] points."""
    # Ghi chú: Gán/cập nhật (lon1, lat1) để lưu dữ liệu dùng ở bước tiếp theo.
    lon1, lat1 = point_a[:2]
    # Ghi chú: Gán/cập nhật (lon2, lat2) để lưu dữ liệu dùng ở bước tiếp theo.
    lon2, lat2 = point_b[:2]
    # Ghi chú: Gán/cập nhật earth_radius_m để lưu dữ liệu dùng ở bước tiếp theo.
    earth_radius_m = 6_371_000.0

    # Ghi chú: Gán/cập nhật phi1 để lưu dữ liệu dùng ở bước tiếp theo.
    phi1 = math.radians(lat1)
    # Ghi chú: Gán/cập nhật phi2 để lưu dữ liệu dùng ở bước tiếp theo.
    phi2 = math.radians(lat2)
    # Ghi chú: Gán/cập nhật delta_phi để lưu dữ liệu dùng ở bước tiếp theo.
    delta_phi = math.radians(lat2 - lat1)
    # Ghi chú: Gán/cập nhật delta_lambda để lưu dữ liệu dùng ở bước tiếp theo.
    delta_lambda = math.radians(lon2 - lon1)

    # Ghi chú: Gán/cập nhật a để lưu dữ liệu dùng ở bước tiếp theo.
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return 2 * earth_radius_m * math.asin(math.sqrt(min(1.0, a)))


# Ghi chú: Hàm line_length_m; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def line_length_m(coordinates):
    """Sum segment lengths in a LineString."""
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return 0.0
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return sum(
        haversine_m(coordinates[index], coordinates[index + 1])
        for index in range(len(coordinates) - 1)
    )


# Ghi chú: Hàm coord_key; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def coord_key(point, precision=7):
    """Rounded endpoint key, useful for detecting likely shared endpoints."""
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return (round(float(point[0]), precision), round(float(point[1]), precision))


# Ghi chú: Hàm safe_text; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def safe_text(value):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if value is None:
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return ""
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if isinstance(value, (dict, list)):
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return json.dumps(value, ensure_ascii=False)
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return str(value)


# Ghi chú: Hàm main; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def main():
    # Ghi chú: Gán/cập nhật parser để lưu dữ liệu dùng ở bước tiếp theo.
    parser = argparse.ArgumentParser(
        description="Inspect GeoJSON roads and buildings without modifying the source file."
    )
    parser.add_argument("geojson_file", help="Path to the input .geojson file")
    # Ghi chú: Gán/cập nhật args để lưu dữ liệu dùng ở bước tiếp theo.
    args = parser.parse_args()

    # Ghi chú: Gán/cập nhật input_path để lưu dữ liệu dùng ở bước tiếp theo.
    input_path = Path(args.geojson_file).expanduser()
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not input_path.is_file():
        print(f"ERROR: File not found: {input_path}", file=sys.stderr)
        print("Tip: drag the GeoJSON file into the terminal to get its full path.", file=sys.stderr)
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return 2

    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with input_path.open("r", encoding="utf-8") as file:
            # Ghi chú: Gán/cập nhật data để lưu dữ liệu dùng ở bước tiếp theo.
            data = json.load(file)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}", file=sys.stderr)
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return 2
    except OSError as exc:
        print(f"ERROR: Cannot read file: {exc}", file=sys.stderr)
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return 2

    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        print("ERROR: Expected a GeoJSON FeatureCollection with a 'features' list.", file=sys.stderr)
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return 2

    # Ghi chú: Gán/cập nhật features để lưu dữ liệu dùng ở bước tiếp theo.
    features = data["features"]
    # Ghi chú: Gán/cập nhật geometry_counts để lưu dữ liệu dùng ở bước tiếp theo.
    geometry_counts = Counter()
    # Ghi chú: Gán/cập nhật highway_counts để lưu dữ liệu dùng ở bước tiếp theo.
    highway_counts = Counter()
    # Ghi chú: Gán/cập nhật layer_counts để lưu dữ liệu dùng ở bước tiếp theo.
    layer_counts = Counter()
    # Ghi chú: Gán/cập nhật line_rows để lưu dữ liệu dùng ở bước tiếp theo.
    line_rows = []
    # Ghi chú: Gán/cập nhật endpoint_to_lines để lưu dữ liệu dùng ở bước tiếp theo.
    endpoint_to_lines = defaultdict(list)
    # Ghi chú: Gán/cập nhật missing_geometry để lưu dữ liệu dùng ở bước tiếp theo.
    missing_geometry = 0
    # Ghi chú: Gán/cập nhật invalid_lines để lưu dữ liệu dùng ở bước tiếp theo.
    invalid_lines = 0
    # Ghi chú: Gán/cập nhật bbox_values để lưu dữ liệu dùng ở bước tiếp theo.
    bbox_values = []

    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for index, feature in enumerate(features):
        # Ghi chú: Gán/cập nhật properties để lưu dữ liệu dùng ở bước tiếp theo.
        properties = feature.get("properties") or {}
        # Ghi chú: Gán/cập nhật geometry để lưu dữ liệu dùng ở bước tiếp theo.
        geometry = feature.get("geometry") or {}
        # Ghi chú: Gán/cập nhật geometry_type để lưu dữ liệu dùng ở bước tiếp theo.
        geometry_type = geometry.get("type", "MISSING")
        # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
        coordinates = geometry.get("coordinates")
        geometry_counts[geometry_type] += 1

        # Ghi chú: Gán/cập nhật highway để lưu dữ liệu dùng ở bước tiếp theo.
        highway = properties.get("highway")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if highway is not None:
            highway_counts[str(highway)] += 1

        # Ghi chú: Gán/cập nhật layer để lưu dữ liệu dùng ở bước tiếp theo.
        layer = properties.get("layer")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if layer is not None:
            layer_counts[str(layer)] += 1

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if geometry_type == "MISSING" or coordinates is None:
            missing_geometry += 1
            continue

        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if geometry_type == "LineString":
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                invalid_lines += 1
                continue

            # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
            try:
                # Ghi chú: Gán/cập nhật length để lưu dữ liệu dùng ở bước tiếp theo.
                length = line_length_m(coordinates)
                # Ghi chú: Gán/cập nhật start để lưu dữ liệu dùng ở bước tiếp theo.
                start = coord_key(coordinates[0])
                # Ghi chú: Gán/cập nhật end để lưu dữ liệu dùng ở bước tiếp theo.
                end = coord_key(coordinates[-1])
                # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
                for point in coordinates:
                    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                    if isinstance(point, list) and len(point) >= 2:
                        bbox_values.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError, IndexError):
                invalid_lines += 1
                continue

            # Ghi chú: Gán/cập nhật osm_id để lưu dữ liệu dùng ở bước tiếp theo.
            osm_id = properties.get("@id") or feature.get("id") or ""
            # Ghi chú: Gán/cập nhật row để lưu dữ liệu dùng ở bước tiếp theo.
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
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if geometry_counts:
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for geometry_type, count in geometry_counts.most_common():
            print(f"  {geometry_type}: {count}")
    else:
        print("  No geometry types found.")

    print("\nHighway tags:")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if highway_counts:
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for highway, count in highway_counts.most_common():
            print(f"  {highway}: {count}")
    else:
        print("  No highway tags found.")

    print("\nLayer tags:")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if layer_counts:
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for layer, count in sorted(layer_counts.items()):
            print(f"  layer={layer}: {count}")
    else:
        print("  No layer tags found.")

    print("\nLineString checks:")
    print(f"  Valid LineStrings analyzed: {len(line_rows)}")
    print(f"  Invalid/too-short LineStrings: {invalid_lines}")
    print(f"  Features missing geometry/coordinates: {missing_geometry}")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if line_rows:
        # Ghi chú: Gán/cập nhật lengths để lưu dữ liệu dùng ở bước tiếp theo.
        lengths = [row["approx_length_m"] for row in line_rows]
        print(f"  Approximate total length (sum of LineStrings): {sum(lengths):.2f} m")
        print(f"  Shortest LineString: {min(lengths):.2f} m")
        print(f"  Longest LineString: {max(lengths):.2f} m")

    # Ghi chú: Gán/cập nhật shared_endpoints để lưu dữ liệu dùng ở bước tiếp theo.
    shared_endpoints = {
        point: items for point, items in endpoint_to_lines.items() if len(items) > 1
    }
    print("\nEndpoint connectivity (exact/rounded endpoint matches only):")
    print(f"  Unique line endpoints: {len(endpoint_to_lines)}")
    print(f"  Endpoint locations shared by 2+ line ends: {len(shared_endpoints)}")
    print("  IMPORTANT: shared endpoints are only clues; this does not prove a walkable connection.")
    print("  Lines may also connect at an interior vertex, and barriers may prevent access.")

    # Ghi chú: Gán/cập nhật output_csv để lưu dữ liệu dùng ở bước tiếp theo.
    output_csv = input_path.with_name(input_path.stem + "_lines_report.csv")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if line_rows:
        # Ghi chú: Gán/cập nhật fieldnames để lưu dữ liệu dùng ở bước tiếp theo.
        fieldnames = list(line_rows[0].keys())
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with output_csv.open("w", newline="", encoding="utf-8-sig") as file:
            # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(line_rows)
        print(f"\nLine details CSV written to: {output_csv}")

    # Ghi chú: Gán/cập nhật endpoints_csv để lưu dữ liệu dùng ở bước tiếp theo.
    endpoints_csv = input_path.with_name(input_path.stem + "_shared_endpoints.csv")
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with endpoints_csv.open("w", newline="", encoding="utf-8-sig") as file:
        # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
        writer = csv.writer(file)
        writer.writerow(["longitude", "latitude", "line_count", "line_ids_and_roles"])
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for (lon, lat), items in sorted(shared_endpoints.items()):
            # Ghi chú: Gán/cập nhật descriptions để lưu dữ liệu dùng ở bước tiếp theo.
            descriptions = "; ".join(
                f"{osm_id} ({role}, highway={highway})"
                for osm_id, role, highway in items
            )
            writer.writerow([lon, lat, len(items), descriptions])
    print(f"Shared endpoint CSV written to: {endpoints_csv}")

    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if bbox_values:
        # Ghi chú: Gán/cập nhật lons để lưu dữ liệu dùng ở bước tiếp theo.
        lons = [point[0] for point in bbox_values]
        # Ghi chú: Gán/cập nhật lats để lưu dữ liệu dùng ở bước tiếp theo.
        lats = [point[1] for point in bbox_values]
        print("\nLine coordinate bounds:")
        print(f"  Longitude: {min(lons):.7f} to {max(lons):.7f}")
        print(f"  Latitude:  {min(lats):.7f} to {max(lats):.7f}")

    print("\nNext step:")
    print("  Review the CSV and map together. Do not automatically accept/reject roads")
    print("  based only on the 'highway' tag or geometric length.")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return 0


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
    raise SystemExit(main())
