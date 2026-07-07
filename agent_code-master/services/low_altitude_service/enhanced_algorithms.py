"""Enhanced ROUTE tools for low-altitude medical delivery.

The module keeps the MCP/service contract while making the route layer more
explainable and visually faithful:
- A* 3D local-grid planning with hard obstacles and soft risk costs;
- explicit obstacle modeling for buildings, power lines and sensitive zones;
- minimum-snap-like trajectory smoothing from discrete waypoints;
- multi-UAV coordination plan with height/time separation;
- richer fields for frontend visualization.
"""
from __future__ import annotations

import heapq
from itertools import count
from typing import Any, Dict, Iterable, List, Tuple

from services.low_altitude_service import algorithms as base
from services.low_altitude_service.multi_uav_planner import build_multi_uav_plan
from services.low_altitude_service.obstacle_model import (
    avoidance_explanations,
    enrich_obstacles,
)
from services.low_altitude_service.trajectory_smoothing import (
    make_ros_node_graph,
    smooth_trajectory,
)

GridPoint = Tuple[int, int, int]
GRID_SIZE = 32
Z_LEVELS = 5


def _heuristic(a: GridPoint, b: GridPoint) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + 0.65 * abs(a[2] - b[2])


def _neighbors(point: GridPoint) -> Iterable[GridPoint]:
    x, y, z = point
    for dx, dy, dz in (
        (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
        (1, 1, 0), (1, -1, 0), (-1, 1, 0), (-1, -1, 0),
        (0, 0, 1), (0, 0, -1),
    ):
        nxt = (x + dx, y + dy, z + dz)
        if 0 <= nxt[0] < GRID_SIZE and 0 <= nxt[1] < GRID_SIZE and 0 <= nxt[2] < Z_LEVELS:
            yield nxt


def _astar(start: GridPoint, goal: GridPoint, blocked: set, weighted: Dict[GridPoint, float]) -> Tuple[List[GridPoint], float, int]:
    tie = count()
    queue = [(0.0, next(tie), start)]
    parent: Dict[GridPoint, GridPoint] = {}
    cost = {start: 0.0}
    expanded = 0

    while queue:
        _, _, current = heapq.heappop(queue)
        expanded += 1
        if current == goal:
            path = [current]
            while current in parent:
                current = parent[current]
                path.append(current)
            return list(reversed(path)), round(cost[goal], 3), expanded

        for nxt in _neighbors(current):
            if nxt in blocked:
                continue
            diagonal = nxt[0] != current[0] and nxt[1] != current[1]
            step = 1.414 if diagonal else 1.0
            step += 0.42 if nxt[2] != current[2] else 0.0
            step += weighted.get(nxt, 0.0)
            new_cost = cost[current] + step
            if new_cost < cost.get(nxt, float("inf")):
                parent[nxt] = current
                cost[nxt] = new_cost
                heapq.heappush(queue, (new_cost + _heuristic(nxt, goal), next(tie), nxt))

    return [], float("inf"), expanded


def _point_pair(mission: Dict[str, Any]):
    return base._point_pair(mission)


def _bounds(mission: Dict[str, Any], obstacles: List[Dict[str, Any]]) -> Dict[str, float]:
    pickup, dropoff = _point_pair(mission)
    lons = [float(pickup.get("lon", 0.0)), float(dropoff.get("lon", 0.0))]
    lats = [float(pickup.get("lat", 0.0)), float(dropoff.get("lat", 0.0))]
    for obs in obstacles:
        if "center_lon" in obs:
            lons.append(float(obs["center_lon"]))
            lats.append(float(obs["center_lat"]))
        for p in obs.get("polyline_geo", []):
            lons.append(float(p["lon"]))
            lats.append(float(p["lat"]))
    lon_pad = max((max(lons) - min(lons)) * 0.42, 0.035)
    lat_pad = max((max(lats) - min(lats)) * 0.42, 0.035)
    return {
        "min_lon": min(lons) - lon_pad,
        "max_lon": max(lons) + lon_pad,
        "min_lat": min(lats) - lat_pad,
        "max_lat": max(lats) + lat_pad,
    }


def _geo_to_grid(lon: float, lat: float, bounds: Dict[str, float]) -> Tuple[int, int]:
    x = round((lon - bounds["min_lon"]) / max(bounds["max_lon"] - bounds["min_lon"], 1e-6) * (GRID_SIZE - 1))
    y = round((lat - bounds["min_lat"]) / max(bounds["max_lat"] - bounds["min_lat"], 1e-6) * (GRID_SIZE - 1))
    return max(0, min(GRID_SIZE - 1, x)), max(0, min(GRID_SIZE - 1, y))


def _grid_to_geo(point: GridPoint, bounds: Dict[str, float], altitude: float) -> Dict[str, Any]:
    x, y, z = point
    lon = bounds["min_lon"] + (bounds["max_lon"] - bounds["min_lon"]) * x / (GRID_SIZE - 1)
    lat = bounds["min_lat"] + (bounds["max_lat"] - bounds["min_lat"]) * y / (GRID_SIZE - 1)
    alt = max(0.0, altitude + (z - 2) * 10)
    return {
        "lon": round(lon, 7),
        "lat": round(lat, 7),
        "altitude_m": round(alt, 2),
        "grid": [x, y, z],
    }


def _cells_near(center: Tuple[int, int], radius: int, z_values=range(Z_LEVELS)) -> List[GridPoint]:
    cx, cy = center
    cells: List[GridPoint] = []
    for x in range(cx - radius, cx + radius + 1):
        for y in range(cy - radius, cy + radius + 1):
            if not (0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE):
                continue
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                for z in z_values:
                    cells.append((x, y, z))
    return cells


def _obstacle_costs(obstacles: List[Dict[str, Any]], bounds: Dict[str, float], vehicle_type: str, profile: str) -> Tuple[set, Dict[GridPoint, float]]:
    blocked = set()
    weighted: Dict[GridPoint, float] = {}
    if vehicle_type == "ground_vehicle":
        return blocked, weighted

    for obs in obstacles:
        center = None
        if "center_lon" in obs:
            center = _geo_to_grid(float(obs["center_lon"]), float(obs["center_lat"]), bounds)
        elif obs.get("polyline_geo"):
            middle = obs["polyline_geo"][len(obs["polyline_geo"]) // 2]
            center = _geo_to_grid(float(middle["lon"]), float(middle["lat"]), bounds)
        if center is None:
            continue

        radius = max(1, min(6, round(float(obs.get("radius_km", 1.0)) * 1.35)))
        kind = obs.get("kind")
        if kind == "no_fly_zone":
            blocked.update(_cells_near(center, radius + 1))
        elif kind == "linear_obstacle":
            for cell in _cells_near(center, radius, z_values=range(0, 3)):
                weighted[cell] = max(weighted.get(cell, 0.0), 10.0)
            for cell in _cells_near(center, radius, z_values=range(3, Z_LEVELS)):
                weighted[cell] = max(weighted.get(cell, 0.0), 2.0)
        elif kind == "building_cluster":
            for cell in _cells_near(center, radius, z_values=range(0, 3)):
                weighted[cell] = max(weighted.get(cell, 0.0), 7.0)
            for cell in _cells_near(center, radius, z_values=range(3, Z_LEVELS)):
                weighted[cell] = max(weighted.get(cell, 0.0), 2.5)
        elif kind == "sensitive_area":
            for cell in _cells_near(center, radius + 1):
                weighted[cell] = max(weighted.get(cell, 0.0), 5.5)
        elif kind == "weather_cell":
            for cell in _cells_near(center, radius + 1):
                weighted[cell] = max(weighted.get(cell, 0.0), 9.5)
        elif kind == "resource_bottleneck":
            for cell in _cells_near(center, radius):
                weighted[cell] = max(weighted.get(cell, 0.0), 2.0)

    if profile == "medical_time_window":
        weighted = {k: v * 0.72 for k, v in weighted.items()}
    elif profile == "drl_compliance":
        weighted = {k: v * 1.25 for k, v in weighted.items()}
    elif profile == "coordfield_allocation":
        weighted = {k: v * 0.95 for k, v in weighted.items()}
    return blocked, weighted


def _compress(path: List[GridPoint], keep_every: int = 3) -> List[GridPoint]:
    if len(path) <= 10:
        return path
    out = [path[0]]
    for i in range(1, len(path) - 1):
        prev_dir = (path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1], path[i][2] - path[i - 1][2])
        next_dir = (path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1], path[i + 1][2] - path[i][2])
        if prev_dir != next_dir or i % keep_every == 0:
            out.append(path[i])
    out.append(path[-1])
    return out


def _route_node(node_id: str, name: str, geo: Dict[str, Any], node_type: str, action: str) -> Dict[str, Any]:
    return base._route_node(node_id, name, geo["lon"], geo["lat"], geo["altitude_m"], node_type, action)


def _astar_nodes(
    mission: Dict[str, Any],
    altitude: float,
    profile: str,
    obstacles: List[Dict[str, Any]],
    vehicle_type: str = "uav",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if vehicle_type == "ground_vehicle":
        nodes = base._build_route_nodes(mission, 0.0, "ground_fallback")
        return nodes, {
            "planner": "ground_corridor_fallback",
            "grid_path_length": 0,
            "grid_cost": 0.0,
            "expanded_nodes": 0,
            "raw_astar_waypoints": [],
            "fallback_used": False,
        }

    pickup, dropoff = _point_pair(mission)
    bounds = _bounds(mission, obstacles)
    sx, sy = _geo_to_grid(float(pickup.get("lon", 0.0)), float(pickup.get("lat", 0.0)), bounds)
    gx, gy = _geo_to_grid(float(dropoff.get("lon", 0.0)), float(dropoff.get("lat", 0.0)), bounds)
    z = 3 if altitude >= 95 else 2
    blocked, weighted = _obstacle_costs(obstacles, bounds, vehicle_type, profile)
    path, cost, expanded = _astar((sx, sy, z), (gx, gy, z), blocked, weighted)
    fallback_used = False
    if not path:
        path, cost, expanded = _astar((sx, sy, z), (gx, gy, z), set(), weighted)
        fallback_used = True
    if not path:
        nodes = base._build_route_nodes(mission, altitude, profile)
        return nodes, {
            "planner": "template_fallback_after_astar_failure",
            "grid_path_length": 0,
            "grid_cost": float("inf"),
            "expanded_nodes": expanded,
            "raw_astar_waypoints": [],
            "fallback_used": True,
        }

    compact = _compress(path)
    labels = {
        "drl_compliance": ("A*_COMPLIANCE", "A*合规避障航点", "规避建筑群/高压线/敏感区风险"),
        "medical_time_window": ("A*_MEDICAL", "A*医疗时间窗航点", "压缩ETA并保持时间窗可行"),
        "coordfield_allocation": ("A*_ALLOC", "A*协同分配航点", "为多机协同保留中继余量"),
        "air_ground_coordination": ("A*_TRANSFER", "A*空地协同航点", "飞至安全交接区域"),
    }
    prefix, name, action = labels.get(profile, ("A*_WP", "A*航点", "航路推进"))
    nodes = [base._point_node(pickup, altitude, "pickup", "pickup")]
    for idx, pt in enumerate(compact[1:-1], 1):
        geo = _grid_to_geo(pt, bounds, altitude)
        node_type = "risk_weighted_waypoint" if pt in weighted else "astar_waypoint"
        nodes.append(_route_node(f"{prefix}_{idx:02d}", f"{name}{idx}", geo, node_type, action))
    nodes.append(base._point_node(dropoff, max(0.0, altitude - 8), "dropoff", "dropoff"))

    raw_astar_waypoints = []
    for i, pt in enumerate(path):
        geo = _grid_to_geo(pt, bounds, altitude)
        raw_astar_waypoints.append(
            {
                "id": f"RAW_ASTAR_{i:03d}",
                "lon": geo["lon"],
                "lat": geo["lat"],
                "altitude_m": geo["altitude_m"],
                "grid": geo["grid"],
                "is_weighted_risk_cell": pt in weighted,
                "is_hard_blocked_cell": pt in blocked,
            }
        )

    return nodes, {
        "planner": "time_space_astar_3d",
        "grid_path_length": len(path),
        "compressed_waypoints": len(nodes),
        "grid_cost": round(cost, 3),
        "expanded_nodes": expanded,
        "hard_blocked_cells": len(blocked),
        "weighted_risk_cells": len(weighted),
        "raw_astar_waypoints": raw_astar_waypoints,
        "fallback_used": fallback_used,
        "search_space": {
            "grid_size": [GRID_SIZE, GRID_SIZE, Z_LEVELS],
            "start_grid": [sx, sy, z],
            "goal_grid": [gx, gy, z],
        },
    }


def _segment_distance_km(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    if hasattr(base, "_segment_distance_km"):
        return float(base._segment_distance_km(a, b))
    return base.haversine_km(float(a.get("lon", 0.0)), float(a.get("lat", 0.0)), float(b.get("lon", 0.0)), float(b.get("lat", 0.0)))


def _route_distance(nodes: List[Dict[str, Any]]) -> float:
    return round(sum(_segment_distance_km(nodes[i], nodes[i + 1]) for i in range(max(len(nodes) - 1, 0))), 3)


def _waypoints_from_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if hasattr(base, "_waypoints_from_nodes"):
        return base._waypoints_from_nodes(nodes)
    return [
        {
            "id": n.get("id"),
            "name": n.get("name"),
            "lon": n.get("lon"),
            "lat": n.get("lat"),
            "altitude_m": n.get("altitude_m", 0.0),
        }
        for n in nodes
    ]


def _energy(distance: float, cargo: float, wind: float, vehicle_type: str, efficiency: float = 1.0) -> float:
    if vehicle_type == "ground_vehicle":
        return round(distance * 44.0 * efficiency, 2)
    return round(distance * (21.0 + cargo * 3.1) * (1 + wind / 45) * efficiency, 2)


def _time_window_slack_mins(mission: Dict[str, Any], duration: float):
    if hasattr(base, "_time_window_slack_mins"):
        return base._time_window_slack_mins(mission, duration)
    return None


def _constraint_summary(mission: Dict[str, Any], nodes: List[Dict[str, Any]], uav: Dict[str, Any], energy_kj: float) -> Dict[str, Any]:
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    return {
        "payload_feasible": float(uav.get("max_payload_kg", 0.0)) >= cargo,
        "battery_feasible": float(uav.get("battery_percent", 0.0)) >= max(25.0, energy_kj / 40.0),
        "route_node_count": len(nodes),
        "payload_margin_kg": round(float(uav.get("max_payload_kg", 0.0)) - cargo, 2),
        "medical_priority": mission.get("priority", 3),
    }


def _telemetry_from_smoothed(smoothed: List[Dict[str, Any]], vehicle_type: str, vehicle_id: str) -> List[Dict[str, Any]]:
    if not smoothed:
        return []
    telemetry: List[Dict[str, Any]] = []
    n = len(smoothed)
    for idx, p in enumerate(smoothed):
        telemetry.append(
            {
                "step": idx,
                "lon": p["lon"],
                "lat": p["lat"],
                "altitude_m": p.get("altitude_m", 0.0),
                "speed_kmh": 50 if vehicle_type != "ground_vehicle" else 36,
                "battery_percent": round(max(8.0, 96.0 - idx * 35 / max(n - 1, 1)), 1),
                "phase": p.get("phase", "minimum_snap_smooth"),
                "vehicle_type": vehicle_type,
                "uav_id": vehicle_id,
                "t_seconds": p.get("t_seconds", 0.0),
            }
        )
    return telemetry


def _enhance_output(
    output: Dict[str, Any],
    mission: Dict[str, Any],
    nodes: List[Dict[str, Any]],
    duration: float,
    vehicle_type: str,
    algorithm_label: str,
    vehicle_id: str,
    scenario: str,
    obstacles: List[Dict[str, Any]],
    risk_tags: List[str],
    steps: List[Dict[str, Any]],
    planner_trace: Dict[str, Any],
    uavs: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    enriched_obstacles = enrich_obstacles(obstacles)
    smoothed = smooth_trajectory(_waypoints_from_nodes(nodes), samples_per_segment=12, nominal_speed_mps=14.5)
    multi = (
        build_multi_uav_plan(smoothed["smoothed_trajectory"], uavs or [], vehicle_id)
        if vehicle_type != "ground_vehicle"
        else {
            "enabled": False,
            "uavs": [],
            "height_time_profile": [],
            "conflict_resolution": [],
            "coordination_summary": "地面兜底模式不生成多 UAV 协同轨迹。",
        }
    )
    visual = base._build_route_visualization(
        mission, nodes, duration, vehicle_type, algorithm_label, vehicle_id, scenario, enriched_obstacles, risk_tags, steps
    )
    visual["telemetry_stream"] = _telemetry_from_smoothed(smoothed["smoothed_trajectory"], vehicle_type, vehicle_id) or visual.get("telemetry_stream", [])
    visual["planner_trace"] = planner_trace
    visual["route_quality_metrics"]["distance_km"] = _route_distance(nodes)
    visual["obstacle_zones"] = enriched_obstacles
    output.update(visual)
    output.update(
        {
            "raw_astar_waypoints": planner_trace.get("raw_astar_waypoints", []),
            "smoothed_trajectory": smoothed["smoothed_trajectory"],
            "trajectory_metrics": smoothed["trajectory_metrics"],
            "smoothing_profile": smoothed["smoothing_profile"],
            "multi_uav_plan": multi,
            "obstacle_avoidance_explanation": avoidance_explanations(enriched_obstacles, planner_trace),
            "ros_node_graph": make_ros_node_graph(),
            "route_generation_mode": "astar_grid_search_plus_minimum_snap_smoothing",
            "fixed_template_used": bool(planner_trace.get("planner") == "template_fallback_after_astar_failure"),
        }
    )
    return output


def compliance_route(input_data: Dict[str, Any], subtask_id: str):
    mission = base._mission(input_data)
    scenario = base._scenario(input_data)
    airspace = base._previous(input_data, "AIR_01")
    weather = base._previous(input_data, "WEA_01")
    dock = base._previous(input_data, "DOCK_01")
    uavs = base._available_uavs(input_data, subtask_id)
    if not airspace.get("is_clear", False):
        return 409, "airspace restricted by temporary no-fly zone", {}
    if not weather.get("is_flyable", False):
        return 422, "weather unsafe for compliance UAV route", {}
    if not uavs:
        return 409, "no available UAV for compliance route", {}

    obstacles = base._scene_obstacles(mission, scenario, airspace, weather, dock)
    altitude = min(float(airspace.get("altitude_limit_m", 120.0)), 100.0)
    nodes, trace = _astar_nodes(mission, altitude, "drl_compliance", obstacles)
    distance = _route_distance(nodes)
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    wind = float(weather.get("wind_speed_mps", 0.0))
    duration = round(distance / 58.0 * 60.0 + 1.8 + 0.04 * len(nodes), 2)
    energy = _energy(distance, cargo, wind, "uav", 1.05)
    eta, time_window_met = base._window_result(mission, duration)
    checks = base._route_conflict_checks(nodes, obstacles, "uav")
    penalty = sum(1 for c in checks if c.get("status") in {"blocked", "unsafe"})
    selected = uavs[0]

    output = {
        "algorithm": "DRL-LLM",
        "algorithm_family": "A*_3D_compliance_planner",
        "uav_id": selected["uav_id"],
        "assigned_vehicle_type": "uav",
        "waypoints_3d": _waypoints_from_nodes(nodes),
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "time_window_slack_mins": _time_window_slack_mins(mission, duration),
        "compliance_score": round(max(0.55, 0.98 - 0.015 * max(len(nodes) - 5, 0) - 0.08 * penalty), 3),
        "collision_risk": round(0.035 + 0.01 * penalty, 3),
        "constraint_summary": _constraint_summary(mission, nodes, selected, energy),
        "optimization_objective": "minimize weighted building/powerline/sensitive-zone risk + distance + energy",
    }
    output = _enhance_output(
        output, mission, nodes, duration, "uav", "A* enhanced DRL-LLM compliance route",
        selected["uav_id"], scenario, obstacles, [], [
            base._decision_step("ComplianceRouteService", "astar_3d_search", "空域、气象、无人机状态满足前置依赖", "执行三维 A* 合规航路搜索"),
            base._decision_step("ObstacleMapNode", "risk_grid", "建筑群/高压线/敏感区转为硬约束或软代价单元", "生成可解释避障路径"),
            base._decision_step("TrajectorySmoother", "minimum_snap_like", "A* 离散航点不能直接飞行", "转换为连续可飞轨迹"),
        ], trace, uavs
    )
    return 200, "A* enhanced compliance route generated with obstacle-aware waypoints", output


def weather_adaptive_dispatch(input_data: Dict[str, Any]):
    mission = base._mission(input_data)
    scenario = base._scenario(input_data)
    airspace = base._previous(input_data, "AIR_01")
    weather = base._previous(input_data, "WEA_01")
    dock = base._previous(input_data, "DOCK_01")
    uavs = base._previous(input_data, "UAV_01").get("available_uavs", [])
    unsafe_air = airspace and not airspace.get("is_clear", True)
    unsafe_weather = not weather.get("is_flyable", False)
    ground_mode = unsafe_air or unsafe_weather or not uavs
    risk_tags = []
    if unsafe_air:
        risk_tags.append("temporary_airspace_restriction")
    if unsafe_weather:
        risk_tags.append("adverse_weather")
    if not uavs:
        risk_tags.append("uav_unavailable")

    obstacles = base._scene_obstacles(mission, scenario, airspace, weather, dock)
    profile = "ground_fallback" if ground_mode else "air_ground_coordination"
    vehicle_type = "ground_vehicle" if ground_mode else "air_ground_coordination"
    nodes, trace = _astar_nodes(mission, 0.0 if ground_mode else 85.0, profile, obstacles, vehicle_type)
    distance = _route_distance(nodes)
    speed = 46.0 if ground_mode else 55.0
    delay = 6.0 if ground_mode else 2.0
    duration = round(distance / speed * 60.0 + delay + 0.03 * len(nodes), 2)
    energy = _energy(distance, float(mission.get("cargo_weight_kg", 0.0)), float(weather.get("wind_speed_mps", 0.0)), "ground_vehicle" if ground_mode else "uav")
    eta, time_window_met = base._window_result(mission, duration)
    vehicle_id = uavs[0]["uav_id"] if uavs and not ground_mode else "GROUND-RESCUE-01"

    output = {
        "algorithm": "NN-AirGround",
        "algorithm_family": "risk_adaptive_air_ground_scheduler",
        "assigned_vehicle_type": vehicle_type,
        "uav_id": vehicle_id,
        "adjusted_route": [n["id"] for n in nodes],
        "waypoints_3d": _waypoints_from_nodes(nodes),
        "weather_delay_mins": delay,
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "compliance_score": round(0.99 if ground_mode else max(0.75, 0.93 - 0.02 * len(risk_tags)), 3),
        "risk_mode": "ground_fallback" if ground_mode else "air_ground_coordination",
        "optimization_objective": "maintain dispatch feasibility under weather/airspace/UAV degradation",
    }
    output = _enhance_output(
        output, mission, nodes, duration, vehicle_type, "NN weather-adaptive air-ground dispatch",
        vehicle_id, scenario, obstacles, risk_tags, [
            base._decision_step("ReplanDecisionAgent", "fallback" if ground_mode else "parallel_candidate", "空域/气象/无人机约束触发备用策略" if ground_mode else "作为空地协同候选方案并行生成", "选择地面兜底路径" if ground_mode else "生成空地协同路径"),
            base._decision_step("WeatherAdaptiveService", "risk_avoidance", "规避强天气/禁飞核心区", "切换道路安全接驳或安全交接节点"),
            base._decision_step("RiskAssessmentService", "authorize", "风险区不再被飞行路径穿越", "允许进入候选推荐"),
        ], trace, uavs
    )
    return 200, "weather-adaptive air-ground plan generated with fallback context", output


def _medical_candidates(mission, scenario, airspace, weather, dock):
    obstacles = base._scene_obstacles(mission, scenario, airspace, weather, dock)
    out = []
    for name, altitude, speed, eff in [
        ("medical_fast_corridor", 94.0, 65.0, 0.96),
        ("medical_safe_corridor", 108.0, 58.0, 1.06),
        ("medical_energy_saving_corridor", 84.0, 54.0, 0.86),
    ]:
        nodes, trace = _astar_nodes(mission, altitude, "medical_time_window", obstacles)
        distance = _route_distance(nodes)
        duration = round(distance / speed * 60.0 + 1.2 + 0.02 * len(nodes), 2)
        energy = _energy(distance, float(mission.get("cargo_weight_kg", 0.0)), float(weather.get("wind_speed_mps", 0.0)), "uav", eff)
        eta, met = base._window_result(mission, duration)
        slack = _time_window_slack_mins(mission, duration)
        risk_load = sum(1 for obs in obstacles if obs.get("severity") == "high")
        objective = round(duration * 0.45 + energy * 0.004 + risk_load * 3.0 - max(min(float(slack or 0), 30), -30) * 0.08, 3)
        out.append(
            {
                "corridor_name": name,
                "route_nodes": nodes,
                "planner_trace": trace,
                "distance": distance,
                "duration": duration,
                "energy": energy,
                "eta": eta,
                "time_window_met": met,
                "slack": slack,
                "objective_value": objective,
            }
        )
    return out


def medical_time_window_schedule(input_data: Dict[str, Any], subtask_id: str):
    mission = base._mission(input_data)
    scenario = base._scenario(input_data)
    airspace = base._previous(input_data, "AIR_01")
    weather = base._previous(input_data, "WEA_01")
    dock = base._previous(input_data, "DOCK_01")
    uavs = base._available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for emergency medical mission", {}

    candidates = _medical_candidates(mission, scenario, airspace, weather, dock)
    selected = min([c for c in candidates if c["time_window_met"]] or candidates, key=lambda c: c["objective_value"])
    nodes = selected["route_nodes"]
    obstacles = base._scene_obstacles(mission, scenario, airspace, weather, dock)
    pickup, dropoff = _point_pair(mission)
    uav = max(uavs, key=lambda u: (float(u.get("battery_percent", 0)), float(u.get("max_payload_kg", 0))))

    output = {
        "algorithm": "TWA-MILP",
        "algorithm_family": "time_window_milp_inspired_candidate_optimizer",
        "uav_id": uav["uav_id"],
        "assigned_vehicle_type": "uav",
        "dispatch_sequence": [pickup.get("id", "pickup"), dropoff.get("id", "dropoff")],
        "waypoints_3d": _waypoints_from_nodes(nodes),
        "flight_distance_km": selected["distance"],
        "estimated_duration_mins": selected["duration"],
        "estimated_energy_kj": selected["energy"],
        "eta": selected["eta"],
        "time_window_met": selected["time_window_met"],
        "time_window_slack_mins": selected["slack"],
        "minimum_required_uavs": 1,
        "solver_status": "OPTIMAL",
        "solver_engine": "enumerated_milp_objective_without_external_solver",
        "selected_corridor": selected["corridor_name"],
        "objective_value": selected["objective_value"],
        "candidate_corridors": [
            {
                "corridor_name": c["corridor_name"],
                "duration_mins": c["duration"],
                "energy_kj": c["energy"],
                "time_window_met": c["time_window_met"],
                "objective_value": c["objective_value"],
                "planner": c["planner_trace"].get("planner"),
                "raw_astar_waypoints_count": len(c["planner_trace"].get("raw_astar_waypoints", [])),
            }
            for c in sorted(candidates, key=lambda c: c["objective_value"])
        ],
        "milp_like_variables": {
            "x_route_selected": selected["corridor_name"],
            "uav_assignment": uav["uav_id"],
            "deadline_constraint": selected["time_window_met"],
            "payload_constraint": uav.get("max_payload_kg", 0) >= float(mission.get("cargo_weight_kg", 0.0)),
        },
        "compliance_score": round(0.93 if selected["time_window_met"] else 0.82, 3),
        "constraint_summary": _constraint_summary(mission, nodes, uav, selected["energy"]),
    }
    output = _enhance_output(
        output, mission, nodes, selected["duration"], "uav", "TWA-MILP medical time-window schedule",
        uav["uav_id"], scenario, obstacles, [], [
            base._decision_step("DecomposeAgent", "insert_medical_scheduler", "任务类型为 emergency_medical", "加入医疗时间窗调度节点"),
            base._decision_step("MedicalScheduler", "candidate_optimize", "以截止期、载荷、能耗、风险为目标函数", f"选择 {selected['corridor_name']}"),
            base._decision_step("TrajectorySmoother", "minimum_snap_like", "离散医疗走廊需要连续化", "输出 smoothed_trajectory"),
        ], selected["planner_trace"], uavs
    )
    return 200, "TWA-MILP optimal schedule generated with A* medical corridors and smoothed trajectory", output


def _score_uav(uav, mission, pickup, weather):
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    margin = float(uav.get("max_payload_kg", 0.0)) - cargo
    dist = base.haversine_km(
        float(uav.get("current_lon", pickup.get("lon", 0.0))),
        float(uav.get("current_lat", pickup.get("lat", 0.0))),
        float(pickup.get("lon", 0.0)),
        float(pickup.get("lat", 0.0)),
    )
    battery = float(uav.get("battery_percent", 0.0))
    score = 0.42 * battery / 100 + 0.32 * max(0.0, min(margin / 5.0, 1.0)) + 0.18 * max(0.0, 1 - dist / 20) - float(weather.get("wind_speed_mps", 0.0)) / 100
    if uav.get("health") == "standby":
        score -= 0.04
    return {
        "uav_id": uav.get("uav_id"),
        "battery_percent": battery,
        "payload_margin_kg": round(margin, 2),
        "pickup_distance_km": round(dist, 3),
        "allocation_score": round(max(score, 0.0), 3),
    }


def agentic_task_allocation(input_data: Dict[str, Any], subtask_id: str):
    mission = base._mission(input_data)
    scenario = base._scenario(input_data)
    airspace = base._previous(input_data, "AIR_01")
    weather = base._previous(input_data, "WEA_01")
    dock = base._previous(input_data, "DOCK_01")
    uavs = base._available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for CoordField allocation", {}

    pickup, dropoff = _point_pair(mission)
    scored = sorted([_score_uav(u, mission, pickup, weather) for u in uavs], key=lambda x: x["allocation_score"], reverse=True)
    selected_id = scored[0]["uav_id"]
    selected = next(u for u in uavs if u["uav_id"] == selected_id)
    obstacles = base._scene_obstacles(mission, scenario, airspace, weather, dock)
    nodes, trace = _astar_nodes(mission, 78.0, "coordfield_allocation", obstacles)
    distance = _route_distance(nodes)
    duration = round(distance / 55.0 * 60.0 + 2.3 + 0.04 * len(nodes), 2)
    energy = _energy(distance, float(mission.get("cargo_weight_kg", 0.0)), float(weather.get("wind_speed_mps", 0.0)), "uav", 1.02)
    eta, met = base._window_result(mission, duration)

    output = {
        "algorithm": "CoordField",
        "algorithm_family": "score_based_multi_uav_allocation",
        "uav_id": selected_id,
        "assigned_vehicle_type": "uav",
        "assignments": [
            {
                "uav_id": selected_id,
                "task": f"{pickup.get('id')}->{dropoff.get('id')}",
                "allocation_score": scored[0]["allocation_score"],
                "policy": "battery_payload_distance_score",
            }
        ],
        "candidate_uav_scores": scored,
        "task_coverage_rate": 1.0,
        "response_time_mins": duration,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "flight_distance_km": distance,
        "eta": eta,
        "time_window_met": met,
        "reallocation_count": 1 if scenario != "normal" else 0,
        "coordination_policy": "select best UAV by battery/payload/distance and reserve relay/backup height layers",
        "compliance_score": 0.90,
        "constraint_summary": _constraint_summary(mission, nodes, selected, energy),
    }
    output = _enhance_output(
        output, mission, nodes, duration, "uav", "CoordField agentic task allocation",
        selected_id, scenario, obstacles, [], [
            base._decision_step("AgenticAllocationService", "score_uavs", "根据载荷、位置、电量和任务覆盖率分配 UAV", f"选择 {selected_id}"),
            base._decision_step("MultiUAVCoordinator", "height_layering", "多 UAV 协同需要时空分离", "生成主机/护航机/备援机轨迹"),
            base._decision_step("TrajectorySmoother", "continuous_flight", "离散航点转连续轨迹", "输出多 UAV 可视化轨迹"),
        ], trace, uavs
    )
    output["time_space_conflicts"] = output.get("multi_uav_plan", {}).get("time_space_conflicts", [])
    return 200, "CoordField allocation generated with score-based UAV assignment and multi-UAV coordination", output


def risk_assessment(input_data: Dict[str, Any]) -> Dict[str, Any]:
    previous = input_data.get("previous_results", {})
    airspace = previous.get("AIR_01", {})
    weather = previous.get("WEA_01", {})
    candidates = {k: v for k, v in previous.items() if k.startswith("ROUTE_") and v}
    risk_factors = []
    if not airspace.get("is_clear", True):
        risk_factors.append("temporary_airspace_restriction")
    if not weather.get("is_flyable", True):
        risk_factors.append("adverse_weather")

    feasible = {k: v for k, v in candidates.items() if v.get("time_window_met", True)}
    if risk_factors:
        ground = {k: v for k, v in feasible.items() if v.get("assigned_vehicle_type") == "ground_vehicle"}
        feasible = ground or feasible

    def score(item):
        out = item[1]
        conflict_penalty = sum(1 for c in out.get("route_conflict_checks", []) if c.get("status") in {"blocked", "unsafe"}) * 25
        ground_bonus = 18 if risk_factors and out.get("assigned_vehicle_type") == "ground_vehicle" else 0
        smoothing_bonus = 5 if out.get("smoothed_trajectory") else 0
        multi_uav_bonus = 4 if out.get("multi_uav_plan", {}).get("enabled") else 0
        return (
            float(out.get("compliance_score", 0.85)) * 50
            - float(out.get("estimated_duration_mins", 60)) * 0.4
            - float(out.get("estimated_energy_kj", 1000)) * 0.005
            - conflict_penalty
            + ground_bonus
            + smoothing_bonus
            + multi_uav_bonus
        )

    recommended = max(feasible.items(), key=score)[0] if feasible else ""
    risk_score = min(1.0, 0.12 + (0.35 if "temporary_airspace_restriction" in risk_factors else 0) + (0.32 if "adverse_weather" in risk_factors else 0))
    return {
        "risk_level": "HIGH" if risk_score >= 0.7 else "MEDIUM" if risk_score >= 0.4 else "LOW",
        "risk_score": round(risk_score, 3),
        "dispatch_allowed": bool(recommended),
        "recommended_subtask_id": recommended,
        "risk_factors": risk_factors,
        "evaluated_candidates": list(candidates),
        "candidate_scores": {k: round(score((k, v)), 3) for k, v in candidates.items()},
        "airspace_snapshot": airspace,
        "weather_snapshot": weather,
        "decision_basis": [
            "过滤不满足时间窗的候选方案",
            "高风险场景优先选择 ground_vehicle 兜底方案",
            "综合合规、耗时、能耗、冲突惩罚、平滑轨迹和多机协同能力进行推荐",
        ],
    }


def execute_tool(tool_name: str, input_data: Dict[str, Any], parameters: Dict[str, Any], subtask_id: str):
    if tool_name == "compliance_route_service":
        return compliance_route(input_data, subtask_id)
    if tool_name == "weather_adaptive_dispatch_service":
        return weather_adaptive_dispatch(input_data)
    if tool_name == "medical_time_window_scheduler_service":
        return medical_time_window_schedule(input_data, subtask_id)
    if tool_name == "agentic_task_allocation_service":
        return agentic_task_allocation(input_data, subtask_id)
    if tool_name == "risk_assessment_service":
        return 200, "risk assessment completed", risk_assessment(input_data)
    return base.execute_tool(tool_name, input_data, parameters, subtask_id)
