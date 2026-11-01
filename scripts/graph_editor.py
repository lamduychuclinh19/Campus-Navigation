"""Safe, patch-based edits for the campus routing graph."""

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from gps_routing import LocalAEQD, projection_for_graph, valid_lonlat


class GraphEditError(ValueError):
    def __init__(self, message, status=400, code="invalid_edit"):
        super().__init__(message)
        self.status = status
        self.code = code


def graph_revision(raw):
    return hashlib.sha256(raw).hexdigest()


def load_graph_snapshot(graph_path):
    raw = graph_path.read_bytes()
    try:
        graph = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GraphEditError(f"Không đọc được graph JSON: {error}", 500, "invalid_graph")
    validate_graph(graph)
    return graph, graph_revision(raw)


def validate_graph(graph):
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), dict) or not isinstance(graph.get("edges"), list):
        raise GraphEditError("Cấu trúc graph không hợp lệ.", 500, "invalid_graph")
    if not graph["nodes"]:
        raise GraphEditError("Graph phải còn ít nhất một node.", 422, "empty_graph")
    node_ids = set(graph["nodes"])
    for node_id, node in graph["nodes"].items():
        coordinates = node.get("coordinates") if isinstance(node, dict) else None
        if (not isinstance(coordinates, list) or len(coordinates) < 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in coordinates[:2])
                or not valid_lonlat(float(coordinates[0]), float(coordinates[1]))):
            raise GraphEditError(f"Tọa độ node {node_id} không hợp lệ.", 422, "invalid_coordinate")
    edge_ids = set()
    for edge in graph["edges"]:
        if not isinstance(edge, dict):
            raise GraphEditError("Edge không hợp lệ.", 422, "invalid_edge")
        edge_id = edge.get("edge_id")
        if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
            raise GraphEditError(f"Edge ID không hợp lệ hoặc trùng: {edge_id}.", 422, "duplicate_edge_id")
        edge_ids.add(edge_id)
        if not isinstance(edge.get("way_id"), str) or not isinstance(edge.get("file"), str):
            raise GraphEditError(f"Edge {edge_id} thiếu way_id/file.", 422, "invalid_edge")
        if (not isinstance(edge.get("from"), str) or not isinstance(edge.get("to"), str)
                or edge.get("from") not in node_ids or edge.get("to") not in node_ids):
            raise GraphEditError(f"Edge {edge_id} tham chiếu node không tồn tại.", 422, "dangling_edge")
        coordinates = edge.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise GraphEditError(f"Edge {edge_id} cần ít nhất hai tọa độ.", 422, "invalid_geometry")
        for point in coordinates:
            if (not isinstance(point, list) or len(point) < 2
                    or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in point[:2])
                    or not valid_lonlat(float(point[0]), float(point[1]))):
                raise GraphEditError(f"Edge {edge_id} có tọa độ không hợp lệ.", 422, "invalid_coordinate")
        length = edge.get("length_m")
        if not isinstance(length, (int, float)) or not math.isfinite(length) or length <= 0:
            raise GraphEditError(f"Edge {edge_id} cần length_m dương.", 422, "invalid_length")


def _measure_line(coords, transformer):
    points = [transformer.forward(point) for point in coords]
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def _normalize_edited_edge(edge, graph, transformer, allow_existing_self_loop=False):
    edge = dict(edge)
    edge_id, source, target = edge.get("edge_id"), edge.get("from"), edge.get("to")
    if source == target and not allow_existing_self_loop:
        raise GraphEditError(f"Edge {edge_id} không thể nối node với chính nó.", 422, "self_loop")
    if (not isinstance(source, str) or not isinstance(target, str)
            or source not in graph["nodes"] or target not in graph["nodes"]):
        raise GraphEditError(f"Edge {edge_id} tham chiếu node không tồn tại.", 422, "dangling_edge")
    coordinates = edge.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise GraphEditError(f"Edge {edge_id} cần ít nhất hai tọa độ.", 422, "invalid_geometry")
    for point in coordinates:
        if (not isinstance(point, (list, tuple)) or len(point) < 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in point[:2])
                or not valid_lonlat(float(point[0]), float(point[1]))):
            raise GraphEditError(f"Edge {edge_id} có tọa độ không hợp lệ.", 422, "invalid_coordinate")
    coordinates = [list(point[:2]) for point in coordinates]
    if not (source == target and allow_existing_self_loop):
        coordinates[0] = list(graph["nodes"][source]["coordinates"][:2])
        coordinates[-1] = list(graph["nodes"][target]["coordinates"][:2])
    length = _measure_line(coordinates, transformer)
    if not math.isfinite(length) or length <= 0:
        raise GraphEditError(f"Edge {edge_id} có chiều dài bằng 0 hoặc không hợp lệ.", 422, "invalid_length")
    edge["coordinates"] = coordinates
    edge["length_m"] = round(length, 2)
    return edge


def _derived_node_rows(graph):
    nodes, edges = graph["nodes"], graph["edges"]
    neighbors = {node_id: [] for node_id in nodes}
    for edge in edges:
        neighbors[edge["from"]].append(edge["to"])
        neighbors[edge["to"]].append(edge["from"])
    components = {}
    component = 0
    for node_id in nodes:
        if node_id in components:
            continue
        component += 1
        stack = [node_id]
        components[node_id] = component
        while stack:
            current = stack.pop()
            for other in neighbors[current]:
                if other not in components:
                    components[other] = component
                    stack.append(other)
    return [{"node_id": node_id, "component": components[node_id],
             "longitude": nodes[node_id]["coordinates"][0],
             "latitude": nodes[node_id]["coordinates"][1],
             "degree": len(neighbors[node_id])}
            for node_id in nodes]


def _write_temp(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def save_graph_changes(payload, graph_path, derived_path, backup_dir, log_path):
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), dict):
        raise GraphEditError("Yêu cầu lưu cần object changes.")
    graph_path, derived_path = Path(graph_path), Path(derived_path)
    raw = graph_path.read_bytes()
    current_revision = graph_revision(raw)
    if payload.get("base_revision") != current_revision:
        raise GraphEditError("Graph đã thay đổi kể từ lúc mở editor. Hãy tải lại trước khi lưu.", 409, "revision_conflict")
    try:
        graph = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GraphEditError(f"Graph JSON không hợp lệ: {error}", 500, "invalid_graph")
    changes = payload["changes"]
    node_changes = changes.get("nodes", {})
    edge_changes = changes.get("edges", {})
    if not isinstance(node_changes, dict) or not isinstance(edge_changes, dict):
        raise GraphEditError("Patch nodes/edges không hợp lệ.")
    if len(node_changes) + len(edge_changes) > 1000:
        raise GraphEditError("Patch quá lớn.", 413, "patch_too_large")

    original_nodes = json.loads(json.dumps(graph["nodes"]))
    original_edges = {edge["edge_id"]: edge for edge in graph["edges"]}
    for node_id, value in node_changes.items():
        if value is not None and not isinstance(value, dict):
            raise GraphEditError(f"Node patch {node_id} không hợp lệ.")
        old_node = graph["nodes"].get(node_id)
        changed_position = (old_node is not None and value is not None
                            and value.get("coordinates", old_node["coordinates"])[:2] != old_node["coordinates"][:2])
        deleting = old_node is not None and value is None
        if changed_position or deleting:
            incident_ids = {edge_id for edge_id, edge in original_edges.items()
                            if node_id in (edge["from"], edge["to"])}
            missing_updates = incident_ids - set(edge_changes)
            if missing_updates:
                action = "di chuyển" if changed_position else "xóa"
                raise GraphEditError(
                    f"Không thể {action} node {node_id}: patch thiếu edge liên quan {', '.join(sorted(missing_updates))}.",
                    422, "incomplete_node_edit")

    # Only listed node/edge IDs are touched. Existing edge/node attributes not
    # included in a coordinate edit are preserved from the current file.
    for node_id, value in node_changes.items():
        if value is None:
            if node_id not in graph["nodes"]:
                raise GraphEditError(f"Không tìm thấy node {node_id} để xóa.", 404, "node_not_found")
            del graph["nodes"][node_id]
            continue
        if not isinstance(value, dict):
            raise GraphEditError(f"Node patch {node_id} không hợp lệ.")
        coordinates = value.get("coordinates")
        if (not isinstance(coordinates, list) or len(coordinates) < 2
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coordinates[:2])
                or not valid_lonlat(float(coordinates[0]), float(coordinates[1]))):
            raise GraphEditError(f"Tọa độ node {node_id} không hợp lệ.", 422, "invalid_coordinate")
        if node_id in graph["nodes"]:
            graph["nodes"][node_id]["coordinates"] = [float(coordinates[0]), float(coordinates[1])]
        else:
            if value.get("id", node_id) != node_id:
                raise GraphEditError("Node ID trong patch không khớp key.")
            graph["nodes"][node_id] = {"coordinates": [float(coordinates[0]), float(coordinates[1])],
                                       "endpoint_refs": list(value.get("endpoint_refs", []))}

    edge_map = {edge["edge_id"]: edge for edge in graph["edges"]}
    for edge_id, value in edge_changes.items():
        if value is None:
            if edge_id not in edge_map:
                raise GraphEditError(f"Không tìm thấy edge {edge_id} để xóa.", 404, "edge_not_found")
            del edge_map[edge_id]
            continue
        if not isinstance(value, dict) or value.get("edge_id") != edge_id:
            raise GraphEditError(f"Edge patch {edge_id} không hợp lệ.")
        edge_map[edge_id] = value
    graph["edges"] = list(edge_map.values())

    # Recalculate only edges named in the patch. Unrelated edge JSON stays
    # byte-for-byte equivalent at the object level.
    transformer = projection_for_graph(graph)
    for edge_id, value in edge_changes.items():
        if value is not None:
            old_edge = original_edges.get(edge_id)
            allow_self_loop = old_edge is not None and old_edge["from"] == old_edge["to"]
            if allow_self_loop and old_edge["from"] in original_nodes:
                old_coordinate = original_nodes[old_edge["from"]]["coordinates"]
                new_coordinate = graph["nodes"][old_edge["from"]]["coordinates"]
                delta = [new_coordinate[0] - old_coordinate[0], new_coordinate[1] - old_coordinate[1]]
                edge_map[edge_id] = dict(edge_map[edge_id])
                edge_map[edge_id]["coordinates"] = [
                    [float(point[0]) + delta[0], float(point[1]) + delta[1]]
                    for point in old_edge["coordinates"]
                ]
            edge_map[edge_id] = _normalize_edited_edge(edge_map[edge_id], graph, transformer, allow_self_loop)
    graph["edges"] = list(edge_map.values())
    validate_graph(graph)
    # Node deletion with remaining incident edges is rejected by validate_graph.

    editor = str(payload.get("actor", "")).strip()[:100] or "unspecified"
    timestamp = datetime.now(timezone.utc).isoformat()
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_stem = datetime.now(timezone.utc).strftime("graph-%Y%m%dT%H%M%S.%fZ")
    graph_backup = backup_dir / f"{backup_stem}.json"
    derived_backup = backup_dir / f"{backup_stem}.graph_nodes.csv"
    graph_backup.write_bytes(raw)
    if derived_path.exists():
        derived_backup.write_bytes(derived_path.read_bytes())

    graph_bytes = (json.dumps(graph, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    rows = _derived_node_rows(graph)
    import io
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["node_id", "component", "longitude", "latitude", "degree"])
    writer.writeheader()
    writer.writerows(rows)
    derived_bytes = ("\ufeff" + buffer.getvalue()).encode("utf-8")
    graph_temp = _write_temp(graph_path, graph_bytes)
    derived_temp = _write_temp(derived_path, derived_bytes)
    try:
        os.replace(graph_temp, graph_path)
        os.replace(derived_temp, derived_path)
    except OSError:
        # Restore the previous graph if the derived file could not be swapped.
        graph_path.write_bytes(raw)
        if derived_backup.exists():
            derived_path.write_bytes(derived_backup.read_bytes())
        raise
    finally:
        graph_temp.unlink(missing_ok=True)
        derived_temp.unlink(missing_ok=True)

    log_record = {"timestamp": timestamp, "actor": editor, "base_revision": current_revision,
                  "revision": graph_revision(graph_bytes), "changes": changes}
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_record, ensure_ascii=False) + "\n")
    return {"graph": graph, "revision": graph_revision(graph_bytes),
            "backup": str(graph_backup), "derived_backup": str(derived_backup) if derived_backup.exists() else None,
            "timestamp": timestamp, "actor": editor}
