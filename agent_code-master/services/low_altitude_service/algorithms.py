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
    }


def _safe_transfer_node(
    pickup: Dict[str, Any],
    dropoff: Dict[str, Any],
    altitude_m: float,
) -> Dict[str, Any]:
    return {
        "id": "SAFE_TRANSFER_NODE",
        "name": "安全接驳点",
        "lon": round(
            (float(pickup.get("lon", 0.0)) + float(dropoff.get("lon", 0.0))) / 2
            + 0.015,
            6,
        ),
        "lat": round(
            (float(pickup.get("lat", 0.0)) + float(dropoff.get("lat", 0.0))) / 2
            - 0.010,
            6,
        ),
        "altitude_m": round(float(altitude_m), 1),
        "type": "transfer",
    }


def _waypoint_nodes(
    mission: Dict[str, Any],
    altitude_m: float,
    lateral_offset_lon: float = 0.005,
    lateral_offset_lat: float = -0.004,
) -> List[Dict[str, Any]]:
    pickup, dropoff = _point_pair(mission)
    start = _point_node(pickup, altitude_m, "pickup", "pickup")
    end = _point_node(dropoff, altitude_m, "dropoff", "dropoff")
    mid = {
        "id": "WP_MID",
        "name": "低空航路转向点",
        "lon": round((start["lon"] + end["lon"]) / 2 + lateral_offset_lon, 6),
        "lat": round((start["lat"] + end["lat"]) / 2 + lateral_offset_lat, 6),
        "altitude_m": round(float(altitude_m), 1),
        "type": "waypoint",
    }
    return [start, mid, end]


def _waypoints(mission: Dict[str, Any], altitude_m: float) -> List[List[float]]:
    return [
        [node["lon"], node["lat"], node["altitude_m"]]
        for node in _waypoint_nodes(mission, altitude_m)
    ]


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


def _geo_bounds(nodes: List[Dict[str, Any]]) -> Dict[str, float]:
    if not nodes:
        return {"min_lon": 0, "max_lon": 0, "min_lat": 0, "max_lat": 0}
    lons = [float(node["lon"]) for node in nodes]
    lats = [float(node["lat"]) for node in nodes]
    lon_pad = max((max(lons) - min(lons)) * 0.18, 0.01)
    lat_pad = max((max(lats) - min(lats)) * 0.18, 0.01)
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
        return {
            "lon": node["lon"],
            "lat": node["lat"],
            "altitude_m": node["altitude_m"],
        }, 0

    distances = [
        max(_segment_distance_km(nodes[i], nodes[i + 1]), 0.0001)
        for i in range(len(nodes) - 1)
    ]
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
                "altitude_m": round(
                    a["altitude_m"]
                    + (b["altitude_m"] - a["altitude_m"]) * ratio,
                    1,
                ),
            }, idx
        travelled += segment_distance
    node = nodes[-1]
    return {
        "lon": node["lon"],
        "lat": node["lat"],
        "altitude_m": node["altitude_m"],
    }, len(nodes) - 2


def _build_route_visualization(
    mission: Dict[str, Any],
    route_nodes: List[Dict[str, Any]],
    duration_mins: float,
    vehicle_type: str,
    algorithm: str,
    uav_id: str = "",
    scenario: str = "normal",
    risk_tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    risk_tags = risk_tags or []
    total_distance = round(
        sum(
            _segment_distance_km(route_nodes[i], route_nodes[i + 1])
            for i in range(max(len(route_nodes) - 1, 0))
        ),
        3,
    )
    route_segments = []
    for idx in range(max(len(route_nodes) - 1, 0)):
        start = route_nodes[idx]
        end = route_nodes[idx + 1]
        segment_distance = round(_segment_distance_km(start, end), 3)
        route_segments.append(
            {
                "segment_id": f"SEG_{idx + 1:02d}",
                "from": start["id"],
                "to": end["id"],
                "mode": "ground" if vehicle_type == "ground_vehicle" else "low_altitude_uav",
                "distance_km": segment_distance,
                "planned_altitude_m": start.get("altitude_m", 0.0),
            }
        )

    telemetry_stream: List[Dict[str, Any]] = []
    steps = 36
    base_battery = 92.0
    battery_drop = 5.0 + total_distance * (0.8 if vehicle_type != "ground_vehicle" else 0.25)
    for step in range(steps + 1):
        progress = step / steps
        point, segment_idx = _interpolate_route(route_nodes, progress)
        elapsed = round(duration_mins * progress, 2)
        if progress < 0.08:
            phase = "takeoff" if vehicle_type != "ground_vehicle" else "departing"
        elif progress > 0.92:
            phase = "landing" if vehicle_type != "ground_vehicle" else "arriving"
        else:
            phase = "cruise" if vehicle_type != "ground_vehicle" else "ground_transfer"
        telemetry_stream.append(
            {
                "t_seconds": round(elapsed * 60, 1),
                "elapsed_mins": elapsed,
                "progress": round(progress, 3),
                "lon": point["lon"],
                "lat": point["lat"],
                "altitude_m": point["altitude_m"],
                "speed_kmh": 0
                if step in {0, steps}
                else (48 if vehicle_type == "ground_vehicle" else 58),
                "battery_percent": round(base_battery - battery_drop * progress, 1),
                "segment_id": route_segments[segment_idx]["segment_id"]
                if route_segments
                else "SEG_00",
                "phase": phase,
                "vehicle_type": vehicle_type,
                "uav_id": uav_id or "GROUND-RESCUE-01",
            }
        )

    return {
        "operational_mode": vehicle_type,
        "algorithm_trace_name": algorithm,
        "route_polyline_geo": route_nodes,
        "route_segments": route_segments,
        "geo_bounds": _geo_bounds(route_nodes),
        "telemetry_stream": telemetry_stream,
        "live_state": telemetry_stream[0] if telemetry_stream else {},
        "visual_overlays": {
            "scenario": scenario,
            "risk_tags": risk_tags,
            "show_no_fly_zone": "temporary_airspace_restriction" in risk_tags,
            "show_weather_cell": "adverse_weather" in risk_tags,
        },
    }


def _recovered_uav() -> Dict[str, Any]:
    return {
        "uav_id": "UAV-MED-RECOVERED",
        "battery_percent": 88,
        "max_payload_kg": 5.0,
        "health": "ready",
    }


def _available_uavs(
    input_data: Dict[str, Any], subtask_id: str
) -> List[Dict[str, Any]]:
    available = list(_previous(input_data, "UAV_01").get("available_uavs", []))
    retry_count = int(
        input_data.get("metadata", {}).get(f"retry_{subtask_id}", 0)
    )
    if (
        not available
        and _scenario(input_data) == "no_available_uav_once"
        and retry_count >= 1
    ):
        return [_recovered_uav()]
    return available


def airspace_check(input_data: Dict[str, Any]) -> Dict[str, Any]:
    mission = _mission(input_data)
    constraints = mission.get("environmental_constraints", {})
    restricted = _scenario(input_data) == "airspace_restricted" or bool(
        constraints.get("restricted_airspace", False)
    )
    pickup, dropoff = _point_pair(mission)
    return {
        "is_clear": not restricted,
        "no_fly_zones": [
            {
                "zone_id": "NFZ-TEMP-01",
                "reason": "temporary emergency control",
                "center_lon": round(
                    (float(pickup.get("lon", 0.0)) + float(dropoff.get("lon", 0.0))) / 2,
                    6,
                ),
                "center_lat": round(
                    (float(pickup.get("lat", 0.0)) + float(dropoff.get("lat", 0.0))) / 2,
                    6,
                ),
                "radius_km": 2.8,
            }
        ]
        if restricted
        else [],
        "altitude_limit_m": float(
            constraints.get("maximum_altitude_m", 120.0)
        ),
        "compliance_rules_checked": 8,
    }


def weather_check(input_data: Dict[str, Any]) -> Dict[str, Any]:
    mission = _mission(input_data)
    constraints = mission.get("environmental_constraints", {})
    bad_weather = _scenario(input_data) == "bad_weather"
    wind = 13.5 if bad_weather else 4.5
    precipitation = 7.2 if bad_weather else 0.2
    visibility = 1.2 if bad_weather else 9.0
    max_wind = float(constraints.get("max_wind_speed_mps", 10.0))
    max_rain = float(constraints.get("max_precipitation_mm_h", 5.0))
    min_visibility = float(constraints.get("minimum_visibility_km", 2.0))
    pickup, dropoff = _point_pair(mission)
    return {
        "wind_speed_mps": wind,
        "precipitation_mm_h": precipitation,
        "visibility_km": visibility,
        "is_flyable": (
            wind <= max_wind
            and precipitation <= max_rain
            and visibility >= min_visibility
        ),
        "weather_window_mins": 45 if not bad_weather else 0,
        "weather_cell": {
            "center_lon": round(
                (float(pickup.get("lon", 0.0)) + float(dropoff.get("lon", 0.0))) / 2
                + 0.01,
                6,
            ),
            "center_lat": round(
                (float(pickup.get("lat", 0.0)) + float(dropoff.get("lat", 0.0))) / 2
                + 0.008,
                6,
            ),
            "radius_km": 3.5,
            "level": "convective_rain" if bad_weather else "normal",
        },
    }


def uav_status(input_data: Dict[str, Any]) -> Dict[str, Any]:
    mission = _mission(input_data)
    cargo_weight = float(mission.get("cargo_weight_kg", 0.0))
    unavailable = _scenario(input_data) in {
        "no_available_uav_once",
        "no_available_uav",
    }
    fleet = [] if unavailable else [
        {
            "uav_id": "UAV-MED-001",
            "battery_percent": 92,
            "max_payload_kg": 5.0,
            "health": "ready",
            "current_lon": 114.052,
            "current_lat": 22.538,
        },
        {
            "uav_id": "UAV-MED-002",
            "battery_percent": 81,
            "max_payload_kg": 3.0,
            "health": "ready",
            "current_lon": 114.060,
            "current_lat": 22.535,
        },
    ]
    available = [
        uav
        for uav in fleet
        if uav["health"] == "ready"
        and uav["max_payload_kg"] >= cargo_weight
    ]
    return {
        "available_uavs": available,
        "fleet_readiness": round(len(available) / max(len(fleet), 1), 3),
        "capacity_satisfied": bool(available),
    }


def dock_status(input_data: Dict[str, Any]) -> Dict[str, Any]:
    busy = _scenario(input_data) == "dock_congested"
    return {
        "available_docks": [] if busy else ["DOCK-HOSP-A"],
        "charging_slots": 0 if busy else 2,
        "estimated_turnaround_mins": 18 if busy else 4,
        "battery_swap_available": not busy,
    }


def compliance_route(
    input_data: Dict[str, Any], subtask_id: str
) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    airspace = _previous(input_data, "AIR_01")
    weather = _previous(input_data, "WEA_01")
    uavs = _available_uavs(input_data, subtask_id)
    if not airspace.get("is_clear", False):
        return 409, "airspace restricted by temporary no-fly zone", {}
    if not weather.get("is_flyable", False):
        return 422, "weather unsafe for compliance UAV route", {}
    if not uavs:
        return 409, "no available UAV for compliance route", {}

    altitude = min(float(airspace.get("altitude_limit_m", 120)), 100.0)
    route_nodes = _waypoint_nodes(mission, altitude)
    distance = _distance(mission, 1.06)
    wind = float(weather.get("wind_speed_mps", 0.0))
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    duration = round(distance / 58.0 * 60.0 + 2.0, 2)
    energy = round(distance * (23.0 + cargo * 3.2) * (1 + wind / 45), 2)
    eta, time_window_met = _window_result(mission, duration)
    output = {
        "algorithm": "DRL-LLM",
        "uav_id": uavs[0]["uav_id"],
        "waypoints_3d": [[n["lon"], n["lat"], n["altitude_m"]] for n in route_nodes],
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "compliance_score": 0.97,
        "collision_risk": 0.03,
    }
    output.update(
        _build_route_visualization(
            mission=mission,
            route_nodes=route_nodes,
            duration_mins=duration,
            vehicle_type="uav",
            algorithm="DRL-LLM compliance route",
            uav_id=uavs[0]["uav_id"],
            scenario=_scenario(input_data),
        )
    )
    return 200, "DRL-LLM compliance route generated", output


def weather_adaptive_dispatch(
    input_data: Dict[str, Any]
) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    airspace = _previous(input_data, "AIR_01")
    weather = _previous(input_data, "WEA_01")
    available_uavs = _previous(input_data, "UAV_01").get(
        "available_uavs", []
    )
    unsafe_air = airspace and not airspace.get("is_clear", True)
    unsafe_weather = not weather.get("is_flyable", False)
    ground_mode = unsafe_air or unsafe_weather or not available_uavs
    risk_tags = []
    if unsafe_air:
        risk_tags.append("temporary_airspace_restriction")
    if unsafe_weather:
        risk_tags.append("adverse_weather")

    pickup, dropoff = _point_pair(mission)
    altitude = 0.0 if ground_mode else 85.0
    route_nodes = [
        _point_node(pickup, altitude, "pickup", "pickup"),
        _safe_transfer_node(pickup, dropoff, altitude),
        _point_node(dropoff, altitude, "dropoff", "dropoff"),
    ]
    distance = _distance(mission, 1.24 if ground_mode else 1.1)
    speed = 50.0 if ground_mode else 55.0
    delay = 5.0 if ground_mode else 2.0
    duration = round(distance / speed * 60.0 + delay, 2)
    energy = round(distance * (44.0 if ground_mode else 30.0), 2)
    eta, time_window_met = _window_result(mission, duration)
    vehicle_type = "ground_vehicle" if ground_mode else "air_ground_coordination"
    output = {
        "algorithm": "NN-AirGround",
        "assigned_vehicle_type": vehicle_type,
        "uav_id": available_uavs[0]["uav_id"] if available_uavs and not ground_mode else "GROUND-RESCUE-01",
        "adjusted_route": [node["id"] for node in route_nodes],
        "weather_delay_mins": delay,
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "compliance_score": 0.99 if ground_mode else 0.91,
    }
    output.update(
        _build_route_visualization(
            mission=mission,
            route_nodes=route_nodes,
            duration_mins=duration,
            vehicle_type=vehicle_type,
            algorithm="NN weather-adaptive air-ground dispatch",
            uav_id=output["uav_id"],
            scenario=_scenario(input_data),
            risk_tags=risk_tags,
        )
    )
    return 200, "weather-adaptive air-ground plan generated", output


def medical_time_window_schedule(
    input_data: Dict[str, Any], subtask_id: str
) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    uavs = _available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for emergency medical mission", {}

    route_nodes = _waypoint_nodes(
        mission,
        altitude_m=90.0,
        lateral_offset_lon=-0.004,
        lateral_offset_lat=0.006,
    )
    distance = _distance(mission, 1.03)
    duration = round(distance / 65.0 * 60.0 + 1.5, 2)
    energy = round(
        distance * (21.0 + float(mission.get("cargo_weight_kg", 0.0)) * 2.8),
        2,
    )
    eta, time_window_met = _window_result(mission, duration)
    pickup, dropoff = _point_pair(mission)
    output = {
        "algorithm": "TWA-MILP",
        "uav_id": uavs[0]["uav_id"],
        "dispatch_sequence": [
            pickup.get("id", "pickup"),
            dropoff.get("id", "dropoff"),
        ],
        "waypoints_3d": [[n["lon"], n["lat"], n["altitude_m"]] for n in route_nodes],
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "minimum_required_uavs": 1,
        "solver_status": "OPTIMAL",
        "compliance_score": 0.9,
    }
    output.update(
        _build_route_visualization(
            mission=mission,
            route_nodes=route_nodes,
            duration_mins=duration,
            vehicle_type="uav",
            algorithm="TWA-MILP medical time-window schedule",
            uav_id=uavs[0]["uav_id"],
            scenario=_scenario(input_data),
        )
    )
    return 200, "TWA-MILP optimal schedule generated", output


def agentic_task_allocation(
    input_data: Dict[str, Any], subtask_id: str
) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    uavs = _available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for CoordField allocation", {}

    pickup, dropoff = _point_pair(mission)
    route_nodes = _waypoint_nodes(
        mission,
        altitude_m=78.0,
        lateral_offset_lon=0.012,
        lateral_offset_lat=0.004,
    )
    distance = _distance(mission, 1.08)
    response_time = round(distance / 55.0 * 60.0 + 2.5, 2)
    energy = round(distance * 28.0, 2)
    eta, time_window_met = _window_result(mission, response_time)
    output = {
        "algorithm": "CoordField",
        "uav_id": uavs[0]["uav_id"],
        "assignments": [
            {
                "uav_id": uavs[0]["uav_id"],
                "task": f"{pickup.get('id')}->{dropoff.get('id')}",
                "allocation_score": 0.93,
            }
        ],
        "task_coverage_rate": 1.0,
        "response_time_mins": response_time,
        "estimated_duration_mins": response_time,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "reallocation_count": 1
        if _scenario(input_data) != "normal"
        else 0,
        "compliance_score": 0.88,
    }
    output.update(
        _build_route_visualization(
            mission=mission,
            route_nodes=route_nodes,
            duration_mins=response_time,
            vehicle_type="uav",
            algorithm="CoordField agentic task allocation",
            uav_id=uavs[0]["uav_id"],
            scenario=_scenario(input_data),
        )
    )
    return 200, "CoordField allocation generated", output


def risk_assessment(input_data: Dict[str, Any]) -> Dict[str, Any]:
    previous = input_data.get("previous_results", {})
    airspace = previous.get("AIR_01", {})
    weather = previous.get("WEA_01", {})
    route_candidates = {
        task_id: output
        for task_id, output in previous.items()
        if task_id.startswith("ROUTE_") and output
    }
    risk_factors = []
    if not airspace.get("is_clear", True):
        risk_factors.append("temporary_airspace_restriction")
    if not weather.get("is_flyable", True):
        risk_factors.append("adverse_weather")

    feasible = {
        task_id: output
        for task_id, output in route_candidates.items()
        if output.get("time_window_met", True)
    }
    if risk_factors:
        ground_candidates = {
            task_id: output
            for task_id, output in feasible.items()
            if output.get("assigned_vehicle_type") == "ground_vehicle"
        }
        feasible = ground_candidates

    def score(item: Tuple[str, Dict[str, Any]]) -> float:
        output = item[1]
        return (
            float(output.get("compliance_score", 0.85)) * 50
            - float(output.get("estimated_duration_mins", 60)) * 0.4
            - float(output.get("estimated_energy_kj", 1000)) * 0.005
        )

    recommended = max(feasible.items(), key=score)[0] if feasible else ""
    risk_score = min(
        1.0,
        0.12
        + (0.35 if "temporary_airspace_restriction" in risk_factors else 0)
        + (0.32 if "adverse_weather" in risk_factors else 0),
    )
    risk_level = "HIGH" if risk_score >= 0.7 else "MEDIUM" if risk_score >= 0.4 else "LOW"
    return {
        "risk_level": risk_level,
        "risk_score": round(risk_score, 3),
        "dispatch_allowed": bool(recommended),
        "recommended_subtask_id": recommended,
        "risk_factors": risk_factors,
        "evaluated_candidates": list(route_candidates),
        "airspace_snapshot": airspace,
        "weather_snapshot": weather,
    }


def dispatch_report(input_data: Dict[str, Any]) -> Dict[str, Any]:
    risk = _previous(input_data, "RISK_01")
    allowed = bool(risk.get("dispatch_allowed", False))
    return {
        "mission_status": "READY_FOR_DISPATCH" if allowed else "BLOCKED",
        "dispatch_brief": (
            f"推荐方案 {risk.get('recommended_subtask_id')}，"
            f"综合风险等级 {risk.get('risk_level', 'UNKNOWN')}。"
        ),
        "command_actions": [
            "锁定任务载荷并复核交接单",
            "向空域与地面保障单位同步执行窗口",
            "按推荐方案派发并持续监测气象变化",
        ]
        if allowed
        else ["保持任务待命", "请求人工复核风险与资源状态"],
    }


def execute_tool(
    tool_name: str,
    input_data: Dict[str, Any],
    parameters: Dict[str, Any],
    subtask_id: str,
) -> Tuple[int, str, Dict[str, Any]]:
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
