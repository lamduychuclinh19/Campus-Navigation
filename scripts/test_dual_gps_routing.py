
"""Focused dual-routing tests using temporary in-memory graph snapshots."""

# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import copy
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from pathlib import Path
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import sys
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from dual_gps_routing import (
    MAX_NODE_CONNECTOR_DISTANCE_METERS, _connector_validation, _line_intersects_polygon,
    evaluate_gps_routes,
)
# Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
from gps_routing import LocalAEQD, get_places, projection_for_graph


# Ghi chú: Hàm fixture_graph; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def fixture_graph(directed=False):
    # Ghi chú: Gán/cập nhật center để lưu dữ liệu dùng ở bước tiếp theo.
    center = [106.682, 10.760]
    # Ghi chú: Gán/cập nhật project để lưu dữ liệu dùng ở bước tiếp theo.
    project = LocalAEQD(*center)
    # Ghi chú: Gán/cập nhật coords để lưu dữ liệu dùng ở bước tiếp theo.
    coords = {name: project.inverse(point) for name, point in {
        "N1":(0,0), "N2":(20,0), "N3":(40,0), "N4":(60,0)
    }.items()}
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return {"directed":directed,
            "nodes":{key:{"coordinates":value} for key,value in coords.items()},
            "edges":[
                {"edge_id":"E12","from":"N1","to":"N2","length_m":20.0,"coordinates":[coords['N1'],coords['N2']]},
                {"edge_id":"E23","from":"N2","to":"N3","length_m":20.0,"coordinates":[coords['N2'],coords['N3']]},
                {"edge_id":"E34","from":"N3","to":"N4","length_m":20.0,"coordinates":[coords['N3'],coords['N4']]}
            ]}, coords


# Ghi chú: Hàm access_rows; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def access_rows(coords, node="N4"):
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return [{"place_id":"DEST","confirmed_access":"yes","graph_node_candidate":node,
             "projected_boundary_lon":str(coords[node][0]),"projected_boundary_lat":str(coords[node][1])}]


# Ghi chú: Hàm run_eval; xem các câu lệnh bên dưới để theo dõi cách xử lý.
def run_eval(gps, graph=None, coords=None, **kwargs):
    # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
    graph, coords = (graph,coords) if graph is not None else fixture_graph()
    # Ghi chú: Gán/cập nhật buildings để lưu dữ liệu dùng ở bước tiếp theo.
    buildings=kwargs.pop("buildings", [])
    # Ghi chú: Trả kết quả hiện tại về nơi gọi.
    return evaluate_gps_routes({"latitude":gps[1],"longitude":gps[0],"accuracy":3.0,
                                "location_source":"browser","destination_place_id":"DEST"},
                               graph=graph, access_rows=access_rows(coords), buildings=buildings, **kwargs)


# Ghi chú: Lớp DualGpsRoutingTests; xem các câu lệnh bên dưới để theo dõi cách xử lý.
class DualGpsRoutingTests(unittest.TestCase):
    # Ghi chú: Hàm test_01_gps_exactly_on_edge; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_01_gps_exactly_on_edge(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph, coords = fixture_graph(); tr=projection_for_graph(graph)
        # Ghi chú: Gán/cập nhật gps để lưu dữ liệu dùng ở bước tiếp theo.
        gps=tr.inverse((-20,0)); result=run_eval(gps,graph,coords)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"SUCCESS")
        self.assertAlmostEqual(result["candidates"]["nearest_edge"]["connector_distance_meters"],0,places=1)

    # Ghi chú: Hàm test_02_gps_near_middle_of_two_nodes; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_02_gps_near_middle_of_two_nodes(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph, coords = fixture_graph(); tr=projection_for_graph(graph)
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result=run_eval(tr.inverse((-20,4)),graph,coords)
        self.assertEqual(result["evaluation"]["status"],"SUCCESS")
        self.assertLess(result["candidates"]["nearest_node"]["connector_distance_meters"],MAX_NODE_CONNECTOR_DISTANCE_METERS)

    # Ghi chú: Hàm test_03_gps_sits_at_junction; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_03_gps_sits_at_junction(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph, coords = fixture_graph(); result=run_eval(coords["N2"],graph,coords)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"SUCCESS")
        self.assertEqual(result["candidates"]["nearest_node"]["graph_node_id"],"N2")

    # Ghi chú: Hàm test_04_connector_crosses_building_is_invalid; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_04_connector_crosses_building_is_invalid(self):
        # Ghi chú: Gán/cập nhật polygon để lưu dữ liệu dùng ở bước tiếp theo.
        polygon={"type":"Polygon","coordinates":[[[106.6819,10.7599],[106.6821,10.7599],[106.6821,10.7601],[106.6819,10.7601],[106.6819,10.7599]]]}
        # Ghi chú: Gán/cập nhật status để lưu dữ liệu dùng ở bước tiếp theo.
        status=_connector_validation([106.6818,10.76],[106.6822,10.76],[("BLDG",polygon)])
        self.assertEqual(status["status"],"INVALID")

    # Ghi chú: Hàm test_17_touching_boundary_is_allowed_but_interior_is_blocked; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_17_touching_boundary_is_allowed_but_interior_is_blocked(self):
        # Ghi chú: Gán/cập nhật ring để lưu dữ liệu dùng ở bước tiếp theo.
        ring=[(0,0),(1,0),(1,1),(0,1),(0,0)]
        self.assertFalse(_line_intersects_polygon((0,0),(0,0),[ring]))
        self.assertFalse(_line_intersects_polygon((0,0),(-1,0),[ring]))
        self.assertTrue(_line_intersects_polygon((0,0),(0.5,0.5),[ring]))
        self.assertTrue(_line_intersects_polygon((0.5,0.5),(0.5,0.5),[ring]))
        # Ghi chú: Gán/cập nhật small_ring để lưu dữ liệu dùng ở bước tiếp theo.
        small_ring=[(0,0),(0.001,0),(0.001,0.001),(0,0.001),(0,0)]
        self.assertTrue(_line_intersects_polygon((0.0005,0.00001),(0.0005,0.00001),[small_ring]))
        self.assertTrue(_line_intersects_polygon((0.5,0.0000001),(0.5,-0.001),[ring]))
        # Ghi chú: Gán/cập nhật outer để lưu dữ liệu dùng ở bước tiếp theo.
        outer=[(0,0),(10,0),(10,10),(0,10),(0,0)]
        # Ghi chú: Gán/cập nhật hole để lưu dữ liệu dùng ở bước tiếp theo.
        hole=[(4,4),(6,4),(6,6),(4,6),(4,4)]
        self.assertFalse(_line_intersects_polygon((4,4),(6,4),[outer,hole]))
        self.assertTrue(_line_intersects_polygon((5,5),(11,5),[outer,hole]))

    # Ghi chú: Hàm test_18_real_graph_boundary_node_is_unverified_not_invalid; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_18_real_graph_boundary_node_is_unverified_not_invalid(self):
        # Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
        import json
        # Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
        from dual_gps_routing import _load_building_geometries
        # Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
        from gps_routing import GRAPH_PATH
        # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
        graph=json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        # Ghi chú: Gán/cập nhật coordinate để lưu dữ liệu dùng ở bước tiếp theo.
        coordinate=graph["nodes"]["N030"]["coordinates"]
        # Ghi chú: Gán/cập nhật validation để lưu dữ liệu dùng ở bước tiếp theo.
        validation=_connector_validation(coordinate,coordinate,_load_building_geometries())
        self.assertEqual(validation["status"],"UNVERIFIED")
        # Ghi chú: Gán/cập nhật interior để lưu dữ liệu dùng ở bước tiếp theo.
        interior=graph["nodes"]["N027"]["coordinates"]
        self.assertEqual(_connector_validation(interior,interior,_load_building_geometries())["status"],"INVALID")

    # Ghi chú: Hàm test_05_gps_outside_graph_radius; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_05_gps_outside_graph_radius(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph, coords=fixture_graph(); tr=projection_for_graph(graph)
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result=run_eval(tr.inverse((1000,1000)),graph,coords)
        self.assertEqual(result["evaluation"]["status"],"NO_VALID_ROUTE")

    # Ghi chú: Hàm test_06_no_node_candidate_in_configured_radius; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_06_no_node_candidate_in_configured_radius(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph, coords=fixture_graph(); tr=projection_for_graph(graph)
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result=run_eval(tr.inverse((10,2)),graph,coords,max_node_distance_m=1)
        self.assertEqual(result["candidates"]["nearest_node"]["code"],"no_node_candidate")

    # Ghi chú: Hàm test_07_both_methods_route_to_destination; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_07_both_methods_route_to_destination(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph, coords=fixture_graph(); result=run_eval(coords["N1"],graph,coords)
        self.assertEqual([result["candidates"][x]["status"] for x in ("nearest_edge","nearest_node")],["SUCCESS","SUCCESS"])

    # Ghi chú: Hàm test_08_only_nearest_edge_can_route; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_08_only_nearest_edge_can_route(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph()
        # Ghi chú: Gán/cập nhật gps để lưu dữ liệu dùng ở bước tiếp theo.
        gps=projection_for_graph(graph).inverse((-20,0))
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result=run_eval(gps,graph,coords,max_node_distance_m=0.5)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"SUCCESS")
        self.assertEqual(result["candidates"]["nearest_node"]["status"],"FAILED")

    # Ghi chú: Hàm test_09_only_nearest_node_can_route; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_09_only_nearest_node_can_route(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph(directed=True)
        # Ghi chú: Gán/cập nhật tr để lưu dữ liệu dùng ở bước tiếp theo.
        tr=projection_for_graph(graph)
        # Ghi chú: Gán/cập nhật graph['edges'] để lưu dữ liệu dùng ở bước tiếp theo.
        graph["edges"]=[
            {"edge_id":"E12","from":"N1","to":"N2","length_m":20.0,"coordinates":[coords['N1'],coords['N2']]},
            {"edge_id":"E14","from":"N1","to":"N4","length_m":100.0,"coordinates":[coords['N1'],tr.inverse((-30,20)),coords['N4']]}
        ]
        # Ghi chú: Gán/cập nhật gps để lưu dữ liệu dùng ở bước tiếp theo.
        gps=tr.inverse((-25,2))
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result=run_eval(gps,graph,coords)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"FAILED")
        self.assertEqual(result["candidates"]["nearest_node"]["status"],"SUCCESS")

    # Ghi chú: Hàm test_10_no_route_candidates_fail_cleanly; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_10_no_route_candidates_fail_cleanly(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph(directed=True); graph["edges"]=[]
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result=run_eval(coords["N1"],graph,coords)
        self.assertEqual(result["evaluation"]["status"],"NO_VALID_ROUTE")

    # Ghi chú: Hàm test_11_invalid_candidate_is_not_selected; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_11_invalid_candidate_is_not_selected(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph(); tr=projection_for_graph(graph); gps=tr.inverse((-20,5))
        # Ghi chú: Gán/cập nhật polygon để lưu dữ liệu dùng ở bước tiếp theo.
        polygon={"type":"Polygon","coordinates":[[tr.inverse((-16,2)),tr.inverse((-14,2)),tr.inverse((-14,3)),tr.inverse((-16,3)),tr.inverse((-16,2))]]}
        # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
        result=evaluate_gps_routes({"latitude":gps[1],"longitude":gps[0],"accuracy":3,"location_source":"browser","destination_place_id":"DEST"},
                                   graph=graph,access_rows=access_rows(coords),buildings=[("BARRIER_BUILDING",polygon)])
        # Ghi chú: Gán/cập nhật rejected để lưu dữ liệu dùng ở bước tiếp theo.
        rejected=result["candidates"]["nearest_node"].get("rejected_node_candidates",[])
        self.assertIn("N2",[item["node_id"] for item in rejected])
        self.assertNotEqual(result["evaluation"]["selected_method"],"nearest_node")

    # Ghi chú: Hàm test_12_poor_accuracy_is_rejected; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_12_poor_accuracy_is_rejected(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph()
        # Ghi chú: Mở tài nguyên trong phạm vi khối lệnh và tự giải phóng sau khi dùng.
        with self.assertRaises(Exception):
            evaluate_gps_routes({"latitude":coords["N1"][1],"longitude":coords["N1"][0],"accuracy":500,
                "location_source":"browser","destination_place_id":"DEST"},graph=graph,access_rows=access_rows(coords),buildings=[])

    # Ghi chú: Hàm test_13_graph_snapshot_is_not_mutated; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_13_graph_snapshot_is_not_mutated(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph(); before=copy.deepcopy(graph); run_eval(coords["N1"],graph,coords)
        self.assertEqual(graph,before)

    # Ghi chú: Hàm test_14_real_graph_multiple_fixtures_and_dijkstra_cost; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_14_real_graph_multiple_fixtures_and_dijkstra_cost(self):
        # Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
        import json
        # Ghi chú: Nạp thư viện/thành phần cần cho tệp này.
        from gps_routing import GRAPH_PATH, read_access_rows
        # Ghi chú: Gán/cập nhật graph để lưu dữ liệu dùng ở bước tiếp theo.
        graph=json.loads(GRAPH_PATH.read_text(encoding="utf-8")); before=copy.deepcopy(graph)
        # Ghi chú: Gán/cập nhật rows để lưu dữ liệu dùng ở bước tiếp theo.
        rows=read_access_rows(); destinations=sorted({r["place_id"] for r in rows if r["confirmed_access"].lower()=="yes"})
        self.assertTrue(destinations)
        # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
        for node in list(graph["nodes"].values())[:4]:
            # Ghi chú: Gán/cập nhật result để lưu dữ liệu dùng ở bước tiếp theo.
            result=evaluate_gps_routes({"latitude":node["coordinates"][1],"longitude":node["coordinates"][0],"accuracy":4,
                "location_source":"browser","destination_place_id":destinations[0]},graph=graph,access_rows=rows,buildings=[])
            self.assertIn(result["evaluation"]["status"],("SUCCESS","NO_VALID_ROUTE"))
            # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
            for candidate in result["candidates"].values():
                self.assertGreaterEqual(candidate["computation_time_ms"],0)
                # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                if candidate["status"]=="SUCCESS": self.assertGreaterEqual(candidate["total_distance_meters"],candidate["connector_distance_meters"])
            # Ghi chú: Gán/cập nhật candidate để lưu dữ liệu dùng ở bước tiếp theo.
            candidate=result["candidates"]["nearest_node"]
            # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
            if candidate["status"]=="SUCCESS":
                # Ghi chú: Gán/cập nhật start để lưu dữ liệu dùng ở bước tiếp theo.
                start=candidate["graph_node_id"]
                # Ghi chú: Gán/cập nhật dist để lưu dữ liệu dùng ở bước tiếp theo.
                dist={key:float("inf") for key in graph["nodes"]};dist[start]=0.0
                # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
                for _ in range(len(dist)-1):
                    # Ghi chú: Gán/cập nhật changed để lưu dữ liệu dùng ở bước tiếp theo.
                    changed=False
                    # Ghi chú: Lặp qua dữ liệu theo điều kiện của vòng lặp.
                    for edge in graph["edges"]:
                        # Ghi chú: Gán/cập nhật (u, v, w) để lưu dữ liệu dùng ở bước tiếp theo.
                        u,v,w=edge["from"],edge["to"],float(edge["length_m"])
                        # Ghi chú: Gán/cập nhật dist[v] để lưu dữ liệu dùng ở bước tiếp theo.
                        if dist[u]+w<dist[v]:dist[v]=dist[u]+w;changed=True
                        # Ghi chú: Gán/cập nhật dist[u] để lưu dữ liệu dùng ở bước tiếp theo.
                        if not graph.get("directed",False) and dist[v]+w<dist[u]:dist[u]=dist[v]+w;changed=True
                    # Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
                    if not changed:break
                # Ghi chú: Gán/cập nhật target để lưu dữ liệu dùng ở bước tiếp theo.
                target=candidate["destination_access_point_id"]
                # Ghi chú: Gán/cập nhật target_access để lưu dữ liệu dùng ở bước tiếp theo.
                target_access=next(a for a in get_places(graph,rows)[destinations[0]] if a["node"]==target)
                # Ghi chú: Gán/cập nhật expected để lưu dữ liệu dùng ở bước tiếp theo.
                expected=dist[target]+target_access["connector_m"]
                self.assertAlmostEqual(candidate["route_distance_meters"],expected,delta=0.03)
        self.assertEqual(graph,before)

    # Ghi chú: Hàm test_15_destination_changes_use_fresh_access_candidates; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_15_destination_changes_use_fresh_access_candidates(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph(); rows=access_rows(coords,"N4")+[{
            "place_id":"MID","confirmed_access":"yes","graph_node_candidate":"N3",
            "projected_boundary_lon":str(coords["N3"][0]),"projected_boundary_lat":str(coords["N3"][1])}]
        # Ghi chú: Gán/cập nhật gps để lưu dữ liệu dùng ở bước tiếp theo.
        gps=coords["N1"]
        # Ghi chú: Hàm request; xem các câu lệnh bên dưới để theo dõi cách xử lý.
        def request(destination):
            # Ghi chú: Trả kết quả hiện tại về nơi gọi.
            return evaluate_gps_routes({"latitude":gps[1],"longitude":gps[0],"accuracy":3,"location_source":"browser","destination_place_id":destination},
                                       graph=graph,access_rows=rows,buildings=[])
        # Ghi chú: Gán/cập nhật (first, second) để lưu dữ liệu dùng ở bước tiếp theo.
        first,second=request("DEST"),request("MID")
        self.assertEqual(first["selected_route"]["destination_access_point_id"],"N4")
        self.assertEqual(second["selected_route"]["destination_access_point_id"],"N3")

    # Ghi chú: Hàm test_16_successive_gps_fixtures_are_independent; xem các câu lệnh bên dưới để theo dõi cách xử lý.
    def test_16_successive_gps_fixtures_are_independent(self):
        # Ghi chú: Gán/cập nhật (graph, coords) để lưu dữ liệu dùng ở bước tiếp theo.
        graph,coords=fixture_graph(); before=copy.deepcopy(graph)
        # Ghi chú: Gán/cập nhật first để lưu dữ liệu dùng ở bước tiếp theo.
        first=run_eval(coords["N1"],graph,coords)
        # Ghi chú: Gán/cập nhật second để lưu dữ liệu dùng ở bước tiếp theo.
        second=run_eval(coords["N2"],graph,coords)
        self.assertNotEqual(first["gps"],second["gps"])
        self.assertEqual(first["evaluation"]["selected_method"],second["evaluation"]["selected_method"])
        self.assertEqual(graph,before)


# Ghi chú: Kiểm tra điều kiện để chọn nhánh xử lý.
if __name__ == "__main__":
    unittest.main()
