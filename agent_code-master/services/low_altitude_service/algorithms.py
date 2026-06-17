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


def _waypoints(mission: Dict[str, Any], altitude_m: float) -> List[List[float]]:
    pickup, dropoff = _point_pair(mission)
    start_lon = float(pickup.get("lon", 0.0))
    start_lat = float(pickup.get("lat", 0.0))
    end_lon = float(dropoff.get("lon", 0.0))
    end_lat = float(dropoff.get("lat", 0.0))
    return [
        [start_lon, start_lat, altitude_m],
        [
            round((start_lon + end_lon) / 2 + 0.005, 6),
            round((start_lat + end_lat) / 2 - 0.004, 6),
            altitude_m,
        ],
        [end_lon, end_lat, altitude_m],
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
    return {
        "is_clear": not restricted,
        "no_fly_zones": [
            {
                "zone_id": "NFZ-TEMP-01",
                "reason": "temporary emergency control",
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
        },
        {
            "uav_id": "UAV-MED-002",
            "battery_percent": 81,
            "max_payload_kg": 3.0,
            "health": "ready",
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

    distance = _distance(mission, 1.06)
    wind = float(weather.get("wind_speed_mps", 0.0))
    cargo = float(mission.get("cargo_weight_kg", 0.0))
    duration = round(distance / 58.0 * 60.0 + 2.0, 2)
    energy = round(distance * (23.0 + cargo * 3.2) * (1 + wind / 45), 2)
    eta, time_window_met = _window_result(mission, duration)
    return 200, "DRL-LLM compliance route generated", {
        "algorithm": "DRL-LLM",
        "uav_id": uavs[0]["uav_id"],
        "waypoints_3d": _waypoints(
            mission, min(float(airspace.get("altitude_limit_m", 120)), 100.0)
        ),
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "compliance_score": 0.97,
        "collision_risk": 0.03,
    }


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
    distance = _distance(mission, 1.24 if ground_mode else 1.1)
    speed = 50.0 if ground_mode else 55.0
    delay = 5.0 if ground_mode else 2.0
    duration = round(distance / speed * 60.0 + delay, 2)
    energy = round(distance * (44.0 if ground_mode else 30.0), 2)
    eta, time_window_met = _window_result(mission, duration)
    pickup, dropoff = _point_pair(mission)
    return 200, "weather-adaptive air-ground plan generated", {
        "algorithm": "NN-AirGround",
        "assigned_vehicle_type": "ground_vehicle"
        if ground_mode
        else "air_ground_coordination",
        "adjusted_route": [
            pickup.get("id", "pickup"),
            "SAFE_TRANSFER_NODE",
            dropoff.get("id", "dropoff"),
        ],
        "weather_delay_mins": delay,
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "compliance_score": 0.99 if ground_mode else 0.91,
    }


def medical_time_window_schedule(
    input_data: Dict[str, Any], subtask_id: str
) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    uavs = _available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for emergency medical mission", {}

    distance = _distance(mission, 1.03)
    duration = round(distance / 65.0 * 60.0 + 1.5, 2)
    energy = round(
        distance * (21.0 + float(mission.get("cargo_weight_kg", 0.0)) * 2.8),
        2,
    )
    eta, time_window_met = _window_result(mission, duration)
    pickup, dropoff = _point_pair(mission)
    return 200, "TWA-MILP optimal schedule generated", {
        "algorithm": "TWA-MILP",
        "uav_id": uavs[0]["uav_id"],
        "dispatch_sequence": [
            pickup.get("id", "pickup"),
            dropoff.get("id", "dropoff"),
        ],
        "flight_distance_km": distance,
        "estimated_duration_mins": duration,
        "estimated_energy_kj": energy,
        "eta": eta,
        "time_window_met": time_window_met,
        "minimum_required_uavs": 1,
        "solver_status": "OPTIMAL",
        "compliance_score": 0.9,
    }


def agentic_task_allocation(
    input_data: Dict[str, Any], subtask_id: str
) -> Tuple[int, str, Dict[str, Any]]:
    mission = _mission(input_data)
    uavs = _available_uavs(input_data, subtask_id)
    if not uavs:
        return 409, "no available UAV for CoordField allocation", {}

    pickup, dropoff = _point_pair(mission)
    distance = _distance(mission, 1.08)
    response_time = round(distance / 55.0 * 60.0 + 2.5, 2)
    energy = round(distance * 28.0, 2)
    eta, time_window_met = _window_result(mission, response_time)
    return 200, "CoordField allocation generated", {
        "algorithm": "CoordField",
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
