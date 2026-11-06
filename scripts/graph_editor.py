"""Safe, patch-based edits for the campus routing graph."""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import csv
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from datetime import datetime, timezone
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import hashlib
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import math
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import os
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import tempfile

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from gps_routing import LocalAEQD, projection_for_graph, valid_lonlat


# Ghi chú: Lớp GraphEditError; xem các câu lệnh bên dưới để theo dõi cách xử lý.
class GraphEditError(ValueError):
    # Ghi chú: Hàm __init__; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def __init__(self, message, status=400, code="invalid_edit"):
        super().__init__(message)
        # Ghi chú: Gán/cập nhật self.status để lưu dữ liệu dùng ở bước tiếp theo.
        self.status = status
        # Ghi chú: Gán/cập nhật self.code để lưu dữ liệu dùng ở bước tiếp theo.
        self.code = code


# Ghi chú: Hàm graph_revision; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def graph_revision(raw):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return hashlib.sha256(raw).hexdigest()


# Ghi chú: Hàm load_graph_snapshot; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def load_graph_snapshot(graph_path):
    # Ghi chú: Gán/cập nhật raw để lưu dữ liệu dùng ở bước tiếp theo.
    raw = graph_path.read_bytes()
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
        graph = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError(f"Không đọc được graph JSON: {error}", 500, "invalid_graph")
    validate_graph(graph)
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return graph, graph_revision(raw)


# Ghi chú: Hàm validate_graph; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def validate_graph(graph):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), dict) or not isinstance(graph.get("edges"), list):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError("Cấu trúc graph không hợp lệ.", 500, "invalid_graph")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not graph["nodes"]:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError("Graph phải còn ít nhất một node.", 422, "empty_graph")
    # Ghi chú: Gán/cập nhật node_ids để lưu dữ liệu dùng ở bước tiếp theo.
    node_ids = set(graph["nodes"])
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node_id, node in graph["nodes"].items():
        # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
        coordinates = node.get("coordinates") if isinstance(node, dict) else None
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if (not isinstance(coordinates, list) or len(coordinates) < 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinates[:2])
                or not valid_lonlat(float(coordinates[0]), float(coordinates[1]))):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Tọa độ node {node_id} không hợp lệ.", 422, "invalid_coordinate")
    # Ghi chú: Gán/cập nhật edge_ids để lưu dữ liệu dùng ở bước tiếp theo.
    edge_ids = set()
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge in graph["edges"]:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(edge, dict):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError("Edge không hợp lệ.", 422, "invalid_edge")
        # Ghi chú: Gán/cập nhật edge_id để lưu dữ liệu dùng ở bước tiếp theo.
        edge_id = edge.get("edge_id")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Edge ID không hợp lệ hoặc trùng: {edge_id}.", 422, "duplicate_edge_id")
        edge_ids.add(edge_id)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(edge.get("way_id"), str) or not isinstance(edge.get("file"), str):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Edge {edge_id} thiếu way_id/file.", 422, "invalid_edge")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if (not isinstance(edge.get("from"), str) or not isinstance(edge.get("to"), str)
                or edge.get("from") not in node_ids or edge.get("to") not in node_ids):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Edge {edge_id} tham chiếu node không tồn tại.", 422, "dangling_edge")
        # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
        coordinates = edge.get("coordinates")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Edge {edge_id} cần ít nhất hai tọa độ.", 422, "invalid_geometry")
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for point in coordinates:
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if (not isinstance(point, list) or len(point) < 2
                    or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in point[:2])
                    or not valid_lonlat(float(point[0]), float(point[1]))):
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise GraphEditError(f"Edge {edge_id} có tọa độ không hợp lệ.", 422, "invalid_coordinate")
        # Ghi chú: Gán/cập nhật length để lưu dữ liệu dùng ở bước tiếp theo.
        length = edge.get("length_m")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(length, (int, float)) or not math.isfinite(length) or length <= 0:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Edge {edge_id} cần length_m dương.", 422, "invalid_length")


# Ghi chú: Hàm _measure_line; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _measure_line(coords, transformer):
    # Ghi chú: Gán/cập nhật points để lưu dữ liệu dùng ở bước tiếp theo.
    points = [transformer.forward(point) for point in coords]
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


# Ghi chú: Hàm _normalize_edited_edge; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _normalize_edited_edge(edge, graph, transformer, allow_existing_self_loop=False):
    # Ghi chú: Gán/cập nhật edge để lưu dữ liệu dùng ở bước tiếp theo.
    edge = dict(edge)
    # Ghi chú: Gán/cập nhật (edge_id, source, target) để lưu dữ liệu dùng ở bước tiếp theo.
    edge_id, source, target = edge.get("edge_id"), edge.get("from"), edge.get("to")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if source == target and not allow_existing_self_loop:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError(f"Edge {edge_id} không thể nối node với chính nó.", 422, "self_loop")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if (not isinstance(source, str) or not isinstance(target, str)
            or source not in graph["nodes"] or target not in graph["nodes"]):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError(f"Edge {edge_id} tham chiếu node không tồn tại.", 422, "dangling_edge")
    # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
    coordinates = edge.get("coordinates")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError(f"Edge {edge_id} cần ít nhất hai tọa độ.", 422, "invalid_geometry")
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for point in coordinates:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if (not isinstance(point, (list, tuple)) or len(point) < 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in point[:2])
                or not valid_lonlat(float(point[0]), float(point[1]))):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Edge {edge_id} có tọa độ không hợp lệ.", 422, "invalid_coordinate")
    # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
    coordinates = [list(point[:2]) for point in coordinates]
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not (source == target and allow_existing_self_loop):
        # Ghi chú: Gán/cập nhật coordinates[0] để lưu dữ liệu dùng ở bước tiếp theo.
        coordinates[0] = list(graph["nodes"][source]["coordinates"][:2])
        # Ghi chú: Gán/cập nhật coordinates[-1] để lưu dữ liệu dùng ở bước tiếp theo.
        coordinates[-1] = list(graph["nodes"][target]["coordinates"][:2])
    # Ghi chú: Gán/cập nhật length để lưu dữ liệu dùng ở bước tiếp theo.
    length = _measure_line(coordinates, transformer)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not math.isfinite(length) or length <= 0:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError(f"Edge {edge_id} có chiều dài bằng 0 hoặc không hợp lệ.", 422, "invalid_length")
    # Ghi chú: Gán/cập nhật edge['coordinates'] để lưu dữ liệu dùng ở bước tiếp theo.
    edge["coordinates"] = coordinates
    # Ghi chú: Gán/cập nhật edge['length_m'] để lưu dữ liệu dùng ở bước tiếp theo.
    edge["length_m"] = round(length, 2)
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return edge


# Ghi chú: Hàm _derived_node_rows; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _derived_node_rows(graph):
    # Ghi chú: Gán/cập nhật (nodes, edges) để lưu dữ liệu dùng ở bước tiếp theo.
    nodes, edges = graph["nodes"], graph["edges"]
    # Ghi chú: Gán/cập nhật neighbors để lưu dữ liệu dùng ở bước tiếp theo.
    neighbors = {node_id: [] for node_id in nodes}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge in edges:
        neighbors[edge["from"]].append(edge["to"])
        neighbors[edge["to"]].append(edge["from"])
    # Ghi chú: Gán/cập nhật components để lưu dữ liệu dùng ở bước tiếp theo.
    components = {}
    # Ghi chú: Gán/cập nhật component để lưu dữ liệu dùng ở bước tiếp theo.
    component = 0
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node_id in nodes:
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if node_id in components:
            continue
        component += 1
        # Ghi chú: Gán/cập nhật stack để lưu dữ liệu dùng ở bước tiếp theo.
        stack = [node_id]
        # Ghi chú: Gán/cập nhật components[node_id] để lưu dữ liệu dùng ở bước tiếp theo.
        components[node_id] = component
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        while stack:
            # Ghi chú: Gán/cập nhật current để lưu dữ liệu dùng ở bước tiếp theo.
            current = stack.pop()
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for other in neighbors[current]:
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if other not in components:
                    # Ghi chú: Gán/cập nhật components[other] để lưu dữ liệu dùng ở bước tiếp theo.
                    components[other] = component
                    stack.append(other)
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return [{"node_id": node_id, "component": components[node_id],
             "longitude": nodes[node_id]["coordinates"][0],
             "latitude": nodes[node_id]["coordinates"][1],
             "degree": len(neighbors[node_id])}
            for node_id in nodes]


# Ghi chú: Hàm _write_temp; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def _write_temp(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return Path(handle.name)


# Ghi chú: Hàm save_graph_changes; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def save_graph_changes(payload, graph_path, derived_path, backup_dir, log_path):
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), dict):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError("Yêu cầu lưu cần object changes.")
    # Ghi chú: Gán/cập nhật (graph_path, derived_path) để lưu dữ liệu dùng ở bước tiếp theo.
    graph_path, derived_path = Path(graph_path), Path(derived_path)
    # Ghi chú: Gán/cập nhật raw để lưu dữ liệu dùng ở bước tiếp theo.
    raw = graph_path.read_bytes()
    # Ghi chú: Gán/cập nhật current_revision để lưu dữ liệu dùng ở bước tiếp theo.
    current_revision = graph_revision(raw)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if payload.get("base_revision") != current_revision:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError("Graph đã thay đổi kể từ lúc mở editor. Hãy tải lại trước khi lưu.", 409, "revision_conflict")
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
        graph = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError(f"Graph JSON không hợp lệ: {error}", 500, "invalid_graph")
    # Ghi chú: Gán/cập nhật changes để lưu dữ liệu dùng ở bước tiếp theo.
    changes = payload["changes"]
    # Ghi chú: Gán/cập nhật node_changes để lưu dữ liệu dùng ở bước tiếp theo.
    node_changes = changes.get("nodes", {})
    # Ghi chú: Gán/cập nhật edge_changes để lưu dữ liệu dùng ở bước tiếp theo.
    edge_changes = changes.get("edges", {})
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if not isinstance(node_changes, dict) or not isinstance(edge_changes, dict):
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError("Patch nodes/edges không hợp lệ.")
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if len(node_changes) + len(edge_changes) > 1000:
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise GraphEditError("Patch quá lớn.", 413, "patch_too_large")

    # Ghi chú: Gán/cập nhật original_nodes để lưu dữ liệu dùng ở bước tiếp theo.
    original_nodes = json.loads(json.dumps(graph["nodes"]))
    # Ghi chú: Gán/cập nhật original_edges để lưu dữ liệu dùng ở bước tiếp theo.
    original_edges = {edge["edge_id"]: edge for edge in graph["edges"]}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node_id, value in node_changes.items():
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if value is not None and not isinstance(value, dict):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Node patch {node_id} không hợp lệ.")
        # Ghi chú: Gán/cập nhật old_node để lưu dữ liệu dùng ở bước tiếp theo.
        old_node = graph["nodes"].get(node_id)
        # Ghi chú: Gán/cập nhật changed_position để lưu dữ liệu dùng ở bước tiếp theo.
        changed_position = (old_node is not None and value is not None
                            and value.get("coordinates", old_node["coordinates"])[:2] != old_node["coordinates"][:2])
        # Ghi chú: Gán/cập nhật deleting để lưu dữ liệu dùng ở bước tiếp theo.
        deleting = old_node is not None and value is None
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if changed_position or deleting:
            # Ghi chú: Gán/cập nhật incident_ids để lưu dữ liệu dùng ở bước tiếp theo.
            incident_ids = {edge_id for edge_id, edge in original_edges.items()
                            if node_id in (edge["from"], edge["to"])}
            # Ghi chú: Gán/cập nhật missing_updates để lưu dữ liệu dùng ở bước tiếp theo.
            missing_updates = incident_ids - set(edge_changes)
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if missing_updates:
                # Ghi chú: Gán/cập nhật action để lưu dữ liệu dùng ở bước tiếp theo.
                action = "di chuyển" if changed_position else "xóa"
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise GraphEditError(
                    f"Không thể {action} node {node_id}: patch thiếu edge liên quan {', '.join(sorted(missing_updates))}.",
                    422, "incomplete_node_edit")

    # Only listed node/edge IDs are touched. Existing edge/node attributes not
    # included in a coordinate edit are preserved from the current file.
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for node_id, value in node_changes.items():
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if value is None:
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if node_id not in graph["nodes"]:
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise GraphEditError(f"Không tìm thấy node {node_id} để xóa.", 404, "node_not_found")
            del graph["nodes"][node_id]
            continue
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(value, dict):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Node patch {node_id} không hợp lệ.")
        # Ghi chú: Gán/cập nhật coordinates để lưu dữ liệu dùng ở bước tiếp theo.
        coordinates = value.get("coordinates")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if (not isinstance(coordinates, list) or len(coordinates) < 2
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coordinates[:2])
                or not valid_lonlat(float(coordinates[0]), float(coordinates[1]))):
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Tọa độ node {node_id} không hợp lệ.", 422, "invalid_coordinate")
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if node_id in graph["nodes"]:
            # Ghi chú: Gán/cập nhật graph['nodes'][node_id]['coordinates'] để lưu dữ liệu dùng ở bước tiếp theo.
            graph["nodes"][node_id]["coordinates"] = [float(coordinates[0]), float(coordinates[1])]
        else:
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if value.get("id", node_id) != node_id:
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise GraphEditError("Node ID trong patch không khớp key.")
            # Ghi chú: Gán/cập nhật graph['nodes'][node_id] để lưu dữ liệu dùng ở bước tiếp theo.
            graph["nodes"][node_id] = {"coordinates": [float(coordinates[0]), float(coordinates[1])],
                                       "endpoint_refs": list(value.get("endpoint_refs", []))}

    # Ghi chú: Gán/cập nhật edge_map để lưu dữ liệu dùng ở bước tiếp theo.
    edge_map = {edge["edge_id"]: edge for edge in graph["edges"]}
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge_id, value in edge_changes.items():
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if value is None:
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if edge_id not in edge_map:
                # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
                raise GraphEditError(f"Không tìm thấy edge {edge_id} để xóa.", 404, "edge_not_found")
            del edge_map[edge_id]
            continue
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if not isinstance(value, dict) or value.get("edge_id") != edge_id:
            # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
            raise GraphEditError(f"Edge patch {edge_id} không hợp lệ.")
        # Ghi chú: Gán/cập nhật edge_map[edge_id] để lưu dữ liệu dùng ở bước tiếp theo.
        edge_map[edge_id] = value
    # Ghi chú: Gán/cập nhật graph['edges'] để lưu dữ liệu dùng ở bước tiếp theo.
    graph["edges"] = list(edge_map.values())

    # Recalculate only edges named in the patch. Unrelated edge JSON stays
    # byte-for-byte equivalent at the object level.
    # Ghi chú: Gán/cập nhật transformer để lưu dữ liệu dùng ở bước tiếp theo.
    transformer = projection_for_graph(graph)
    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
    for edge_id, value in edge_changes.items():
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if value is not None:
            # Ghi chú: Gán/cập nhật old_edge để lưu dữ liệu dùng ở bước tiếp theo.
            old_edge = original_edges.get(edge_id)
            # Ghi chú: Gán/cập nhật allow_self_loop để lưu dữ liệu dùng ở bước tiếp theo.
            allow_self_loop = old_edge is not None and old_edge["from"] == old_edge["to"]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if allow_self_loop and old_edge["from"] in original_nodes:
                # Ghi chú: Gán/cập nhật old_coordinate để lưu dữ liệu dùng ở bước tiếp theo.
                old_coordinate = original_nodes[old_edge["from"]]["coordinates"]
                # Ghi chú: Gán/cập nhật new_coordinate để lưu dữ liệu dùng ở bước tiếp theo.
                new_coordinate = graph["nodes"][old_edge["from"]]["coordinates"]
                # Ghi chú: Gán/cập nhật delta để lưu dữ liệu dùng ở bước tiếp theo.
                delta = [new_coordinate[0] - old_coordinate[0], new_coordinate[1] - old_coordinate[1]]
                # Ghi chú: Gán/cập nhật edge_map[edge_id] để lưu dữ liệu dùng ở bước tiếp theo.
                edge_map[edge_id] = dict(edge_map[edge_id])
                # Ghi chú: Gán/cập nhật edge_map[edge_id]['coordinates'] để lưu dữ liệu dùng ở bước tiếp theo.
                edge_map[edge_id]["coordinates"] = [
                    [float(point[0]) + delta[0], float(point[1]) + delta[1]]
                    for point in old_edge["coordinates"]
                ]
            # Ghi chú: Gán/cập nhật edge_map[edge_id] để lưu dữ liệu dùng ở bước tiếp theo.
            edge_map[edge_id] = _normalize_edited_edge(edge_map[edge_id], graph, transformer, allow_self_loop)
    # Ghi chú: Gán/cập nhật graph['edges'] để lưu dữ liệu dùng ở bước tiếp theo.
    graph["edges"] = list(edge_map.values())
    validate_graph(graph)
    # Node deletion with remaining incident edges is rejected by validate_graph.

    # Ghi chú: Gán/cập nhật editor để lưu dữ liệu dùng ở bước tiếp theo.
    editor = str(payload.get("actor", "")).strip()[:100] or "unspecified"
    # Ghi chú: Gán/cập nhật timestamp để lưu dữ liệu dùng ở bước tiếp theo.
    timestamp = datetime.now(timezone.utc).isoformat()
    # Ghi chú: Gán/cập nhật backup_dir để lưu dữ liệu dùng ở bước tiếp theo.
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    # Ghi chú: Gán/cập nhật backup_stem để lưu dữ liệu dùng ở bước tiếp theo.
    backup_stem = datetime.now(timezone.utc).strftime("graph-%Y%m%dT%H%M%S.%fZ")
    # Ghi chú: Gán/cập nhật graph_backup để lưu dữ liệu dùng ở bước tiếp theo.
    graph_backup = backup_dir / f"{backup_stem}.json"
    # Ghi chú: Gán/cập nhật derived_backup để lưu dữ liệu dùng ở bước tiếp theo.
    derived_backup = backup_dir / f"{backup_stem}.graph_nodes.csv"
    graph_backup.write_bytes(raw)
    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
    if derived_path.exists():
        derived_backup.write_bytes(derived_path.read_bytes())

    # Ghi chú: Gán/cập nhật graph_bytes để lưu dữ liệu dùng ở bước tiếp theo.
    graph_bytes = (json.dumps(graph, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # Ghi chú: Gán/cập nhật rows để lưu dữ liệu dùng ở bước tiếp theo.
    rows = _derived_node_rows(graph)
    # Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
    import io
    # Ghi chú: Gán/cập nhật buffer để lưu dữ liệu dùng ở bước tiếp theo.
    buffer = io.StringIO(newline="")
    # Ghi chú: Gán/cập nhật writer để lưu dữ liệu dùng ở bước tiếp theo.
    writer = csv.DictWriter(buffer, fieldnames=["node_id", "component", "longitude", "latitude", "degree"])
    writer.writeheader()
    writer.writerows(rows)
    # Ghi chú: Gán/cập nhật derived_bytes để lưu dữ liệu dùng ở bước tiếp theo.
    derived_bytes = ("\ufeff" + buffer.getvalue()).encode("utf-8")
    # Ghi chú: Gán/cập nhật graph_temp để lưu dữ liệu dùng ở bước tiếp theo.
    graph_temp = _write_temp(graph_path, graph_bytes)
    # Ghi chú: Gán/cập nhật derived_temp để lưu dữ liệu dùng ở bước tiếp theo.
    derived_temp = _write_temp(derived_path, derived_bytes)
    # Ghi chú: Bắt đầu khối xử lý ngoại lệ cho thao tác có thể thất bại.
    try:
        os.replace(graph_temp, graph_path)
        os.replace(derived_temp, derived_path)
    except OSError:
        # Restore the previous graph if the derived file could not be swapped.
        graph_path.write_bytes(raw)
        # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
        if derived_backup.exists():
            derived_path.write_bytes(derived_backup.read_bytes())
        # Ghi chú: Phát sinh lỗi để báo điều kiện không thể tiếp tục.
        raise
    finally:
        graph_temp.unlink(missing_ok=True)
        derived_temp.unlink(missing_ok=True)

    # Ghi chú: Gán/cập nhật log_record để lưu dữ liệu dùng ở bước tiếp theo.
    log_record = {"timestamp": timestamp, "actor": editor, "base_revision": current_revision,
                  "revision": graph_revision(graph_bytes), "changes": changes}
    # Ghi chú: Gán/cập nhật log_path để lưu dữ liệu dùng ở bước tiếp theo.
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_record, ensure_ascii=False) + "\n")
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {"graph": graph, "revision": graph_revision(graph_bytes),
            "backup": str(graph_backup), "derived_backup": str(derived_backup) if derived_backup.exists() else None,
            "timestamp": timestamp, "actor": editor}
