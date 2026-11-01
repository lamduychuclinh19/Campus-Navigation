
"""Focused dual-routing tests using temporary in-memory graph snapshots."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dual_gps_routing import (
    MAX_NODE_CONNECTOR_DISTANCE_METERS, _connector_validation, _line_intersects_polygon,
    evaluate_gps_routes,
)
from gps_routing import LocalAEQD, get_places, projection_for_graph


def fixture_graph(directed=False):
    center = [106.682, 10.760]
    project = LocalAEQD(*center)
    coords = {name: project.inverse(point) for name, point in {
        "N1":(0,0), "N2":(20,0), "N3":(40,0), "N4":(60,0)
    }.items()}
    return {"directed":directed,
            "nodes":{key:{"coordinates":value} for key,value in coords.items()},
            "edges":[
                {"edge_id":"E12","from":"N1","to":"N2","length_m":20.0,"coordinates":[coords['N1'],coords['N2']]},
                {"edge_id":"E23","from":"N2","to":"N3","length_m":20.0,"coordinates":[coords['N2'],coords['N3']]},
                {"edge_id":"E34","from":"N3","to":"N4","length_m":20.0,"coordinates":[coords['N3'],coords['N4']]}
            ]}, coords


def access_rows(coords, node="N4"):
    return [{"place_id":"DEST","confirmed_access":"yes","graph_node_candidate":node,
             "projected_boundary_lon":str(coords[node][0]),"projected_boundary_lat":str(coords[node][1])}]


def run_eval(gps, graph=None, coords=None, **kwargs):
    graph, coords = (graph,coords) if graph is not None else fixture_graph()
    buildings=kwargs.pop("buildings", [])
    return evaluate_gps_routes({"latitude":gps[1],"longitude":gps[0],"accuracy":3.0,
                                "location_source":"browser","destination_place_id":"DEST"},
                               graph=graph, access_rows=access_rows(coords), buildings=buildings, **kwargs)


class DualGpsRoutingTests(unittest.TestCase):
    def test_01_gps_exactly_on_edge(self):
        graph, coords = fixture_graph(); tr=projection_for_graph(graph)
        gps=tr.inverse((-20,0)); result=run_eval(gps,graph,coords)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"SUCCESS")
        self.assertAlmostEqual(result["candidates"]["nearest_edge"]["connector_distance_meters"],0,places=1)

    def test_02_gps_near_middle_of_two_nodes(self):
        graph, coords = fixture_graph(); tr=projection_for_graph(graph)
        result=run_eval(tr.inverse((-20,4)),graph,coords)
        self.assertEqual(result["evaluation"]["status"],"SUCCESS")
        self.assertLess(result["candidates"]["nearest_node"]["connector_distance_meters"],MAX_NODE_CONNECTOR_DISTANCE_METERS)

    def test_03_gps_sits_at_junction(self):
        graph, coords = fixture_graph(); result=run_eval(coords["N2"],graph,coords)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"SUCCESS")
        self.assertEqual(result["candidates"]["nearest_node"]["graph_node_id"],"N2")

    def test_04_connector_crosses_building_is_invalid(self):
        polygon={"type":"Polygon","coordinates":[[[106.6819,10.7599],[106.6821,10.7599],[106.6821,10.7601],[106.6819,10.7601],[106.6819,10.7599]]]}
        status=_connector_validation([106.6818,10.76],[106.6822,10.76],[("BLDG",polygon)])
        self.assertEqual(status["status"],"INVALID")

    def test_17_touching_boundary_is_allowed_but_interior_is_blocked(self):
        ring=[(0,0),(1,0),(1,1),(0,1),(0,0)]
        self.assertFalse(_line_intersects_polygon((0,0),(0,0),[ring]))
        self.assertFalse(_line_intersects_polygon((0,0),(-1,0),[ring]))
        self.assertTrue(_line_intersects_polygon((0,0),(0.5,0.5),[ring]))
        self.assertTrue(_line_intersects_polygon((0.5,0.5),(0.5,0.5),[ring]))
        small_ring=[(0,0),(0.001,0),(0.001,0.001),(0,0.001),(0,0)]
        self.assertTrue(_line_intersects_polygon((0.0005,0.00001),(0.0005,0.00001),[small_ring]))
        self.assertTrue(_line_intersects_polygon((0.5,0.0000001),(0.5,-0.001),[ring]))
        outer=[(0,0),(10,0),(10,10),(0,10),(0,0)]
        hole=[(4,4),(6,4),(6,6),(4,6),(4,4)]
        self.assertFalse(_line_intersects_polygon((4,4),(6,4),[outer,hole]))
        self.assertTrue(_line_intersects_polygon((5,5),(11,5),[outer,hole]))

    def test_18_real_graph_boundary_node_is_unverified_not_invalid(self):
        import json
        from dual_gps_routing import _load_building_geometries
        from gps_routing import GRAPH_PATH
        graph=json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        coordinate=graph["nodes"]["N030"]["coordinates"]
        validation=_connector_validation(coordinate,coordinate,_load_building_geometries())
        self.assertEqual(validation["status"],"UNVERIFIED")
        interior=graph["nodes"]["N027"]["coordinates"]
        self.assertEqual(_connector_validation(interior,interior,_load_building_geometries())["status"],"INVALID")

    def test_05_gps_outside_graph_radius(self):
        graph, coords=fixture_graph(); tr=projection_for_graph(graph)
        result=run_eval(tr.inverse((1000,1000)),graph,coords)
        self.assertEqual(result["evaluation"]["status"],"NO_VALID_ROUTE")

    def test_06_no_node_candidate_in_configured_radius(self):
        graph, coords=fixture_graph(); tr=projection_for_graph(graph)
        result=run_eval(tr.inverse((10,2)),graph,coords,max_node_distance_m=1)
        self.assertEqual(result["candidates"]["nearest_node"]["code"],"no_node_candidate")

    def test_07_both_methods_route_to_destination(self):
        graph, coords=fixture_graph(); result=run_eval(coords["N1"],graph,coords)
        self.assertEqual([result["candidates"][x]["status"] for x in ("nearest_edge","nearest_node")],["SUCCESS","SUCCESS"])

    def test_08_only_nearest_edge_can_route(self):
        graph,coords=fixture_graph()
        gps=projection_for_graph(graph).inverse((-20,0))
        result=run_eval(gps,graph,coords,max_node_distance_m=0.5)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"SUCCESS")
        self.assertEqual(result["candidates"]["nearest_node"]["status"],"FAILED")

    def test_09_only_nearest_node_can_route(self):
        graph,coords=fixture_graph(directed=True)
        tr=projection_for_graph(graph)
        graph["edges"]=[
            {"edge_id":"E12","from":"N1","to":"N2","length_m":20.0,"coordinates":[coords['N1'],coords['N2']]},
            {"edge_id":"E14","from":"N1","to":"N4","length_m":100.0,"coordinates":[coords['N1'],tr.inverse((-30,20)),coords['N4']]}
        ]
        gps=tr.inverse((-25,2))
        result=run_eval(gps,graph,coords)
        self.assertEqual(result["candidates"]["nearest_edge"]["status"],"FAILED")
        self.assertEqual(result["candidates"]["nearest_node"]["status"],"SUCCESS")

    def test_10_no_route_candidates_fail_cleanly(self):
        graph,coords=fixture_graph(directed=True); graph["edges"]=[]
        result=run_eval(coords["N1"],graph,coords)
        self.assertEqual(result["evaluation"]["status"],"NO_VALID_ROUTE")

    def test_11_invalid_candidate_is_not_selected(self):
        graph,coords=fixture_graph(); tr=projection_for_graph(graph); gps=tr.inverse((-20,5))
        polygon={"type":"Polygon","coordinates":[[tr.inverse((-16,2)),tr.inverse((-14,2)),tr.inverse((-14,3)),tr.inverse((-16,3)),tr.inverse((-16,2))]]}
        result=evaluate_gps_routes({"latitude":gps[1],"longitude":gps[0],"accuracy":3,"location_source":"browser","destination_place_id":"DEST"},
                                   graph=graph,access_rows=access_rows(coords),buildings=[("BARRIER_BUILDING",polygon)])
        rejected=result["candidates"]["nearest_node"].get("rejected_node_candidates",[])
        self.assertIn("N2",[item["node_id"] for item in rejected])
        self.assertNotEqual(result["evaluation"]["selected_method"],"nearest_node")

    def test_12_poor_accuracy_is_rejected(self):
        graph,coords=fixture_graph()
        with self.assertRaises(Exception):
            evaluate_gps_routes({"latitude":coords["N1"][1],"longitude":coords["N1"][0],"accuracy":500,
                "location_source":"browser","destination_place_id":"DEST"},graph=graph,access_rows=access_rows(coords),buildings=[])

    def test_13_graph_snapshot_is_not_mutated(self):
        graph,coords=fixture_graph(); before=copy.deepcopy(graph); run_eval(coords["N1"],graph,coords)
        self.assertEqual(graph,before)

    def test_14_real_graph_multiple_fixtures_and_dijkstra_cost(self):
        import json
        from gps_routing import GRAPH_PATH, read_access_rows
        graph=json.loads(GRAPH_PATH.read_text(encoding="utf-8")); before=copy.deepcopy(graph)
        rows=read_access_rows(); destinations=sorted({r["place_id"] for r in rows if r["confirmed_access"].lower()=="yes"})
        self.assertTrue(destinations)
        for node in list(graph["nodes"].values())[:4]:
            result=evaluate_gps_routes({"latitude":node["coordinates"][1],"longitude":node["coordinates"][0],"accuracy":4,
                "location_source":"browser","destination_place_id":destinations[0]},graph=graph,access_rows=rows,buildings=[])
            self.assertIn(result["evaluation"]["status"],("SUCCESS","NO_VALID_ROUTE"))
            for candidate in result["candidates"].values():
                self.assertGreaterEqual(candidate["computation_time_ms"],0)
                if candidate["status"]=="SUCCESS": self.assertGreaterEqual(candidate["total_distance_meters"],candidate["connector_distance_meters"])
            candidate=result["candidates"]["nearest_node"]
            if candidate["status"]=="SUCCESS":
                # Independent Bellman-Ford check of graph-only cost plus the
                # confirmed destination access connector.
                start=candidate["graph_node_id"]
                dist={key:float("inf") for key in graph["nodes"]};dist[start]=0.0
                for _ in range(len(dist)-1):
                    changed=False
                    for edge in graph["edges"]:
                        u,v,w=edge["from"],edge["to"],float(edge["length_m"])
                        if dist[u]+w<dist[v]:dist[v]=dist[u]+w;changed=True
                        if not graph.get("directed",False) and dist[v]+w<dist[u]:dist[u]=dist[v]+w;changed=True
                    if not changed:break
                target=candidate["destination_access_point_id"]
                target_access=next(a for a in get_places(graph,rows)[destinations[0]] if a["node"]==target)
                expected=dist[target]+target_access["connector_m"]
                self.assertAlmostEqual(candidate["route_distance_meters"],expected,delta=0.03)
        self.assertEqual(graph,before)

    def test_15_destination_changes_use_fresh_access_candidates(self):
        graph,coords=fixture_graph(); rows=access_rows(coords,"N4")+[{
            "place_id":"MID","confirmed_access":"yes","graph_node_candidate":"N3",
            "projected_boundary_lon":str(coords["N3"][0]),"projected_boundary_lat":str(coords["N3"][1])}]
        gps=coords["N1"]
        def request(destination):
            return evaluate_gps_routes({"latitude":gps[1],"longitude":gps[0],"accuracy":3,"location_source":"browser","destination_place_id":destination},
                                       graph=graph,access_rows=rows,buildings=[])
        first,second=request("DEST"),request("MID")
        self.assertEqual(first["selected_route"]["destination_access_point_id"],"N4")
        self.assertEqual(second["selected_route"]["destination_access_point_id"],"N3")

    def test_16_successive_gps_fixtures_are_independent(self):
        graph,coords=fixture_graph(); before=copy.deepcopy(graph)
        first=run_eval(coords["N1"],graph,coords)
        second=run_eval(coords["N2"],graph,coords)
        self.assertNotEqual(first["gps"],second["gps"])
        self.assertEqual(first["evaluation"]["selected_method"],second["evaluation"]["selected_method"])
        self.assertEqual(graph,before)


if __name__ == "__main__":
    unittest.main()
