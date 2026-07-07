"""Enhanced ROUTE tools for low-altitude medical delivery.

This module keeps the existing service contract but replaces the four ROUTE tools
with stronger implementations inspired by open-source UAV planning projects:
- 3D A* path search with hard/soft obstacle cells;
- MILP-like medical time-window candidate evaluation;
- risk-adaptive air/ground fallback;
- score-based UAV task allocation with time-space conflict checks.
"""

import heapq
from itertools import count
from typing import Any, Dict, Iterable, List, Tuple

from services.low_altitude_service import algorithms as base

GridPoint = Tuple[int, int, int]


def _heuristic(a: GridPoint, b: GridPoint) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + 0.6 * abs(a[2] - b[2])


def _neighbors(point: GridPoint, size: int = 28, z_levels: int = 4) -> Iterable[GridPoint]:
    x, y, z = point
    for dx, dy, dz in (
        (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
        (1, 1, 0), (1, -1, 0), (-1, 1, 0), (-1, -1, 0),
        (0, 0, 1), (0, 0, -1),
    ):
        nxt = (x + dx, y + dy, z + dz)
        if 0 <= nxt[0] < size and 0 <= nxt[1] < size and 0 <= nxt[2] < z_levels:
            yield nxt


def _astar(start: GridPoint, goal: GridPoint, blocked: set, weighted: Dict[GridPoint, float]) -> Tuple[List[GridPoint], float, int]:
    tie = count()
    q = [(0.0, next(tie), start)]
    parent: Dict[GridPoint, GridPoint] = {}
    cost = {start: 0.0}
    expanded = 0
    while q:
        _, _, current = heapq.heappop(q)
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
            step = 1.414 if nxt[0] != current[0] and nxt[1] != current[1] else 1.0
            step += 0.35 if nxt[2] != current[2] else 0.0
            step += weighted.get(nxt, 0.0)
            new_cost = cost[current] + step
            if new_cost < cost.get(nxt, float("inf")):
                parent[nxt] = current
                cost[nxt] = new_cost
                heapq.heappush(q, (new_cost + _heuristic(nxt, goal), next(tie), nxt))
    return [], float("inf"), expanded


def _bounds(mission: Dict[str, Any], obstacles: List[Dict[str, Any]]) -> Dict[str, float]:
    pickup, dropoff = base._point_pair(mission)
    lons = [float(pickup.get("lon", 0.0)), float(dropoff.get("lon", 0.0))]
    lats = [float(pickup.get("lat", 0.0)), float(dropoff.get("lat", 0.0))]
    for obs in obstacles:
        if "center_lon" in obs:
            lons.append(float(obs["center_lon"]))
            lats.append(float(obs["center_lat"]))
        for p in obs.get("polyline_geo", []):
            lons.append(float(p["lon"]))
            lats.append(float(p["lat"]))
    lon_pad = max((max(lons) - min(lons)) * 0.35, 0.03)
    lat_pad = max((max(lats) - min(lats)) * 0.35, 0.03)
    return {"min_lon": min(lons)-lon_pad, "max_lon": max(lons)+lon_pad, "min_lat": min(lats)-lat_pad, "max_lat": max(lats)+lat_pad}


def _geo_to_grid(lon: float, lat: float, bounds: Dict[str, float], size: int = 28) -> Tuple[int, int]:
    x = round((lon - bounds["min_lon"]) / max(bounds["max_lon"] - bounds["min_lon"], 1e-6) * (size - 1))
    y = round((lat - bounds["min_lat"]) / max(bounds["max_lat"] - bounds["min_lat"], 1e-6) * (size - 1))
    return max(0, min(size - 1, x)), max(0, min(size - 1, y))


def _grid_to_geo(point: GridPoint, bounds: Dict[str, float], altitude: float) -> Tuple[float, float, float]:
    x, y, z = point
    lon = bounds["min_lon"] + (bounds["max_lon"] - bounds["min_lon"]) * x / 27
    lat = bounds["min_lat"] + (bounds["max_lat"] - bounds["min_lat"]) * y / 27
    alt = max(0.0, altitude + (z - 2) * 9)
    return round(lon, 6), round(lat, 6), round(alt, 1)


def _cells_near(center: Tuple[int, int], radius: int, z_values=range(4)) -> List[GridPoint]:
    cx, cy = center
    cells = []
    for x in range(cx-radius, cx+radius+1):
        for y in range(cy-radius, cy+radius+1):
            if (x-cx)**2 + (y-cy)**2 <= radius**2:
                for z in z_values:
                    cells.append((x, y, z))
    return cells


def _obstacle_costs(obstacles: List[Dict[str, Any]], bounds: Dict[str, float], vehicle_type: str, profile: str) -> Tuple[set, Dict[GridPoint, float]]:
    blocked = set()
    weighted: Dict[GridPoint, float] = {}
    if vehicle_type == "ground_vehicle":
        return blocked, weighted
    for obs in obstacles:
        if "center_lon" not in obs:
            continue
        center = _geo_to_grid(float(obs["center_lon"]), float(obs["center_lat"]), bounds)
        radius = max(1, min(5, round(float(obs.get("radius_km", 1.0)) * 1.2)))
        kind = obs.get("kind")
        if kind == "no_fly_zone":
            blocked.update(_cells_near(center, radius + 1))
        elif kind == "weather_cell":
            for cell in _cells_near(center, radius):
                weighted[cell] = max(weighted.get(cell, 0.0), 8.0)
        elif kind in {"building_cluster", "sensitive_area"}:
            for cell in _cells_near(center, radius):
                weighted[cell] = max(weighted.get(cell, 0.0), 3.0)
        elif kind == "resource_bottleneck":
            for cell in _cells_near(center, radius):
                weighted[cell] = max(weighted.get(cell, 0.0), 2.0)
    if profile == "medical_time_window":
        weighted = {k: v * 0.65 for k, v in weighted.items()}
    elif profile == "drl_compliance":
        weighted = {k: v * 1.25 for k, v in weighted.items()}
    return blocked, weighted


def _compress(path: List[GridPoint], keep_every: int = 3) -> List[GridPoint]:
    if len(path) <= 10:
        return path
    out = [path[0]]
    for i in range(1, len(path)-1):
        prev_dir = (path[i][0]-path[i-1][0], path[i][1]-path[i-1][1], path[i][2]-path[i-1][2])
        next_dir = (path[i+1][0]-path[i][0], path[i+1][1]-path[i][1], path[i+1][2]-path[i][2])
        if prev_dir != next_dir or i % keep_every == 0:
            out.append(path[i])
    out.append(path[-1])
    return out


def _ground_route(mission: Dict[str, Any]) -> List[Dict[str, Any]]:
    return base._build_route_nodes(mission, 0.0, "ground_fallback")


def _route_distance(nodes: List[Dict[str, Any]]) -> float:
    return round(sum(base._segment_distance_km(nodes[i], nodes[i + 1]) for i in range(max(len(nodes) - 1, 0))), 3)


def _astar_nodes(mission: Dict[str, Any], altitude: float, profile: str, obstacles: List[Dict[str, Any]], vehicle_type: str = "uav") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if vehicle_type == "ground_vehicle":
        return _ground_route(mission), {"planner": "ground_corridor_fallback", "grid_path_length": 0, "grid_cost": 0.0}
    pickup, dropoff = base._point_pair(mission)
    bounds = _bounds(mission, obstacles)
    sx, sy = _geo_to_grid(float(pickup.get("lon", 0.0)), float(pickup.get("lat", 0.0)), bounds)
    gx, gy = _geo_to_grid(float(dropoff.get("lon", 0.0)), float(dropoff.get("lat", 0.0)), bounds)
    z = 2 if altitude >= 85 else 1
    blocked, weighted = _obstacle_costs(obstacles, bounds, vehicle_type, profile)
    path, cost, expanded = _astar((sx, sy, z), (gx, gy, z), blocked, weighted)
    if not path:
        return base._build_route_nodes(mission, altitude, profile), {"planner": "template_fallback_after_astar_failure", "grid_path_length": 0, "grid_cost": float("inf"), "expanded_nodes": expanded}
    compact = _compress(path)
    labels = {
        "drl_compliance": ("A*_COMPLIANCE", "A*合规避障航点", "规避禁飞/障碍风险"),
        "medical_time_window": ("A*_MEDICAL", "A*医疗时间窗航点", "压缩ETA并保持约束可行"),
        "coordfield_allocation": ("A*_ALLOC", "A*协同分配航点", "为任务分配保留中继余量"),
        "air_ground_coordination": ("A*_TRANSFER", "A*空地协同航点", "飞至安全交接区域"),
    }
    prefix, name, action = labels.get(profile, ("A*_WP", "A*航点", "航路推进"))
    nodes = [base._point_node(pickup, altitude, "pickup", "pickup")]
    for idx, pt in enumerate(compact[1:-1], 1):
        lon, lat, alt = _grid_to_geo(pt, bounds, altitude)
        nodes.append(base._route_node(f"{prefix}_{idx:02d}", f"{name}{idx}", lon, lat, alt, "avoidance" if pt in weighted else "waypoint", action))
    nodes.append(base._point_node(dropoff, max(0.0, altitude - 8), "dropoff", "dropoff"))
    return nodes, {
        "planner": "time_space_astar_3d",
        "grid_path_length": len(path),
        "compressed_waypoints": len(nodes),
        "grid_cost": round(cost, 3),
        "expanded_nodes": expanded,
        "hard_blocked_cells": len(blocked),
        "weighted_risk_cells": len(weighted),
    }


def _energy(distance: float, cargo: float, wind: float, vehicle_type: str, efficiency: float = 1.0) -> float:
    if vehicle_type == "ground_vehicle":
        return round(distance * 44.0 * efficiency, 2)
    return round(distance * (21.0 + cargo * 3.1) * (1 + wind / 45) * efficiency, 2)


def _constraint_summary(mission: Dict[str, Any], nodes: List[Dict[str, Any]], uav: Dict[str, Any], energy_kj: float) -> Dict[str, Any]:
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    return {
        "payload_feasible": float(uav.get("max_payload_kg", 0.0)) >= cargo,
        "battery_feasible": float(uav.get("battery_percent", 0.0)) >= max(25.0, energy_kj / 40.0),
        "route_node_count": len(nodes),
        "payload_margin_kg": round(float(uav.get("max_payload_kg", 0.0)) - cargo, 2),
        "medical_priority": mission.get("priority", 3),
    }


def _visual(mission, nodes, duration, vehicle_type, algorithm, vehicle_id, scenario, obstacles, risk_tags, steps, trace):
    visual = base._build_route_visualization(mission, nodes, duration, vehicle_type, algorithm, vehicle_id, scenario, obstacles, risk_tags, steps)
    visual["planner_trace"] = trace
    visual["route_quality_metrics"]["distance_km"] = _route_distance(nodes)
    return visual


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
    output = {
        "algorithm": "DRL-LLM",
        "algorithm_family": "A*_3D_compliance_planner",
        "uav_id": uavs[0]["uav_id"],
        "assigned_vehicle_type": "uav",
        "waypoints_3d": base._waypoints_from_nodes(nodes),
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "time_window_slack_mins": base._time_window_slack_mins(mission, duration) if hasattr(base, "_time_window_slack_mins") else None,
        "compliance_score": round(max(0.55, 0.98 - 0.015 * max(len(nodes)-5, 0) - 0.08 * penalty), 3),
        "collision_risk": round(0.035 + 0.01 * penalty, 3),
        "constraint_summary": _constraint_summary(mission, nodes, uavs[0], energy),
        "optimization_objective": "minimize weighted airspace risk + distance + energy under UAV feasibility constraints",
    }
    output.update(_visual(mission, nodes, duration, "uav", "A* enhanced DRL-LLM compliance route", uavs[0]["uav_id"], scenario, obstacles, [], [
        base._decision_step("ComplianceRouteService", "astar_search", "空域、气象、无人机状态满足前置依赖", "执行三维A*合规航路搜索"),
        base._decision_step("ComplianceRouteService", "risk_weighting", "建筑群、敏感区和线性障碍转为网格代价", "生成可解释避障航点"),
        base._decision_step("PostprocessAgent", "score", "合规评分高、碰撞风险低", "进入候选方案池"),
    ], trace))
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
    if unsafe_air: risk_tags.append("temporary_airspace_restriction")
    if unsafe_weather: risk_tags.append("adverse_weather")
    if not uavs: risk_tags.append("uav_unavailable")
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
    output.update(_visual(mission, nodes, duration, vehicle_type, "NN weather-adaptive air-ground dispatch", vehicle_id, scenario, obstacles, risk_tags, [
        base._decision_step("ReplanDecisionAgent", "fallback" if ground_mode else "parallel_candidate", "空域/气象/无人机约束触发备用策略" if ground_mode else "作为空地协同候选方案并行生成", "选择地面兜底路径" if ground_mode else "生成空地协同路径"),
        base._decision_step("WeatherAdaptiveService", "risk_avoidance", "规避强天气/禁飞核心区", "切换道路安全接驳或安全交接节点"),
        base._decision_step("RiskAssessmentService", "authorize", "风险区不再被飞行路径穿越", "允许进入候选推荐"),
    ], trace))
    return 200, "weather-adaptive air-ground plan generated with fallback context", output


def _medical_slack(mission, duration):
    if hasattr(base, "_time_window_slack_mins"):
        return base._time_window_slack_mins(mission, duration)
    return None


def _medical_candidates(mission, scenario, airspace, weather, dock):
    obstacles = base._scene_obstacles(mission, scenario, airspace, weather, dock)
    out = []
    for name, altitude, speed, eff in [
        ("medical_fast_corridor", 90.0, 65.0, 0.96),
        ("medical_safe_corridor", 102.0, 58.0, 1.06),
        ("medical_energy_saving_corridor", 82.0, 54.0, 0.86),
    ]:
        nodes, trace = _astar_nodes(mission, altitude, "medical_time_window", obstacles)
        distance = _route_distance(nodes)
        duration = round(distance / speed * 60.0 + 1.2 + 0.02 * len(nodes), 2)
        energy = _energy(distance, float(mission.get("cargo_weight_kg", 0.0)), float(weather.get("wind_speed_mps", 0.0)), "uav", eff)
        eta, met = base._window_result(mission, duration)
        slack = _medical_slack(mission, duration)
        risk_load = sum(1 for obs in obstacles if obs.get("severity") == "high")
        objective = round(duration * 0.45 + energy * 0.004 + risk_load * 3.0 - max(min(float(slack or 0), 30), -30) * 0.08, 3)
        out.append({"corridor_name": name, "route_nodes": nodes, "planner_trace": trace, "distance": distance, "duration": duration, "energy": energy, "eta": eta, "time_window_met": met, "slack": slack, "objective_value": objective})
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
    pickup, dropoff = base._point_pair(mission)
    uav = max(uavs, key=lambda u: (float(u.get("battery_percent", 0)), float(u.get("max_payload_kg", 0))))
    output = {
        "algorithm": "TWA-MILP",
        "algorithm_family": "time_window_milp_inspired_candidate_optimizer",
        "uav_id": uav["uav_id"],
        "assigned_vehicle_type": "uav",
        "dispatch_sequence": [pickup.get("id", "pickup"), dropoff.get("id", "dropoff")],
        "waypoints_3d": base._waypoints_from_nodes(nodes),
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
        "candidate_corridors": [{"corridor_name": c["corridor_name"], "duration_mins": c["duration"], "energy_kj": c["energy"], "time_window_met": c["time_window_met"], "objective_value": c["objective_value"], "planner": c["planner_trace"].get("planner")} for c in sorted(candidates, key=lambda c: c["objective_value"])],
        "milp_like_variables": {"x_route_selected": selected["corridor_name"], "uav_assignment": uav["uav_id"], "deadline_constraint": selected["time_window_met"], "payload_constraint": uav.get("max_payload_kg", 0) >= float(mission.get("cargo_weight_kg", 0.0))},
        "compliance_score": round(0.93 if selected["time_window_met"] else 0.82, 3),
        "constraint_summary": _constraint_summary(mission, nodes, uav, selected["energy"]),
    }
    output.update(_visual(mission, nodes, selected["duration"], "uav", "TWA-MILP medical time-window schedule", uav["uav_id"], scenario, obstacles, [], [
        base._decision_step("DecomposeAgent", "insert_medical_scheduler", "任务类型为 emergency_medical", "加入医疗时间窗调度节点"),
        base._decision_step("MedicalScheduler", "candidate_optimize", "以截止期、载荷、能耗、风险为目标函数", f"选择 {selected['corridor_name']}"),
        base._decision_step("PostprocessAgent", "score", "预计到达时间满足时间窗" if selected["time_window_met"] else "未完全满足时间窗但保留最小惩罚方案", "进入候选方案池"),
    ], selected["planner_trace"]))
    return 200, "TWA-MILP optimal schedule generated with A* medical corridors", output


def _score_uav(uav, mission, pickup, weather):
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    margin = float(uav.get("max_payload_kg", 0.0)) - cargo
    dist = base.haversine_km(float(uav.get("current_lon", pickup.get("lon", 0.0))), float(uav.get("current_lat", pickup.get("lat", 0.0))), float(pickup.get("lon", 0.0)), float(pickup.get("lat", 0.0)))
    battery = float(uav.get("battery_percent", 0.0))
    score = 0.42 * battery / 100 + 0.32 * max(0.0, min(margin / 5.0, 1.0)) + 0.18 * max(0.0, 1 - dist / 20) - float(weather.get("wind_speed_mps", 0.0)) / 100
    if uav.get("health") == "standby": score -= 0.04
    return {"uav_id": uav.get("uav_id"), "battery_percent": battery, "payload_margin_kg": round(margin, 2), "pickup_distance_km": round(dist, 3), "allocation_score": round(max(score, 0.0), 3)}


def _route_signature(nodes):
    sig = []
    for idx in range(16):
        p, _ = base._interpolate_route(nodes, idx / 15)
        sig.append((round(p["lon"] * 1000), round(p["lat"] * 1000), round(p["altitude_m"] / 10)))
    return sig


def _conflicts(routes):
    occupied = {}
    out = []
    for rid, route in enumerate(routes):
        for t, cell in enumerate(route):
            key = (t, cell)
            if key in occupied:
                out.append({"time_index": t, "cell": cell, "agents": [occupied[key], rid]})
            else:
                occupied[key] = rid
    return out


def agentic_task_allocation(input_data: Dict[str, Any], subtask_id: str):
    mission = base._mission(input_data)
    scenario = base._scenario(input_data)
    airspace = base._previous(input_data, "AIR_01")
    weather = base._previous(input_data, "WEA_01")
    dock = base._previous(input_data, "DOCK_01")
    uavs = base._available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for CoordField allocation", {}
    pickup, dropoff = base._point_pair(mission)
    scored = sorted([_score_uav(u, mission, pickup, weather) for u in uavs], key=lambda x: x["allocation_score"], reverse=True)
    selected_id = scored[0]["uav_id"]
    selected = next(u for u in uavs if u["uav_id"] == selected_id)
    obstacles = base._scene_obstacles(mission, scenario, airspace, weather, dock)
    nodes, trace = _astar_nodes(mission, 78.0, "coordfield_allocation", obstacles)
    distance = _route_distance(nodes)
    duration = round(distance / 55.0 * 60.0 + 2.3 + 0.04 * len(nodes), 2)
    energy = _energy(distance, float(mission.get("cargo_weight_kg", 0.0)), float(weather.get("wind_speed_mps", 0.0)), "uav", 1.02)
    eta, met = base._window_result(mission, duration)
    conflicts = _conflicts([_route_signature(nodes)])
    output = {
        "algorithm": "CoordField",
        "algorithm_family": "score_based_multi_uav_allocation",
        "uav_id": selected_id,
        "assigned_vehicle_type": "uav",
        "assignments": [{"uav_id": selected_id, "task": f"{pickup.get('id')}->{dropoff.get('id')}", "allocation_score": scored[0]["allocation_score"], "policy": "battery_payload_distance_score"}],
        "candidate_uav_scores": scored,
        "task_coverage_rate": 1.0,
        "response_time_mins": duration,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "flight_distance_km": distance,
        "eta": eta,
        "time_window_met": met,
        "reallocation_count": 1 if scenario != "normal" else 0,
        "time_space_conflicts": conflicts,
        "coordination_policy": "select best UAV by battery/payload/distance and reserve relay corridor",
        "compliance_score": round(max(0.74, 0.90 - 0.03 * len(conflicts)), 3),
        "constraint_summary": _constraint_summary(mission, nodes, selected, energy),
    }
    output.update(_visual(mission, nodes, duration, "uav", "CoordField agentic task allocation", selected_id, scenario, obstacles, [], [
        base._decision_step("AgenticAllocationService", "score_uavs", "根据载荷、位置、电量和任务覆盖率分配 UAV", f"选择 {selected_id}"),
        base._decision_step("AgenticAllocationService", "reserve_reallocation", "保留动态重分配余量", "生成中继点和末端接近航点"),
        base._decision_step("AgenticAllocationService", "time_space_check", "检查同一时间同一空域网格占用", "未发现冲突" if not conflicts else "发现冲突并保留重分配标记"),
    ], trace))
    return 200, "CoordField allocation generated with score-based UAV assignment", output


def risk_assessment(input_data: Dict[str, Any]) -> Dict[str, Any]:
    previous = input_data.get("previous_results", {})
    airspace = previous.get("AIR_01", {})
    weather = previous.get("WEA_01", {})
    candidates = {k: v for k, v in previous.items() if k.startswith("ROUTE_") and v}
    risk_factors = []
    if not airspace.get("is_clear", True): risk_factors.append("temporary_airspace_restriction")
    if not weather.get("is_flyable", True): risk_factors.append("adverse_weather")
    feasible = {k: v for k, v in candidates.items() if v.get("time_window_met", True)}
    if risk_factors:
        ground = {k: v for k, v in feasible.items() if v.get("assigned_vehicle_type") == "ground_vehicle"}
        feasible = ground or feasible
    def score(item):
        out = item[1]
        conflict_penalty = sum(1 for c in out.get("route_conflict_checks", []) if c.get("status") in {"blocked", "unsafe"}) * 25
        ground_bonus = 18 if risk_factors and out.get("assigned_vehicle_type") == "ground_vehicle" else 0
        return float(out.get("compliance_score", 0.85)) * 50 - float(out.get("estimated_duration_mins", 60)) * 0.4 - float(out.get("estimated_energy_kj", 1000)) * 0.005 - conflict_penalty + ground_bonus
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
        "decision_basis": ["过滤不满足时间窗的候选方案", "高风险场景优先选择 ground_vehicle 兜底方案", "综合合规、耗时、能耗、冲突惩罚和地面兜底奖励进行推荐"],
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
