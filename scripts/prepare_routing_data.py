"""Audit campus GeoJSON and prepare human-reviewable Dijkstra edge data.

This script never edits source GeoJSON and never guesses which building a
walkway connects to. It reports likely endpoint matches and creates an edge
CSV template for manually confirming routing connections.

Run from any directory:
    python scripts/prepare_routing_data.py
"""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import csv
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path


# Ghi chú: Gán/cập nhật PROJECT_ROOT để lưu dữ liệu dùng ở bước tiếp theo.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Ghi chú: Gán/cập nhật WAYS_DIR để lưu dữ liệu dùng ở bước tiếp theo.
WAYS_DIR = PROJECT_ROOT / "data" / "ways"
# Ghi chú: Gán/cập nhật NODES_DIR để lưu dữ liệu dùng ở bước tiếp theo.
NODES_DIR = PROJECT_ROOT / "data" / "nodes"
# Ghi chú: Gán/cập nhật OUTPUT_DIR để lưu dữ liệu dùng ở bước tiếp theo.
OUTPUT_DIR = PROJECT_ROOT / "data" / "routing"
# Ghi chú: Gán/cập nhật ENDPOINTS_CSV để lưu dữ liệu dùng ở bước tiếp theo.
ENDPOINTS_CSV = OUTPUT_DIR / "way_endpoints.csv"
# Ghi chú: Gán/cập nhật MATCHES_CSV để lưu dữ liệu dùng ở bước tiếp theo.
MATCHES_CSV = OUTPUT_DIR / "nearby_endpoints.csv"
# Ghi chú: Gán/cập nhật EDGES_CSV để lưu dữ liệu dùng ở bước tiếp theo.
EDGES_CSV = OUTPUT_DIR / "edge_connections.csv"
# Ghi chú: Gán/cập nhật SNAP_DISTANCE_M để lưu dữ liệu dùng ở bước tiếp theo.
SNAP_DISTANCE_M = 2.0
# Ghi chú: Gán/cập nhật EARTH_RADIUS_M để lưu dữ liệu dùng ở bước tiếp theo.
EARTH_RADIUS_M = 6_371_000.0


# Ghi chú: Hàm distance_m; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def distance_m(a, b):
    """Haversine distance between GeoJSON [longitude, latitude] points."""
    # Ghi chú: Gán/cập nhật (lon1, lat1) để lưu dữ liệu dùng ở bước tiếp theo.
    lon1, lat1 = map(math.radians, a[:2])
    # Ghi chú: Gán/cập nhật (lon2, lat2) để lưu dữ liệu dùng ở bước tiếp theo.
    lon2, lat2 = map(math.radians, b[:2])
    # Ghi chú: Gán/cập nhật d_lat để lưu dữ liệu dùng ở bước tiếp theo.
    d_lat = lat2 - lat1
    # Ghi chú: Gán/cập nhật d_lon để lưu dữ liệu dùng ở bước tiếp theo.
    d_lon = lon2 - lon1
    # Ghi chú: Gán/cập nhật h để lưu dữ liệu dùng ở bước tiếp theo.
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


# Ghi chú: Hàm length_m; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def length_m(coordinates):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return sum(distance_m(a, b) for a, b in zip(coordinates, coordinates[1:]))


# Ghi chú: Hàm read_feature_collection; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def read_feature_collection(path):
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with path.open("r", encoding="utf-8") as file:
        # Ghi chú: Gán/cập nhật data để lưu dữ liệu dùng ở bước tiếp theo.
        data = json.load(file)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise ValueError("expected a GeoJSON FeatureCollection")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return data["features"]


# Ghi chú: Hàm get_way_records; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def get_way_records():
    # Ghi chú: Gán/cập nhật records để lưu dữ liệu dùng ở bước tiếp theo.
    records = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for path in sorted(WAYS_DIR.glob("*.geojson")):
        # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
        try:
            # Ghi chú: Gán/cập nhật features để lưu dữ liệu dùng ở bước tiếp theo.
            features = read_feature_collection(path)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"Skip {path.name}: {error}")
            continue
        # Ghi chú: Gán/cập nhật line_number để lưu dữ liệu dùng ở bước tiếp theo.
        line_number = 0
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for feature in features:
            # Ghi chú: Gán/cập nhật geometry để lưu dữ liệu dùng ở bước tiếp theo.
            geometry = feature.get("geometry") or {}
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if geometry.get("type") != "LineString":
                continue
            # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
            coords = geometry.get("coordinates") or []
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if len(coords) < 2:
                continue
            line_number += 1
            # Ghi chú: Gán/cập nhật edge_id để lưu dữ liệu dùng ở bước tiếp theo.
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
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return records


# Ghi chú: Hàm write_csv; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def write_csv(path, rows, fieldnames):
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# Ghi chú: Hàm main; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    previous_matches = {}
    if MATCHES_CSV.exists():
        try:
            with MATCHES_CSV.open("r", newline="", encoding="utf-8-sig") as file:
                for row in csv.DictReader(file):
                    key = tuple(sorted(((row.get("edge_1", ""), row.get("endpoint_1", "")),
                                        (row.get("edge_2", ""), row.get("endpoint_2", "")))))
                    previous_matches[key] = row
        except (OSError, UnicodeDecodeError, csv.Error):
            previous_matches = {}
    # Ghi chú: Gán/cập nhật records để lưu dữ liệu dùng ở bước tiếp theo.
    records = get_way_records()

    # Ghi chú: Gán/cập nhật endpoint_rows để lưu dữ liệu dùng ở bước tiếp theo.
    endpoint_rows = []
    # Ghi chú: Gán/cập nhật endpoints để lưu dữ liệu dùng ở bước tiếp theo.
    endpoints = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for record in records:
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for role in ("start", "end"):
            # Ghi chú: Gán/cập nhật lon để lưu dữ liệu dùng ở bước tiếp theo.
            lon = record[f"{role}_lon"]
            # Ghi chú: Gán/cập nhật lat để lưu dữ liệu dùng ở bước tiếp theo.
            lat = record[f"{role}_lat"]
            endpoint_rows.append({
                "edge_id": record["edge_id"], "file": record["file"], "endpoint": role,
                "longitude": lon, "latitude": lat, "length_m": record["length_m"],
            })
            endpoints.append((record["edge_id"], record["file"], role, [lon, lat]))

    # Ghi chú: Gán/cập nhật matches để lưu dữ liệu dùng ở bước tiếp theo.
    matches = []
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for index, first in enumerate(endpoints):
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for second in endpoints[index + 1:]:
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if first[0] == second[0]:
                continue
            # Ghi chú: Gán/cập nhật gap để lưu dữ liệu dùng ở bước tiếp theo.
            gap = distance_m(first[3], second[3])
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if gap <= SNAP_DISTANCE_M:
                key = tuple(sorted(((first[0], first[2]), (second[0], second[2]))))
                previous = previous_matches.get(key)
                decision = "REVIEW"
                if previous:
                    try:
                        old_gap = float(previous.get("gap_m", "inf"))
                        old_decision = previous.get("confirmed_connected", "").strip().lower()
                        if abs(old_gap - gap) <= 0.5 and old_decision in ("yes", "no", "y", "n"):
                            decision = old_decision
                    except (TypeError, ValueError):
                        pass
                matches.append({
                    "edge_1": first[0], "file_1": first[1], "endpoint_1": first[2],
                    "edge_2": second[0], "file_2": second[1], "endpoint_2": second[2],
                    "gap_m": round(gap, 3), "confirmed_connected": decision,
                })

    write_csv(ENDPOINTS_CSV, endpoint_rows,
              ["edge_id", "file", "endpoint", "longitude", "latitude", "length_m"])
    write_csv(MATCHES_CSV, matches,
              ["edge_1", "file_1", "endpoint_1", "edge_2", "file_2", "endpoint_2", "gap_m", "confirmed_connected"])

    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not EDGES_CSV.exists():
        # Ghi chú: Gán/cập nhật template để lưu dữ liệu dùng ở bước tiếp theo.
        template = [{
            "edge_id": row["edge_id"], "file": row["file"],
            "from_node": "", "to_node": "", "length_m": row["length_m"],
            "include_in_routing": "no", "notes": "Fill node IDs only after verifying endpoints",
        } for row in records]
        write_csv(EDGES_CSV, template,
                  ["edge_id", "file", "from_node", "to_node", "length_m", "include_in_routing", "notes"])

    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Gán/cập nhật node_file_count để lưu dữ liệu dùng ở bước tiếp theo.
        node_file_count = sum(1 for _ in NODES_DIR.glob("*.geojson"))
    except OSError:
        # Ghi chú: Gán/cập nhật node_file_count để lưu dữ liệu dùng ở bước tiếp theo.
        node_file_count = 0

    print(f"Node GeoJSON files: {node_file_count}")
    print(f"Valid way LineStrings: {len(records)}")
    print(f"Way endpoints: {len(endpoint_rows)}")
    print(f"Endpoint pairs within {SNAP_DISTANCE_M:.1f} m (candidates, not proof): {len(matches)}")
    print(f"Created/updated report: {ENDPOINTS_CSV}")
    print(f"Created/updated report: {MATCHES_CSV}")
    print(f"Edge review template: {EDGES_CSV}")
    print("Source GeoJSON files were not modified.")


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    main()
