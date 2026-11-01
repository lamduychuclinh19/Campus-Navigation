"""Focused, isolated tests for patch-based routing graph editing."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graph_editor import GraphEditError, graph_revision, load_graph_snapshot, save_graph_changes


class GraphEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="campusnav-graph-editor-")
        self.root = Path(self.temp.name)
        self.graph_path = self.root / "graph.json"
        self.derived_path = self.root / "graph_nodes.csv"
        self.backup_dir = self.root / "backups"
        self.log_path = self.root / "graph_edit_log.jsonl"
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

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, changes, revision=None):
        raw = self.graph_path.read_bytes()
        return {"base_revision": revision or graph_revision(raw), "actor": "test-admin", "changes": changes}

    def save(self, changes):
        return save_graph_changes(self.payload(changes), self.graph_path, self.derived_path,
                                  self.backup_dir, self.log_path)

    def test_move_node_updates_every_incident_edge_only(self):
        before = json.loads(self.graph_path.read_text())
        result = self.save({"nodes": {"N002": {"coordinates": [106.6811, 10.7601]}},
                            "edges": {"w1_part01": {**before["edges"][0],
                                "coordinates": [[106.68, 10.76], [106.6811, 10.7601]]}}})
        saved = result["graph"]
        self.assertEqual(saved["nodes"]["N002"]["coordinates"], [106.6811, 10.7601])
        self.assertEqual(saved["edges"][0]["coordinates"][-1], [106.6811, 10.7601])
        self.assertGreater(saved["edges"][0]["length_m"], 0)
        self.assertEqual(saved["edges"][1], before["edges"][1])
        reloaded, revision = load_graph_snapshot(self.graph_path)
        self.assertEqual(reloaded["nodes"]["N002"]["coordinates"], [106.6811, 10.7601])
        self.assertEqual(revision, result["revision"])

    def test_incomplete_move_is_rejected_without_write(self):
        raw = self.graph_path.read_bytes()
        with self.assertRaises(GraphEditError) as error:
            self.save({"nodes": {"N002": {"coordinates": [106.6811, 10.76]}}, "edges": {}})
        self.assertEqual(error.exception.code, "incomplete_node_edit")
        self.assertEqual(self.graph_path.read_bytes(), raw)

    def test_add_and_connect_nodes(self):
        changes = {"nodes": {"N005": {"coordinates": [106.684, 10.76], "endpoint_refs": []}},
                   "edges": {"edit_001": {"edge_id": "edit_001", "way_id": "manual_edit", "file": "manual_edit",
                       "from": "N004", "to": "N005", "length_m": 1,
                       "coordinates": [[106.683, 10.76], [106.684, 10.76]]}}}
        saved = self.save(changes)["graph"]
        self.assertIn("N005", saved["nodes"])
        edge = next(item for item in saved["edges"] if item["edge_id"] == "edit_001")
        self.assertAlmostEqual(edge["length_m"], 109.64, delta=1.0)
        self.assertEqual(edge["from"], "N004")

    def test_split_edge_and_delete_requires_edges_removed_first(self):
        before = json.loads(self.graph_path.read_text())["edges"][0]
        changes = {"nodes": {"N005": {"coordinates": [106.6805, 10.76], "endpoint_refs": []}},
                   "edges": {
                       "w1_part01": {**before, "to": "N005", "coordinates": [[106.68, 10.76], [106.6805, 10.76]]},
                       "edit_001": {**before, "edge_id": "edit_001", "from": "N005", "coordinates": [[106.6805, 10.76], [106.681, 10.76]]}}}
        saved = self.save(changes)["graph"]
        self.assertEqual(len(saved["edges"]), 3)
        split_lengths = sum(edge["length_m"] for edge in saved["edges"] if edge["edge_id"] in ("w1_part01", "edit_001"))
        self.assertAlmostEqual(split_lengths, 109.64, delta=1.0)
        revision = load_graph_snapshot(self.graph_path)[1]
        with self.assertRaises(GraphEditError):
            save_graph_changes({"base_revision": revision, "changes": {"nodes": {"N005": None}, "edges": {}}},
                               self.graph_path, self.derived_path, self.backup_dir, self.log_path)

    def test_delete_edge_then_isolated_node(self):
        self.save({"nodes": {"N005": {"coordinates": [106.684, 10.76], "endpoint_refs": []}},
                   "edges": {"edit_001": {"edge_id": "edit_001", "way_id": "manual_edit", "file": "manual_edit",
                       "from": "N004", "to": "N005", "length_m": 1,
                       "coordinates": [[106.683, 10.76], [106.684, 10.76]]}}})
        revision=load_graph_snapshot(self.graph_path)[1]
        saved=save_graph_changes({"base_revision":revision,"changes":{"nodes":{"N005":None},"edges":{"edit_001":None}}},
                                 self.graph_path,self.derived_path,self.backup_dir,self.log_path)
        self.assertNotIn("N005",saved["graph"]["nodes"])
        self.assertNotIn("edit_001",{edge["edge_id"] for edge in saved["graph"]["edges"]})

    def test_stale_revision_and_bad_coordinates_are_rejected(self):
        raw = self.graph_path.read_bytes()
        with self.assertRaises(GraphEditError) as error:
            save_graph_changes({"base_revision": "stale", "changes": {}}, self.graph_path, self.derived_path,
                               self.backup_dir, self.log_path)
        self.assertEqual(error.exception.code, "revision_conflict")
        with self.assertRaises(GraphEditError):
            self.save({"nodes": {"N002": {"coordinates": [500, 100]}}, "edges": {}})
        self.assertEqual(self.graph_path.read_bytes(), raw)

    def test_dangling_reference_and_zero_length_edge_are_rejected(self):
        raw=self.graph_path.read_bytes();graph=json.loads(raw)
        with self.assertRaises(GraphEditError):
            self.save({"nodes":{},"edges":{"edit_001":{"edge_id":"edit_001","way_id":"manual_edit","file":"manual_edit",
                "from":"MISSING","to":"N001","length_m":1,"coordinates":[[106.68,10.76],[106.68,10.76]]}}})
        same=graph["nodes"]["N001"]["coordinates"]
        with self.assertRaises(GraphEditError) as error:
            self.save({"nodes":{"N002":{"coordinates":same}},"edges":{"w1_part01":{**graph["edges"][0],
                "coordinates":[same,same]}}})
        self.assertEqual(error.exception.code,"invalid_length")
        self.assertEqual(self.graph_path.read_bytes(),raw)

    def test_backup_can_restore_graph_and_derived_file(self):
        original_graph = self.graph_path.read_bytes()
        original_derived = self.derived_path.read_bytes()
        before = json.loads(original_graph)
        self.save({"nodes": {"N002": {"coordinates": [106.6811, 10.76]}},
                   "edges": {"w1_part01": {**before["edges"][0],
                       "coordinates": [[106.68, 10.76], [106.6811, 10.76]]}}})
        graph_backup = next(self.backup_dir.glob("*.json"))
        derived_backup = next(self.backup_dir.glob("*.graph_nodes.csv"))
        shutil.copy2(graph_backup, self.graph_path)
        shutil.copy2(derived_backup, self.derived_path)
        self.assertEqual(self.graph_path.read_bytes(), original_graph)
        self.assertEqual(self.derived_path.read_bytes(), original_derived)
        record = json.loads(self.log_path.read_text().splitlines()[0])
        self.assertEqual(record["actor"], "test-admin")
        self.assertIn("timestamp", record)


if __name__ == "__main__":
    unittest.main()
