"""Focused, isolated tests for patch-based routing graph editing."""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import json
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import shutil
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import tempfile
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import unittest
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from graph_editor import GraphEditError, graph_revision, load_graph_snapshot, save_graph_changes


# Ghi chú: Lớp GraphEditorTests; xem các câu lệnh bên dưới để theo dõi cách xử lý.
class GraphEditorTests(unittest.TestCase):
    # Ghi chú: Hàm setUp; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def setUp(self):
        # Ghi chú: Gán/cập nhật self.temp để lưu dữ liệu dùng ở bước tiếp theo.
        self.temp = tempfile.TemporaryDirectory(prefix="campusnav-graph-editor-")
        # Ghi chú: Gán/cập nhật self.root để lưu dữ liệu dùng ở bước tiếp theo.
        self.root = Path(self.temp.name)
        # Ghi chú: Gán/cập nhật self.graph_path để lưu dữ liệu dùng ở bước tiếp theo.
        self.graph_path = self.root / "graph.json"
        # Ghi chú: Gán/cập nhật self.derived_path để lưu dữ liệu dùng ở bước tiếp theo.
        self.derived_path = self.root / "graph_nodes.csv"
        # Ghi chú: Gán/cập nhật self.backup_dir để lưu dữ liệu dùng ở bước tiếp theo.
        self.backup_dir = self.root / "backups"
        # Ghi chú: Gán/cập nhật self.log_path để lưu dữ liệu dùng ở bước tiếp theo.
        self.log_path = self.root / "graph_edit_log.jsonl"
        # Ghi chú: Gán/cập nhật self.graph để lưu dữ liệu dùng ở bước tiếp theo.
        self.graph = {"directed": False, "nodes": {
            "N001": {"coordinates": [106.68, 10.76], "endpoint_refs": ["source-a"]},
            "N002": {"coordinates": [106.681, 10.76], "endpoint_refs": ["source-b"]},
            "N003": {"coordinates": [106.682, 10.76], "endpoint_refs": ["source-c"]},
            "N004": {"coordinates": [106.683, 10.76], "endpoint_refs": ["source-d"]}},
            "edges": [
                {"edge_id": "w1_part01", "way_id": "w1", "file": "w1.geojson", "from": "N001", "to": "N002",
                 "length_m": 10.0, "coordinates": [[106.68, 10.76], [106.681, 10.76]]},
                {"edge_id": "w2_part01", "way_id": "w2", "file": "w2.geojson", "from": "N003", "to": "N004",
                 "length_m": 10.0, "coordinates": [[106.682, 10.76], [106.683, 10.76]]}]}
        self.graph_path.write_text(json.dumps(self.graph), encoding="utf-8")
        self.derived_path.write_text("\ufeffnode_id,component,longitude,latitude,degree\n", encoding="utf-8")

    # Ghi chú: Hàm tearDown; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def tearDown(self):
        self.temp.cleanup()

    # Ghi chú: Hàm payload; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def payload(self, changes, revision=None):
        # Ghi chú: Gán/cập nhật raw để lưu dữ liệu dùng ở bước tiếp theo.
        raw = self.graph_path.read_bytes()
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return {"base_revision": revision or graph_revision(raw), "actor": "test-admin", "changes": changes}

    # Ghi chú: Hàm save; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def save(self, changes):
        # Ghi chú: Trả kết quả hiện tại về nơi gọi.
        return save_graph_changes(self.payload(changes), self.graph_path, self.derived_path,
                                  self.backup_dir, self.log_path)

    # Ghi chú: Hàm test_move_node_updates_every_incident_edge_only; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_move_node_updates_every_incident_edge_only(self):
        # Ghi chú: Gán/cập nhật before để lưu dữ liệu dùng ở bước tiếp theo.
        before = json.loads(self.graph_path.read_text())
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result = self.save({"nodes": {"N002": {"coordinates": [106.6811, 10.7601]}},
                            "edges": {"w1_part01": {**before["edges"][0],
                                "coordinates": [[106.68, 10.76], [106.6811, 10.7601]]}}})
        # Ghi chú: Gán/cập nhật saved để lưu dữ liệu dùng ở bước tiếp theo.
        saved = result["graph"]
        self.assertEqual(saved["nodes"]["N002"]["coordinates"], [106.6811, 10.7601])
        self.assertEqual(saved["edges"][0]["coordinates"][-1], [106.6811, 10.7601])
        self.assertGreater(saved["edges"][0]["length_m"], 0)
        self.assertEqual(saved["edges"][1], before["edges"][1])
        # Ghi chú: Gán/cập nhật (reloaded, revision) để lưu dữ liệu dùng ở bước tiếp theo.
        reloaded, revision = load_graph_snapshot(self.graph_path)
        self.assertEqual(reloaded["nodes"]["N002"]["coordinates"], [106.6811, 10.7601])
        self.assertEqual(revision, result["revision"])

    # Ghi chú: Hàm test_incomplete_move_is_rejected_without_write; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_incomplete_move_is_rejected_without_write(self):
        # Ghi chú: Gán/cập nhật raw để lưu dữ liệu dùng ở bước tiếp theo.
        raw = self.graph_path.read_bytes()
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with self.assertRaises(GraphEditError) as error:
            self.save({"nodes": {"N002": {"coordinates": [106.6811, 10.76]}}, "edges": {}})
        self.assertEqual(error.exception.code, "incomplete_node_edit")
        self.assertEqual(self.graph_path.read_bytes(), raw)

    # Ghi chú: Hàm test_add_and_connect_nodes; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_add_and_connect_nodes(self):
        # Ghi chú: Gán/cập nhật changes để lưu dữ liệu dùng ở bước tiếp theo.
        changes = {"nodes": {"N005": {"coordinates": [106.684, 10.76], "endpoint_refs": []}},
                   "edges": {"edit_001": {"edge_id": "edit_001", "way_id": "manual_edit", "file": "manual_edit",
                       "from": "N004", "to": "N005", "length_m": 1,
                       "coordinates": [[106.683, 10.76], [106.684, 10.76]]}}}
        # Ghi chú: Gán/cập nhật saved để lưu dữ liệu dùng ở bước tiếp theo.
        saved = self.save(changes)["graph"]
        self.assertIn("N005", saved["nodes"])
        # Ghi chú: Gán/cập nhật edge để lưu dữ liệu dùng ở bước tiếp theo.
        edge = next(item for item in saved["edges"] if item["edge_id"] == "edit_001")
        self.assertAlmostEqual(edge["length_m"], 109.64, delta=1.0)
        self.assertEqual(edge["from"], "N004")

    # Ghi chú: Hàm test_split_edge_and_delete_requires_edges_removed_first; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_split_edge_and_delete_requires_edges_removed_first(self):
        # Ghi chú: Gán/cập nhật before để lưu dữ liệu dùng ở bước tiếp theo.
        before = json.loads(self.graph_path.read_text())["edges"][0]
        # Ghi chú: Gán/cập nhật changes để lưu dữ liệu dùng ở bước tiếp theo.
        changes = {"nodes": {"N005": {"coordinates": [106.6805, 10.76], "endpoint_refs": []}},
                   "edges": {
                       "w1_part01": {**before, "to": "N005", "coordinates": [[106.68, 10.76], [106.6805, 10.76]]},
                       "edit_001": {**before, "edge_id": "edit_001", "from": "N005", "coordinates": [[106.6805, 10.76], [106.681, 10.76]]}}}
        # Ghi chú: Gán/cập nhật saved để lưu dữ liệu dùng ở bước tiếp theo.
        saved = self.save(changes)["graph"]
        self.assertEqual(len(saved["edges"]), 3)
        # Ghi chú: Gán/cập nhật split_lengths để lưu dữ liệu dùng ở bước tiếp theo.
        split_lengths = sum(edge["length_m"] for edge in saved["edges"] if edge["edge_id"] in ("w1_part01", "edit_001"))
        self.assertAlmostEqual(split_lengths, 109.64, delta=1.0)
        # Ghi chú: Gán/cập nhật revision để lưu dữ liệu dùng ở bước tiếp theo.
        revision = load_graph_snapshot(self.graph_path)[1]
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with self.assertRaises(GraphEditError):
            save_graph_changes({"base_revision": revision, "changes": {"nodes": {"N005": None}, "edges": {}}},
                               self.graph_path, self.derived_path, self.backup_dir, self.log_path)

    # Ghi chú: Hàm test_delete_edge_then_isolated_node; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_delete_edge_then_isolated_node(self):
        self.save({"nodes": {"N005": {"coordinates": [106.684, 10.76], "endpoint_refs": []}},
                   "edges": {"edit_001": {"edge_id": "edit_001", "way_id": "manual_edit", "file": "manual_edit",
                       "from": "N004", "to": "N005", "length_m": 1,
                       "coordinates": [[106.683, 10.76], [106.684, 10.76]]}}})
        # Ghi chú: Gán/cập nhật revision để lưu dữ liệu dùng ở bước tiếp theo.
        revision=load_graph_snapshot(self.graph_path)[1]
        # Ghi chú: Gán/cập nhật saved để lưu dữ liệu dùng ở bước tiếp theo.
        saved=save_graph_changes({"base_revision":revision,"changes":{"nodes":{"N005":None},"edges":{"edit_001":None}}},
                                 self.graph_path,self.derived_path,self.backup_dir,self.log_path)
        self.assertNotIn("N005",saved["graph"]["nodes"])
        self.assertNotIn("edit_001",{edge["edge_id"] for edge in saved["graph"]["edges"]})

    # Ghi chú: Hàm test_stale_revision_and_bad_coordinates_are_rejected; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_stale_revision_and_bad_coordinates_are_rejected(self):
        # Ghi chú: Gán/cập nhật raw để lưu dữ liệu dùng ở bước tiếp theo.
        raw = self.graph_path.read_bytes()
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with self.assertRaises(GraphEditError) as error:
            save_graph_changes({"base_revision": "stale", "changes": {}}, self.graph_path, self.derived_path,
                               self.backup_dir, self.log_path)
        self.assertEqual(error.exception.code, "revision_conflict")
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with self.assertRaises(GraphEditError):
            self.save({"nodes": {"N002": {"coordinates": [500, 100]}}, "edges": {}})
        self.assertEqual(self.graph_path.read_bytes(), raw)

    # Ghi chú: Hàm test_dangling_reference_and_zero_length_edge_are_rejected; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_dangling_reference_and_zero_length_edge_are_rejected(self):
        # Ghi chú: Gán/cập nhật raw để lưu dữ liệu dùng ở bước tiếp theo.
        raw=self.graph_path.read_bytes();graph=json.loads(raw)
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with self.assertRaises(GraphEditError):
            self.save({"nodes":{},"edges":{"edit_001":{"edge_id":"edit_001","way_id":"manual_edit","file":"manual_edit",
                "from":"MISSING","to":"N001","length_m":1,"coordinates":[[106.68,10.76],[106.68,10.76]]}}})
        # Ghi chú: Gán/cập nhật same để lưu dữ liệu dùng ở bước tiếp theo.
        same=graph["nodes"]["N001"]["coordinates"]
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with self.assertRaises(GraphEditError) as error:
            self.save({"nodes":{"N002":{"coordinates":same}},"edges":{"w1_part01":{**graph["edges"][0],
                "coordinates":[same,same]}}})
        self.assertEqual(error.exception.code,"invalid_length")
        self.assertEqual(self.graph_path.read_bytes(),raw)

    # Ghi chú: Hàm test_backup_can_restore_graph_and_derived_file; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_backup_can_restore_graph_and_derived_file(self):
        # Ghi chú: Gán/cập nhật original_graph để lưu dữ liệu dùng ở bước tiếp theo.
        original_graph = self.graph_path.read_bytes()
        # Ghi chú: Gán/cập nhật original_derived để lưu dữ liệu dùng ở bước tiếp theo.
        original_derived = self.derived_path.read_bytes()
        # Ghi chú: Gán/cập nhật before để lưu dữ liệu dùng ở bước tiếp theo.
        before = json.loads(original_graph)
        self.save({"nodes": {"N002": {"coordinates": [106.6811, 10.76]}},
                   "edges": {"w1_part01": {**before["edges"][0],
                       "coordinates": [[106.68, 10.76], [106.6811, 10.76]]}}})
        # Ghi chú: Gán/cập nhật graph_backup để lưu dữ liệu dùng ở bước tiếp theo.
        graph_backup = next(self.backup_dir.glob("*.json"))
        # Ghi chú: Gán/cập nhật derived_backup để lưu dữ liệu dùng ở bước tiếp theo.
        derived_backup = next(self.backup_dir.glob("*.graph_nodes.csv"))
        shutil.copy2(graph_backup, self.graph_path)
        shutil.copy2(derived_backup, self.derived_path)
        self.assertEqual(self.graph_path.read_bytes(), original_graph)
        self.assertEqual(self.derived_path.read_bytes(), original_derived)
        # Ghi chú: Gán/cập nhật record để lưu dữ liệu dùng ở bước tiếp theo.
        record = json.loads(self.log_path.read_text().splitlines()[0])
        self.assertEqual(record["actor"], "test-admin")
        self.assertIn("timestamp", record)


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    unittest.main()
