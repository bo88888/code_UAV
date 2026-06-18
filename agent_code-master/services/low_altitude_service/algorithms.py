import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _mission(input_data: Dict[str, Any]) -> Dict[str, Any]:
    return input_data.get("mission") or input_data.get("xml_config", {})


def _scenario(input_data: Dict[str, Any]) -> str:
    return _mission(input_data).get("simulation_scenario", "normal")


def _previous(input_data: Dict[str, Any], subtask_id: str) -> Dict[str, Any]:
    return input_data.get("previous_results", {}).get(subtask_id, {})


def _as_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _point_pair(mission: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    points = mission.get("delivery_points", [])
    pickup = next(
        (point for point in points if point.get("role") == "pickup"),
        points[0] if points else {},
    )
    dropoff = next(
        (point for point in points if point.get("role") == "dropoff"),
        points[-1] if points else {},
    )
    return pickup, dropoff


def haversine_km(
    lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance(mission: Dict[str, Any], multiplier: float = 1.0) -> float:
    pickup, dropoff = _point_pair(mission)
    distance = haversine_km(
        float(pickup.get("lon", 0.0)),
        float(pickup.get("lat", 0.0)),
        float(dropoff.get("lon", 0.0)),
        float(dropoff.get("lat", 0.0)),
    )
    return round(distance * multiplier, 3)


def _point_node(
    point: Dict[str, Any],
    altitude_m: float,
    node_type: str,
    default_name: str,
) -> Dict[str, Any]:
    return {
        "id": point.get("id", default_name),
        "name": point.get("id", default_name),
        "lon": float(point.get("lon", 0.0)),
        "lat": float(point.get("lat", 0.0)),
        "altitude_m": round(float(altitude_m), 1),
        "type": node_type,
        "action": "起飞装载" if node_type == "pickup" else "投送交付",
    }


def _mission_midpoint(mission: Dict[str, Any]) -> Tuple[float, float]:
    pickup, dropoff = _point_pair(mission)
    return (
        (float(pickup.get("lon", 0.0)) + float(dropoff.get("lon", 0.0))) / 2,
        (float(pickup.get("lat", 0.0)) + float(dropoff.get("lat", 0.0))) / 2,
    )


def _route_node(
    node_id: str,
    name: str,
    lon: float,
    lat: float,
    altitude_m: float,
    node_type: str,
    action: str,
) -> Dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "lon": round(lon, 6),
        "lat": round(lat, 6),
        "altitude_m": round(float(altitude_m), 1),
        "type": node_type,
        "action": action,
    }


def _scene_obstacles(
    mission: Dict[str, Any],
    scenario: str,
    airspace: Optional[Dict[str, Any]] = None,
    weather: Optional[Dict[str, Any]] = None,
    dock: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    mid_lon, mid_lat = _mission_midpoint(mission)
    obstacles: List[Dict[str, Any]] = [
        {
            "id": "OBS_BUILDING_CLUSTER",
            "name": "高层建筑群",
            "kind": "building_cluster",
            "severity": "medium",
            "center_lon": round(mid_lon - 0.008, 6),
            "center_lat": round(mid_lat + 0.004, 6),
            "radius_km": 1.45,
            "height_m": 118,
            "avoidance_rule": "水平绕飞且最低净空 35m",
        },
        {
            "id": "OBS_POWERLINE",
            "name": "高压线走廊",
            "kind": "linear_obstacle",
            "severity": "medium",
            "polyline_geo": [
                {"lon": round(mid_lon - 0.025, 6), "lat": round(mid_lat - 0.006, 6)},
                {"lon": round(mid_lon + 0.025, 6), "lat": round(mid_lat + 0.012, 6)},
            ],
            "height_m": 68,
            "avoidance_rule": "跨越点高度不低于 90m 或绕行",
        },
        {
            "id": "OBS_SCHOOL_ZONE",
            "name": "人口密集敏感区",
            "kind": "sensitive_area",
            "severity": "low",
            "center_lon": round(mid_lon + 0.013, 6),
            "center_lat": round(mid_lat + 0.004, 6),
            "radius_km": 1.10,
            "avoidance_rule": "降低穿越概率，优先沿道路/水系边界绕行",
        },
    ]

    no_fly_zones = (airspace or {}).get("no_fly_zones", [])
    for zone in no_fly_zones:
        obstacles.append(
            {
                "id": zone.get("zone_id", "NFZ"),
                "name": "临时禁飞区",
                "kind": "no_fly_zone",
                "severity": "high",
                "center_lon": zone.get("center_lon", round(mid_lon, 6)),
                "center_lat": zone.get("center_lat", round(mid_lat, 6)),
                "radius_km": zone.get("radius_km", 2.8),
                "avoidance_rule": "禁止穿越，必须切换备用航路或地面兜底",
            }
        )

    weather_cell = (weather or {}).get("weather_cell", {})
    if scenario == "bad_weather" or weather_cell.get("level") == "convective_rain":
        obstacles.append(
            {
                "id": "WX_CONVECTIVE_CELL",
                "name": "强降水/低能见度天气单元",
                "kind": "weather_cell",
                "severity": "high",
                "center_lon": weather_cell.get("center_lon", round(mid_lon + 0.01, 6)),
                "center_lat": weather_cell.get("center_lat", round(mid_lat + 0.008, 6)),
                "radius_km": weather_cell.get("radius_km", 3.5),
                "avoidance_rule": "不可穿越核心区，必要时转为空地协同或地面兜底",
            }
        )

    if scenario == "dock_congested" or not (dock or {}).get("battery_swap_available", True):
        obstacles.append(
            {
                "id": "RESOURCE_DOCK_CONGESTION",
                "name": "机巢充换电拥堵",
                "kind": "resource_bottleneck",
                "severity": "medium",
                "center_lon": round(mid_lon - 0.018, 6),
                "center_lat": round(mid_lat - 0.012, 6),
                "radius_km": 0.9,
                "avoidance_rule": "避免将返航/换电节点压到拥堵机巢",
            }
        )
    return obstacles


def _build_route_nodes(
    mission: Dict[str, Any],
    altitude_m: float,
    profile: str,
) -> List[Dict[str, Any]]:
    pickup, dropoff = _point_pair(mission)
    start = _point_node(pickup, altitude_m, "pickup", "pickup")
    end = _point_node(dropoff, altitude_m, "dropoff", "dropoff")
    mid_lon, mid_lat = _mission_midpoint(mission)

    if profile == "drl_compliance":
        return [
            start,
            _route_node("GATE_AIRSPACE", "空域合规门", mid_lon - 0.020, mid_lat - 0.018, altitude_m, "gate", "通过空域约束检查"),
            _route_node("WP_BUILDING_BYPASS", "建筑群绕飞点", mid_lon - 0.002, mid_lat - 0.019, altitude_m, "avoidance", "绕开高层建筑群"),
            _route_node("WP_POWERLINE_CROSS", "高压线跨越点", mid_lon + 0.017, mid_lat + 0.002, max(altitude_m, 96), "avoidance", "提高高度跨越线性障碍"),
            end,
        ]
    if profile == "medical_time_window":
        return [
            start,
            _route_node("MED_FAST_GATE", "医疗优先走廊入口", mid_lon - 0.026, mid_lat + 0.014, altitude_m, "priority_gate", "进入医疗优先航路"),
            _route_node("MED_SHORTCUT", "时间窗捷径航点", mid_lon - 0.004, mid_lat + 0.024, altitude_m, "waypoint", "缩短 ETA 以满足医疗时限"),
            _route_node("MED_DESCENT_GATE", "末端下降门", mid_lon + 0.024, mid_lat + 0.014, altitude_m - 12, "gate", "末端减速下降"),
            end,
        ]
    if profile == "coordfield_allocation":
        return [
            start,
            _route_node("ALLOC_SPLIT", "任务分配汇合点", mid_lon - 0.018, mid_lat + 0.022, altitude_m, "allocation", "CoordField 分配无人机"),
            _route_node("ALLOC_RELAY", "协同中继点", mid_lon + 0.008, mid_lat + 0.030, altitude_m, "relay", "保留动态重分配余量"),
            _route_node("ALLOC_FINAL", "末端接近航点", mid_lon + 0.026, mid_lat + 0.010, altitude_m - 8, "waypoint", "末端接近"),
            end,
        ]
    if profile == "ground_fallback":
        return [
            _point_node(pickup, 0.0, "pickup", "pickup"),
            _route_node("ROAD_SAFE_NODE_1", "道路安全接驳点 1", mid_lon - 0.028, mid_lat - 0.021, 0.0, "ground_node", "避开禁飞/天气核心区"),
            _route_node("ROAD_TRANSFER", "地面转运节点", mid_lon + 0.016, mid_lat - 0.018, 0.0, "transfer", "地面车辆接驳"),
            _route_node("ROAD_SAFE_NODE_2", "道路安全接驳点 2", mid_lon + 0.035, mid_lat + 0.001, 0.0, "ground_node", "沿地面安全走廊接近"),
            _point_node(dropoff, 0.0, "dropoff", "dropoff"),
        ]
    if profile == "air_ground_coordination":
        return [
            start,
            _route_node("AIR_TRANSFER_GATE", "空地协同交接门", mid_lon - 0.022, mid_lat - 0.012, altitude_m, "transfer", "无人机飞至安全交接点"),
            _route_node("SAFE_TRANSFER_NODE", "安全接驳点", mid_lon + 0.012, mid_lat - 0.020, 0.0, "transfer", "切换地面或低高度转运"),
            _point_node(dropoff, 0.0, "dropoff", "dropoff"),
        ]
    return [start, end]


def _waypoints_from_nodes(nodes: List[Dict[str, Any]]) -> List[List[float]]:
    return [[node["lon"], node["lat"], node["altitude_m"]] for node in nodes]


def _window_result(
    mission: Dict[str, Any], duration_mins: float
) -> Tuple[str, bool]:
    pickup, dropoff = _point_pair(mission)
    ready_at = _as_datetime(pickup.get("ready_time", ""))
    deadline = _as_datetime(dropoff.get("deadline", ""))
    if ready_at is None:
        ready_at = datetime(2026, 6, 11, 10, 0, 0)
    eta = ready_at + timedelta(minutes=duration_mins)
    return eta.isoformat(timespec="seconds"), deadline is None or eta <= deadline


def _segment_distance_km(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    return haversine_km(float(a["lon"]), float(a["lat"]), float(b["lon"]), float(b["lat"]))


def _geo_bounds(nodes: List[Dict[str, Any]], obstacles: Optional[List[Dict[str, Any]]] = None) -> Dict[str, float]:
    if not nodes:
        return {"min_lon": 0, "max_lon": 0, "min_lat": 0, "max_lat": 0}
    lons = [float(node["lon"]) for node in nodes]
    lats = [float(node["lat"]) for node in nodes]
    for obstacle in obstacles or []:
        if "center_lon" in obstacle and "center_lat" in obstacle:
            lons.append(float(obstacle["center_lon"]))
            lats.append(float(obstacle["center_lat"]))
        for point in obstacle.get("polyline_geo", []):
            lons.append(float(point["lon"]))
            lats.append(float(point["lat"]))
    lon_pad = max((max(lons) - min(lons)) * 0.20, 0.012)
    lat_pad = max((max(lats) - min(lats)) * 0.20, 0.012)
    return {
        "min_lon": round(min(lons) - lon_pad, 6),
        "max_lon": round(max(lons) + lon_pad, 6),
        "min_lat": round(min(lats) - lat_pad, 6),
        "max_lat": round(max(lats) + lat_pad, 6),
    }


def _interpolate_route(
    nodes: List[Dict[str, Any]], progress: float
) -> Tuple[Dict[str, float], int]:
    if not nodes:
        return {"lon": 0.0, "lat": 0.0, "altitude_m": 0.0}, 0
    if len(nodes) == 1:
        node = nodes[0]
        return {"lon": node["lon"], "lat": node["lat"], "altitude_m": node["altitude_m"]}, 0
    distances = [max(_segment_distance_km(nodes[i], nodes[i + 1]), 0.0001) for i in range(len(nodes) - 1)]
    total = sum(distances)
    target = max(0.0, min(1.0, progress)) * total
    travelled = 0.0
    for idx, segment_distance in enumerate(distances):
        if target <= travelled + segment_distance or idx == len(distances) - 1:
            ratio = (target - travelled) / segment_distance
            a, b = nodes[idx], nodes[idx + 1]
            return {
                "lon": round(a["lon"] + (b["lon"] - a["lon"]) * ratio, 6),
                "lat": round(a["lat"] + (b["lat"] - a["lat"]) * ratio, 6),
                "altitude_m": round(a["altitude_m"] + (b["altitude_m"] - a["altitude_m"]) * ratio, 1),
            }, idx
        travelled += segment_distance
    node = nodes[-1]
    return {"lon": node["lon"], "lat": node["lat"], "altitude_m": node["altitude_m"]}, len(nodes) - 2


def _route_conflict_checks(
    nodes: List[Dict[str, Any]], obstacles: List[Dict[str, Any]], vehicle_type: str
) -> List[Dict[str, Any]]:
    checks = []
    for obstacle in obstacles:
        severity = obstacle.get("severity", "low")
        clearance = 0.0
        status = "monitored"
        if obstacle.get("kind") == "no_fly_zone":
            status = "avoided_by_fallback" if vehicle_type == "ground_vehicle" else "blocked"
            clearance = 0.0 if status == "blocked" else 2.4
        elif obstacle.get("kind") == "weather_cell":
            status = "avoided" if vehicle_type in {"ground_vehicle", "air_ground_coordination"} else "unsafe"
            clearance = 3.1 if status == "avoided" else 0.4
        elif obstacle.get("kind") == "building_cluster":
            status = "avoided"
            clearance = 1.2
        elif obstacle.get("kind") == "linear_obstacle":
            max_alt = max([node.get("altitude_m", 0) for node in nodes] or [0])
            status = "altitude_crossing_ok" if max_alt >= 90 else "requires_altitude_adjustment"
            clearance = max(0.0, max_alt - obstacle.get("height_m", 0))
        else:
            status = "monitored"
            clearance = 0.9
        checks.append(
            {
                "obstacle_id": obstacle.get("id"),
                "name": obstacle.get("name"),
                "kind": obstacle.get("kind"),
                "severity": severity,
                "status": status,
                "min_clearance_km_or_m": round(clearance, 2),
                "rule": obstacle.get("avoidance_rule", ""),
            }
        )
    return checks


def _route_segments(nodes: List[Dict[str, Any]], vehicle_type: str) -> List[Dict[str, Any]]:
    segments = []
    for idx in range(max(len(nodes) - 1, 0)):
        start = nodes[idx]
        end = nodes[idx + 1]
        segment_distance = round(_segment_distance_km(start, end), 3)
        mode = "ground" if vehicle_type == "ground_vehicle" or start.get("altitude_m", 0) == 0 and end.get("altitude_m", 0) == 0 else "low_altitude_uav"
        segments.append(
            {
                "segment_id": f"SEG_{idx + 1:02d}",
                "from": start["id"],
                "to": end["id"],
                "mode": mode,
                "distance_km": segment_distance,
                "planned_altitude_m": start.get("altitude_m", 0.0),
                "segment_action": end.get("action", "航路推进"),
            }
        )
    return segments


def _build_route_visualization(
    mission: Dict[str, Any],
    route_nodes: List[Dict[str, Any]],
    duration_mins: float,
    vehicle_type: str,
    algorithm: str,
    uav_id: str = "",
    scenario: str = "normal",
    obstacles: Optional[List[Dict[str, Any]]] = None,
    risk_tags: Optional[List[str]] = None,
    decision_steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    obstacles = obstacles or []
    risk_tags = risk_tags or []
    total_distance = round(sum(_segment_distance_km(route_nodes[i], route_nodes[i + 1]) for i in range(max(len(route_nodes) - 1, 0))), 3)
    route_segments = _route_segments(route_nodes, vehicle_type)
    telemetry_stream: List[Dict[str, Any]] = []
    tactical_events: List[Dict[str, Any]] = []
    steps = 60
    base_battery = 92.0
    battery_drop = 5.0 + total_distance * (0.78 if vehicle_type != "ground_vehicle" else 0.22)
    for step in range(steps + 1):
        progress = step / steps
        point, segment_idx = _interpolate_route(route_nodes, progress)
        elapsed = round(duration_mins * progress, 2)
        if progress < 0.08:
            phase = "takeoff" if vehicle_type != "ground_vehicle" else "departing"
        elif progress > 0.92:
            phase = "landing" if vehicle_type != "ground_vehicle" else "arriving"
        else:
            phase = "obstacle_avoidance" if 0.32 <= progress <= 0.58 and vehicle_type != "ground_vehicle" else ("cruise" if vehicle_type != "ground_vehicle" else "ground_transfer")
        telemetry_stream.append(
            {
                "t_seconds": round(elapsed * 60, 1),
                "elapsed_mins": elapsed,
                "progress": round(progress, 3),
                "lon": point["lon"],
                "lat": point["lat"],
                "altitude_m": point["altitude_m"],
                "speed_kmh": 0 if step in {0, steps} else (46 if vehicle_type == "ground_vehicle" else 58),
                "battery_percent": round(base_battery - battery_drop * progress, 1),
                "segment_id": route_segments[segment_idx]["segment_id"] if route_segments else "SEG_00",
                "phase": phase,
                "vehicle_type": vehicle_type,
                "uav_id": uav_id or "GROUND-RESCUE-01",
            }
        )
    for progress, event, level in [
        (0.12, "起飞/离港校验完成", "info"),
        (0.34, "进入障碍物规避段", "warning"),
        (0.52, "完成建筑群/线性障碍规避", "success"),
        (0.78, "进入末端接近与投送窗口", "info"),
    ]:
        frame, _ = _interpolate_route(route_nodes, progress)
        tactical_events.append({"progress": progress, "event": event, "level": level, **frame})
    return {
        "operational_mode": vehicle_type,
        "algorithm_trace_name": algorithm,
        "route_polyline_geo": route_nodes,
        "route_segments": route_segments,
        "geo_bounds": _geo_bounds(route_nodes, obstacles),
        "obstacle_zones": obstacles,
        "route_conflict_checks": _route_conflict_checks(route_nodes, obstacles, vehicle_type),
        "telemetry_stream": telemetry_stream,
        "tactical_events": tactical_events,
        "live_state": telemetry_stream[0] if telemetry_stream else {},
        "agent_decision_steps": decision_steps or [],
        "route_quality_metrics": {
            "distance_km": total_distance,
            "turning_points": max(len(route_nodes) - 2, 0),
            "obstacle_count": len(obstacles),
            "risk_tag_count": len(risk_tags),
            "estimated_robustness": round(0.92 - 0.04 * len(risk_tags), 3),
        },
        "visual_overlays": {
            "scenario": scenario,
            "risk_tags": risk_tags,
            "show_no_fly_zone": "temporary_airspace_restriction" in risk_tags,
            "show_weather_cell": "adverse_weather" in risk_tags,
            "show_obstacles": True,
        },
    }


def _recovered_uav() -> Dict[str, Any]:
    return {"uav_id": "UAV-MED-RECOVERED", "battery_percent": 88, "max_payload_kg": 5.0, "health": "ready", "current_lon": 114.052, "current_lat": 22.538}


def _available_uavs(input_data: Dict[str, Any], subtask_id: str) -> List[Dict[str, Any]]:
    available = list(_previous(input_data, "UAV_01").get("available_uavs", []))
    retry_count = int(input_data.get("metadata", {}).get(f"retry_{subtask_id}", 0))
    if not available and _scenario(input_data) == "no_available_uav_once" and retry_count >= 1:
        return [_recovered_uav()]
    return available


def airspace_check(input_data: Dict[str, Any]) -> Dict[str, Any]:
    mission = _mission(input_data)
    constraints = mission.get("environmental_constraints", {})
    scenario = _scenario(input_data)
    restricted = scenario == "airspace_restricted" or bool(constraints.get("restricted_airspace", False))
    mid_lon, mid_lat = _mission_midpoint(mission)
    return {
        "is_clear": not restricted,
        "no_fly_zones": [{"zone_id": "NFZ-TEMP-01", "reason": "temporary emergency control", "center_lon": round(mid_lon, 6), "center_lat": round(mid_lat, 6), "radius_km": 2.8}] if restricted else [],
        "altitude_limit_m": float(constraints.get("maximum_altitude_m", 120.0)),
        "compliance_rules_checked": 8,
        "air_corridor_status": "restricted" if restricted else "available",
    }


def weather_check(input_data: Dict[str, Any]) -> Dict[str, Any]:
    mission = _mission(input_data)
    constraints = mission.get("environmental_constraints", {})
    scenario = _scenario(input_data)
    bad_weather = scenario == "bad_weather"
    wind = 13.5 if bad_weather else 4.5
    precipitation = 7.2 if bad_weather else 0.2
    visibility = 1.2 if bad_weather else 9.0
    max_wind = float(constraints.get("max_wind_speed_mps", 10.0))
    max_rain = float(constraints.get("max_precipitation_mm_h", 5.0))
    min_visibility = float(constraints.get("minimum_visibility_km", 2.0))
    mid_lon, mid_lat = _mission_midpoint(mission)
    return {
        "wind_speed_mps": wind,
        "precipitation_mm_h": precipitation,
        "visibility_km": visibility,
        "is_flyable": wind <= max_wind and precipitation <= max_rain and visibility >= min_visibility,
        "weather_window_mins": 45 if not bad_weather else 0,
        "weather_cell": {"center_lon": round(mid_lon + 0.01, 6), "center_lat": round(mid_lat + 0.008, 6), "radius_km": 3.5, "level": "convective_rain" if bad_weather else "normal"},
    }


def uav_status(input_data: Dict[str, Any]) -> Dict[str, Any]:
    mission = _mission(input_data)
    cargo_weight = float(mission.get("cargo_weight_kg", 0.0))
    scenario = _scenario(input_data)
    unavailable = scenario in {"no_available_uav_once", "no_available_uav"}
    fleet = [] if unavailable else [
        {"uav_id": "UAV-MED-001", "battery_percent": 92, "max_payload_kg": 5.0, "health": "ready", "current_lon": 114.052, "current_lat": 22.538},
        {"uav_id": "UAV-MED-002", "battery_percent": 81, "max_payload_kg": 3.0, "health": "ready", "current_lon": 114.060, "current_lat": 22.535},
        {"uav_id": "UAV-CARGO-003", "battery_percent": 76, "max_payload_kg": 8.0, "health": "standby", "current_lon": 114.041, "current_lat": 22.531},
    ]
    available = [uav for uav in fleet if uav["health"] in {"ready", "standby"} and uav["max_payload_kg"] >= cargo_weight]
    return {"available_uavs": available, "fleet_readiness": round(len(available) / max(len(fleet), 1), 3), "capacity_satisfied": bool(available), "fleet_size": len(fleet)}


def dock_status(input_data: Dict[str, Any]) -> Dict[str, Any]:
    busy = _scenario(input_data) == "dock_congested"
    return {"available_docks": [] if busy else ["DOCK-HOSP-A"], "charging_slots": 0 if busy else 2, "estimated_turnaround_mins": 18 if busy else 4, "battery_swap_available": not busy, "dock_queue_length": 5 if busy else 1}


def _decision_step(agent: str, action: str, reason: str, result: str) -> Dict[str, str]:
    return {"agent": agent, "action": action, "reason": reason, "result": result}


def compliance_route(input_data: Dict[str, Any], subtask_id: str) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    scenario = _scenario(input_data)
    airspace = _previous(input_data, "AIR_01")
    weather = _previous(input_data, "WEA_01")
    dock = _previous(input_data, "DOCK_01")
    uavs = _available_uavs(input_data, subtask_id)
    if not airspace.get("is_clear", False):
        return 409, "airspace restricted by temporary no-fly zone", {}
    if not weather.get("is_flyable", False):
        return 422, "weather unsafe for compliance UAV route", {}
    if not uavs:
        return 409, "no available UAV for compliance route", {}
    altitude = min(float(airspace.get("altitude_limit_m", 120)), 100.0)
    route_nodes = _build_route_nodes(mission, altitude, "drl_compliance")
    obstacles = _scene_obstacles(mission, scenario, airspace, weather, dock)
    distance = round(sum(_segment_distance_km(route_nodes[i], route_nodes[i + 1]) for i in range(len(route_nodes) - 1)), 3)
    wind = float(weather.get("wind_speed_mps", 0.0))
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    duration = round(distance / 58.0 * 60.0 + 2.0, 2)
    energy = round(distance * (23.0 + cargo * 3.2) * (1 + wind / 45), 2)
    eta, time_window_met = _window_result(mission, duration)
    output = {"algorithm": "DRL-LLM", "uav_id": uavs[0]["uav_id"], "waypoints_3d": _waypoints_from_nodes(route_nodes), "flight_distance_km": distance, "estimated_duration_mins": duration, "estimated_energy_kj": energy, "eta": eta, "time_window_met": time_window_met, "compliance_score": 0.97, "collision_risk": 0.05}
    output.update(_build_route_visualization(mission, route_nodes, duration, "uav", "DRL-LLM compliance route", uavs[0]["uav_id"], scenario, obstacles, [], [_decision_step("DecomposeAgent", "select", "空域、气象、无人机状态满足前置依赖", "进入合规航线规划"), _decision_step("ComplianceRouteService", "avoid_obstacle", "检测到建筑群与高压线约束", "生成绕飞与高度跨越航点"), _decision_step("PostprocessAgent", "score", "合规评分高、碰撞风险低", "进入候选方案池")]))
    return 200, "DRL-LLM compliance route generated with obstacle-aware waypoints", output


def weather_adaptive_dispatch(input_data: Dict[str, Any]) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    scenario = _scenario(input_data)
    airspace = _previous(input_data, "AIR_01")
    weather = _previous(input_data, "WEA_01")
    dock = _previous(input_data, "DOCK_01")
    available_uavs = _previous(input_data, "UAV_01").get("available_uavs", [])
    unsafe_air = airspace and not airspace.get("is_clear", True)
    unsafe_weather = not weather.get("is_flyable", False)
    ground_mode = unsafe_air or unsafe_weather or not available_uavs
    risk_tags = []
    if unsafe_air:
        risk_tags.append("temporary_airspace_restriction")
    if unsafe_weather:
        risk_tags.append("adverse_weather")
    profile = "ground_fallback" if ground_mode else "air_ground_coordination"
    route_nodes = _build_route_nodes(mission, 85.0, profile)
    obstacles = _scene_obstacles(mission, scenario, airspace, weather, dock)
    distance = round(sum(_segment_distance_km(route_nodes[i], route_nodes[i + 1]) for i in range(len(route_nodes) - 1)), 3)
    speed = 46.0 if ground_mode else 55.0
    delay = 6.0 if ground_mode else 2.0
    duration = round(distance / speed * 60.0 + delay, 2)
    energy = round(distance * (44.0 if ground_mode else 30.0), 2)
    eta, time_window_met = _window_result(mission, duration)
    vehicle_type = "ground_vehicle" if ground_mode else "air_ground_coordination"
    vehicle_id = available_uavs[0]["uav_id"] if available_uavs and not ground_mode else "GROUND-RESCUE-01"
    output = {"algorithm": "NN-AirGround", "assigned_vehicle_type": vehicle_type, "uav_id": vehicle_id, "adjusted_route": [node["id"] for node in route_nodes], "weather_delay_mins": delay, "flight_distance_km": distance, "estimated_duration_mins": duration, "estimated_energy_kj": energy, "eta": eta, "time_window_met": time_window_met, "compliance_score": 0.99 if ground_mode else 0.91}
    output.update(_build_route_visualization(mission, route_nodes, duration, vehicle_type, "NN weather-adaptive air-ground dispatch", vehicle_id, scenario, obstacles, risk_tags, [_decision_step("ReplanDecisionAgent", "fallback" if ground_mode else "parallel_candidate", "空域/气象/无人机约束触发备用策略" if ground_mode else "作为空地协同候选方案并行生成", "选择地面兜底路径" if ground_mode else "生成空地协同路径"), _decision_step("WeatherAdaptiveService", "avoid_risk_cell", "规避强天气/禁飞核心区", "切换道路安全接驳节点"), _decision_step("RiskAssessmentService", "authorize", "风险区不再被飞行路径穿越", "允许进入候选推荐")]))
    return 200, "weather-adaptive air-ground plan generated with fallback context", output


def medical_time_window_schedule(input_data: Dict[str, Any], subtask_id: str) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    scenario = _scenario(input_data)
    airspace = _previous(input_data, "AIR_01")
    weather = _previous(input_data, "WEA_01")
    dock = _previous(input_data, "DOCK_01")
    uavs = _available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for emergency medical mission", {}
    route_nodes = _build_route_nodes(mission, 90.0, "medical_time_window")
    obstacles = _scene_obstacles(mission, scenario, airspace, weather, dock)
    distance = round(sum(_segment_distance_km(route_nodes[i], route_nodes[i + 1]) for i in range(len(route_nodes) - 1)), 3)
    duration = round(distance / 65.0 * 60.0 + 1.5, 2)
    energy = round(distance * (21.0 + float(mission.get("cargo_weight_kg", 0.0)) * 2.8), 2)
    eta, time_window_met = _window_result(mission, duration)
    pickup, dropoff = _point_pair(mission)
    output = {"algorithm": "TWA-MILP", "uav_id": uavs[0]["uav_id"], "dispatch_sequence": [pickup.get("id", "pickup"), dropoff.get("id", "dropoff")], "waypoints_3d": _waypoints_from_nodes(route_nodes), "flight_distance_km": distance, "estimated_duration_mins": duration, "estimated_energy_kj": energy, "eta": eta, "time_window_met": time_window_met, "minimum_required_uavs": 1, "solver_status": "OPTIMAL", "compliance_score": 0.9}
    output.update(_build_route_visualization(mission, route_nodes, duration, "uav", "TWA-MILP medical time-window schedule", uavs[0]["uav_id"], scenario, obstacles, [], [_decision_step("DecomposeAgent", "insert_medical_scheduler", "任务类型为 emergency_medical", "加入医疗时间窗调度节点"), _decision_step("MedicalScheduler", "optimize_eta", "以截止期和载荷为主约束", "选择医疗优先走廊"), _decision_step("PostprocessAgent", "score", "预计到达时间满足时间窗", "进入候选方案池")]))
    return 200, "TWA-MILP optimal schedule generated with emergency corridor", output


def agentic_task_allocation(input_data: Dict[str, Any], subtask_id: str) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    scenario = _scenario(input_data)
    airspace = _previous(input_data, "AIR_01")
    weather = _previous(input_data, "WEA_01")
    dock = _previous(input_data, "DOCK_01")
    uavs = _available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for CoordField allocation", {}
    pickup, dropoff = _point_pair(mission)
    route_nodes = _build_route_nodes(mission, 78.0, "coordfield_allocation")
    obstacles = _scene_obstacles(mission, scenario, airspace, weather, dock)
    distance = round(sum(_segment_distance_km(route_nodes[i], route_nodes[i + 1]) for i in range(len(route_nodes) - 1)), 3)
    response_time = round(distance / 55.0 * 60.0 + 2.5, 2)
    energy = round(distance * 28.0, 2)
    eta, time_window_met = _window_result(mission, response_time)
    output = {"algorithm": "CoordField", "uav_id": uavs[0]["uav_id"], "assignments": [{"uav_id": uavs[0]["uav_id"], "task": f"{pickup.get('id')}->{dropoff.get('id')}", "allocation_score": 0.93}], "task_coverage_rate": 1.0, "response_time_mins": response_time, "estimated_duration_mins": response_time, "estimated_energy_kj": energy, "eta": eta, "time_window_met": time_window_met, "reallocation_count": 1 if scenario != "normal" else 0, "compliance_score": 0.88}
    output.update(_build_route_visualization(mission, route_nodes, response_time, "uav", "CoordField agentic task allocation", uavs[0]["uav_id"], scenario, obstacles, [], [_decision_step("AgenticAllocationService", "allocate", "根据载荷、位置、电量和任务覆盖率分配 UAV", f"选择 {uavs[0]['uav_id']}"), _decision_step("AgenticAllocationService", "reserve_reallocation", "保留动态重分配余量", "生成中继点和末端接近航点")]))
    return 200, "CoordField allocation generated with allocation corridor", output


def risk_assessment(input_data: Dict[str, Any]) -> Dict[str, Any]:
    previous = input_data.get("previous_results", {})
    airspace = previous.get("AIR_01", {})
    weather = previous.get("WEA_01", {})
    route_candidates = {task_id: output for task_id, output in previous.items() if task_id.startswith("ROUTE_") and output}
    risk_factors = []
    if not airspace.get("is_clear", True):
        risk_factors.append("temporary_airspace_restriction")
    if not weather.get("is_flyable", True):
        risk_factors.append("adverse_weather")
    feasible = {task_id: output for task_id, output in route_candidates.items() if output.get("time_window_met", True)}
    if risk_factors:
        ground_candidates = {task_id: output for task_id, output in feasible.items() if output.get("assigned_vehicle_type") == "ground_vehicle"}
        feasible = ground_candidates

    def score(item: Tuple[str, Dict[str, Any]]) -> float:
        output = item[1]
        conflict_penalty = sum(1 for check in output.get("route_conflict_checks", []) if check.get("status") in {"blocked", "unsafe"}) * 25
        return float(output.get("compliance_score", 0.85)) * 50 - float(output.get("estimated_duration_mins", 60)) * 0.4 - float(output.get("estimated_energy_kj", 1000)) * 0.005 - conflict_penalty

    recommended = max(feasible.items(), key=score)[0] if feasible else ""
    risk_score = min(1.0, 0.12 + (0.35 if "temporary_airspace_restriction" in risk_factors else 0) + (0.32 if "adverse_weather" in risk_factors else 0))
    risk_level = "HIGH" if risk_score >= 0.7 else "MEDIUM" if risk_score >= 0.4 else "LOW"
    candidate_scores = {task_id: round(score((task_id, output)), 3) for task_id, output in route_candidates.items()}
    return {"risk_level": risk_level, "risk_score": round(risk_score, 3), "dispatch_allowed": bool(recommended), "recommended_subtask_id": recommended, "risk_factors": risk_factors, "evaluated_candidates": list(route_candidates), "candidate_scores": candidate_scores, "airspace_snapshot": airspace, "weather_snapshot": weather, "decision_basis": ["过滤不满足时间窗的候选方案", "若存在禁飞/恶劣天气，优先选择不穿越风险区的 ground_vehicle 兜底方案", "综合合规评分、预计耗时、能耗和冲突检查惩罚进行推荐"]}


def dispatch_report(input_data: Dict[str, Any]) -> Dict[str, Any]:
    risk = _previous(input_data, "RISK_01")
    allowed = bool(risk.get("dispatch_allowed", False))
    return {"mission_status": "READY_FOR_DISPATCH" if allowed else "BLOCKED", "dispatch_brief": f"推荐方案 {risk.get('recommended_subtask_id')}，综合风险等级 {risk.get('risk_level', 'UNKNOWN')}。", "command_actions": ["锁定任务载荷并复核交接单", "向空域与地面保障单位同步执行窗口", "按推荐方案派发并持续监测气象变化"] if allowed else ["保持任务待命", "请求人工复核风险与资源状态"]}


def execute_tool(tool_name: str, input_data: Dict[str, Any], parameters: Dict[str, Any], subtask_id: str) -> Tuple[int, str, Dict[str, Any]]:
    if tool_name == "airspace_check_service":
        return 200, "airspace check completed", airspace_check(input_data)
    if tool_name == "weather_check_service":
        return 200, "weather check completed", weather_check(input_data)
    if tool_name == "uav_status_service":
        return 200, "UAV status check completed", uav_status(input_data)
    if tool_name == "dock_status_service":
        return 200, "dock status check completed", dock_status(input_data)
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
    if tool_name == "dispatch_report_service":
        return 200, "dispatch report completed", dispatch_report(input_data)
    return 404, f"unsupported tool: {tool_name}", {}
