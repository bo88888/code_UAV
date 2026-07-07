from __future__ import annotations

import threading
from typing import Any, Dict, List

from services.low_altitude_service import algorithms as base
from services.low_altitude_service import enhanced_algorithms

_PATCH_LOCK = threading.Lock()
_ROUTE_TOOLS = {
    "compliance_route_service",
    "weather_adaptive_dispatch_service",
    "medical_time_window_scheduler_service",
    "agentic_task_allocation_service",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _kind(raw: str) -> str:
    mapping = {
        "building": "building_cluster",
        "building_cluster": "building_cluster",
        "powerline": "linear_obstacle",
        "line": "linear_obstacle",
        "linear_obstacle": "linear_obstacle",
        "sensitive": "sensitive_area",
        "school": "sensitive_area",
        "sensitive_area": "sensitive_area",
        "restricted": "restricted_zone",
        "restricted_zone": "restricted_zone",
        "weather": "weather_cell",
        "weather_cell": "weather_cell",
    }
    return mapping.get(str(raw or "").strip(), "restricted_zone")


def _to_base_kind(kind: str) -> str:
    return "no_fly_zone" if kind == "restricted_zone" else kind


def _custom_obstacles(input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    env = input_data.get("environmental_constraints") or {}
    mission = input_data.get("mission") or input_data.get("xml_config") or {}
    raw_items = (
        env.get("custom_obstacles")
        or env.get("dynamic_obstacles")
        or input_data.get("custom_obstacles")
        or mission.get("custom_obstacles")
        or []
    )
    if not isinstance(raw_items, list):
        return []

    out: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict):
            continue
        ui_kind = _kind(raw.get("kind") or raw.get("type") or raw.get("obstacle_type"))
        lon = raw.get("center_lon", raw.get("lon"))
        lat = raw.get("center_lat", raw.get("lat"))
        if lon is None or lat is None:
            continue
        radius = max(0.15, _f(raw.get("radius_km", raw.get("radius", 0.9)), 0.9))
        item: Dict[str, Any] = {
            "id": raw.get("id") or f"USER_OBS_{idx:03d}",
            "name": raw.get("name") or "前端实时放置障碍",
            "kind": _to_base_kind(ui_kind),
            "frontend_kind": ui_kind,
            "center_lon": _f(lon),
            "center_lat": _f(lat),
            "radius_km": radius,
            "severity": raw.get("severity") or ("high" if ui_kind == "restricted_zone" else "medium"),
            "source": "frontend_dynamic_obstacle",
            "avoidance_rule": raw.get("avoidance_rule") or _rule(ui_kind),
        }
        if ui_kind == "building_cluster":
            item["height_m"] = int(_f(raw.get("height_m", 128), 128))
        elif ui_kind == "linear_obstacle":
            item["height_m"] = int(_f(raw.get("height_m", 82), 82))
            item["polyline_geo"] = raw.get("polyline_geo") or [
                {"lon": round(item["center_lon"] - radius * 0.006, 7), "lat": round(item["center_lat"] - radius * 0.002, 7)},
                {"lon": round(item["center_lon"] + radius * 0.006, 7), "lat": round(item["center_lat"] + radius * 0.002, 7)},
            ]
        out.append(item)
    return out


def _rule(kind: str) -> str:
    return {
        "building_cluster": "建筑体进入局部代价地图，路径侧向绕行。",
        "linear_obstacle": "线性障碍进入低高度层代价地图，路径抬升或绕行。",
        "sensitive_area": "敏感区进入高代价地图，路径沿边界外侧绕行。",
        "restricted_zone": "受限区域进入硬约束地图，路径重新搜索。",
        "weather_cell": "天气单元进入风险代价地图，路径降低穿越优先级。",
    }.get(kind, "障碍进入局部重规划地图。")


def execute_tool(tool_name: str, input_data: Dict[str, Any], parameters: Dict[str, Any], subtask_id: str):
    user_obs = _custom_obstacles(input_data)
    if not user_obs or tool_name not in _ROUTE_TOOLS:
        code, message, data = enhanced_algorithms.execute_tool(tool_name, input_data, parameters, subtask_id)
        if isinstance(data, dict):
            data.setdefault("telemetry_source", "LIVE_SIMULATION")
            data.setdefault("live_control_mode", "simulated_realtime_playback")
        return code, message, data

    original = base._scene_obstacles

    def patched_scene(mission, scenario, airspace, weather, dock):
        scene = list(original(mission, scenario, airspace, weather, dock))
        ids = {x.get("id") for x in scene}
        for obs in user_obs:
            if obs.get("id") not in ids:
                scene.append(dict(obs))
        return scene

    with _PATCH_LOCK:
        base._scene_obstacles = patched_scene
        try:
            code, message, data = enhanced_algorithms.execute_tool(tool_name, input_data, parameters, subtask_id)
        finally:
            base._scene_obstacles = original

    if isinstance(data, dict):
        data["telemetry_source"] = "LIVE_SIMULATION"
        data["live_control_mode"] = "frontend_dynamic_obstacle_replanning"
        data["dynamic_obstacles"] = user_obs
        data["dynamic_obstacle_count"] = len(user_obs)
        data["replanning_trigger"] = "frontend_obstacle_update"
        data["replanning_explanation"] = f"前端实时放置 {len(user_obs)} 个障碍，已并入 A* 局部代价地图并重新生成航路。"
    return code, message, data
