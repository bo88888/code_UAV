from __future__ import annotations

import heapq
from collections import defaultdict
from copy import deepcopy
from typing import Dict, List, Tuple

from core.medical_models import MedicalNode, MedicalRoute, RouteSegment


class NetworkRouteAgent:
    """Selects L1-L8 corridors and produces an ordered multi-leg route."""

    def __init__(self, nodes: Dict[str, MedicalNode], routes: Dict[str, MedicalRoute]) -> None:
        self.nodes = nodes
        self.routes = routes

    def plan(self, origin_node_id: str, destination_node_id: str, cargo_type: str) -> dict:
        if origin_node_id not in self.nodes:
            raise ValueError(f"unknown origin node: {origin_node_id}")
        if destination_node_id not in self.nodes:
            raise ValueError(f"unknown destination node: {destination_node_id}")
        if origin_node_id == destination_node_id:
            raise ValueError("origin and destination must be different")

        direct = self._same_route_candidate(origin_node_id, destination_node_id)
        if direct:
            segments = direct
            selection_mode = "fixed_medical_corridor"
        else:
            segments = self._dijkstra(origin_node_id, destination_node_id)
            selection_mode = "multi_route_network_shortest_path"

        route_ids = []
        for segment in segments:
            if segment.route_id not in route_ids:
                route_ids.append(segment.route_id)
        node_path = [origin_node_id] + [item.to_node for item in segments]
        total_distance = round(sum(item.distance_km for item in segments), 3)
        relay_nodes = [
            item.to_node
            for item in segments[:-1]
            if self.nodes[item.to_node].node_type == "relay" or item.relay_required
        ]
        incompatible_routes = []
        for route_id in route_ids:
            route = self.routes[route_id]
            if cargo_type not in route.cargo_types:
                incompatible_routes.append(route_id)

        return {
            "selection_mode": selection_mode,
            "origin_node_id": origin_node_id,
            "destination_node_id": destination_node_id,
            "node_path": node_path,
            "route_ids": route_ids,
            "segments": segments,
            "relay_nodes": relay_nodes,
            "total_distance_km": total_distance,
            "cargo_policy_mismatch_routes": incompatible_routes,
            "network_explanation": self._explain(route_ids, relay_nodes, total_distance),
        }

    def _same_route_candidate(self, origin: str, destination: str) -> List[RouteSegment]:
        candidates: List[Tuple[float, List[RouteSegment]]] = []
        for route in self.routes.values():
            forward = self._route_slice(route, origin, destination)
            if forward:
                candidates.append((sum(item.distance_km for item in forward), forward))
            backward = self._route_slice(route, destination, origin)
            if backward:
                reversed_segments = [self._reverse_segment(item) for item in reversed(backward)]
                candidates.append((sum(item.distance_km for item in reversed_segments), reversed_segments))
        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    @staticmethod
    def _route_slice(route: MedicalRoute, origin: str, destination: str) -> List[RouteSegment]:
        nodes = []
        if route.segments:
            nodes.append(route.segments[0].from_node)
            nodes.extend(item.to_node for item in route.segments)
        if origin not in nodes or destination not in nodes:
            return []
        start = nodes.index(origin)
        end = nodes.index(destination)
        if start >= end:
            return []
        return [deepcopy(item) for item in route.segments[start:end]]

    def _dijkstra(self, origin: str, destination: str) -> List[RouteSegment]:
        graph: Dict[str, List[Tuple[str, float, RouteSegment]]] = defaultdict(list)
        for route in self.routes.values():
            for segment in route.segments:
                graph[segment.from_node].append((segment.to_node, segment.distance_km, segment))
                graph[segment.to_node].append(
                    (segment.from_node, segment.distance_km, self._reverse_segment(segment))
                )

        queue = [(0.0, origin)]
        distances = {origin: 0.0}
        previous: Dict[str, Tuple[str, RouteSegment]] = {}
        while queue:
            cost, node = heapq.heappop(queue)
            if node == destination:
                break
            if cost > distances.get(node, float("inf")):
                continue
            for next_node, edge_cost, segment in graph.get(node, []):
                new_cost = cost + edge_cost
                if new_cost < distances.get(next_node, float("inf")):
                    distances[next_node] = new_cost
                    previous[next_node] = (node, segment)
                    heapq.heappush(queue, (new_cost, next_node))

        if destination not in previous:
            raise ValueError(f"no medical route between {origin} and {destination}")
        result = []
        current = destination
        while current != origin:
            parent, segment = previous[current]
            result.append(deepcopy(segment))
            current = parent
        result.reverse()
        return result

    @staticmethod
    def _reverse_segment(segment: RouteSegment) -> RouteSegment:
        return RouteSegment(
            segment_id=f"{segment.segment_id}-REV",
            from_node=segment.to_node,
            to_node=segment.from_node,
            distance_km=segment.distance_km,
            max_altitude_m=segment.max_altitude_m,
            relay_required=segment.relay_required,
            route_id=segment.route_id,
            route_name=segment.route_name,
            route_type=segment.route_type,
            cruise_altitude_m=segment.cruise_altitude_m,
            corridor_width_m=segment.corridor_width_m,
            airspace_rule=segment.airspace_rule,
        )

    def _explain(self, route_ids: List[str], relay_nodes: List[str], distance: float) -> str:
        route_text = "、".join(route_ids)
        if relay_nodes:
            relay_text = "、".join(self.nodes[item].name for item in relay_nodes)
            return f"选择医疗航线 {route_text}，总里程 {distance}km，经 {relay_text} 分段换电或备降保障。"
        return f"选择医疗航线 {route_text}，总里程 {distance}km，任务可在固定受控走廊内直达。"
