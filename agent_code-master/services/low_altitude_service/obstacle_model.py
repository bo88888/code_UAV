"""Obstacle modeling helpers for visual explainability."""
from __future__ import annotations

from typing import Any, Dict, List


def enrich_obstacles(obstacles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for obs in obstacles:
        item = dict(obs)
        kind = item.get("kind")
        item["display_type"] = _display_type(kind)
        item["display_color"] = _display_color(kind)
        item["avoidance_mode"] = _avoidance_mode(kind)
        item["is_hard_constraint"] = kind == "no_fly_zone"
        item["is_soft_cost"] = kind in {"building_cluster", "linear_obstacle", "sensitive_area", "weather_cell", "resource_bottleneck"}
        if kind == "building_cluster":
            item["geometry_3d"] = "extruded_building_block"
            item["height_layer_m"] = item.get("height_m", 118)
        elif kind == "linear_obstacle":
            item["geometry_3d"] = "powerline_corridor"
            item["crossing_min_altitude_m"] = max(96, int(item.get("height_m", 80)) + 16)
        elif kind == "sensitive_area":
            item["geometry_3d"] = "sensitive_population_zone"
            item["preferred_buffer_km"] = round(float(item.get("radius_km", 1.0)) + 0.35, 2)
        elif kind == "no_fly_zone":
            item["geometry_3d"] = "cylindrical_restricted_volume"
        enriched.append(item)
    return enriched


def avoidance_explanations(obstacles: List[Dict[str, Any]], planner_trace: Dict[str, Any]) -> List[str]:
    messages: List[str] = []
    by_id = {obs.get("id"): obs for obs in obstacles}
    if "OBS_BUILDING_CLUSTER" in by_id:
        obs = by_id["OBS_BUILDING_CLUSTER"]
        messages.append(f"绕开 {obs.get('id')} 高层建筑群：建筑体转为软代价网格，A* 优先选择侧向绕飞，避免贴近 {obs.get('height_m', 118)}m 建筑。")
    if "OBS_POWERLINE" in by_id:
        obs = by_id["OBS_POWERLINE"]
        messages.append(f"处理 {obs.get('id')} 高压线走廊：线性障碍要求跨越高度不低于 {max(96, int(obs.get('height_m', 80)) + 16)}m，路径在跨越段抬升或绕行。")
    if "OBS_SCHOOL_ZONE" in by_id:
        messages.append("避开 OBS_SCHOOL_ZONE 人口密集敏感区：将学校/人群区域作为高代价软约束，优先沿边界外侧安全走廊通过。")
    for obs in obstacles:
        if obs.get("kind") == "no_fly_zone":
            messages.append(f"临时受限空域 {obs.get('id')} 被建模为硬约束单元，A* 会绕开该区域；无法绕行时进入地面兜底。")
        if obs.get("kind") == "weather_cell":
            messages.append(f"强降雨/低能见度单元 {obs.get('id')} 被建模为高风险代价区，飞行候选降低优先级。")
    if planner_trace:
        messages.append(f"A* 搜索扩展 {planner_trace.get('expanded_nodes', '--')} 个节点，硬约束单元 {planner_trace.get('hard_blocked_cells', '--')} 个，软风险单元 {planner_trace.get('weighted_risk_cells', '--')} 个。")
    return messages


def _display_type(kind: str) -> str:
    return {
        "building_cluster": "高层建筑群",
        "linear_obstacle": "高压线走廊",
        "sensitive_area": "人口密集敏感区",
        "no_fly_zone": "临时受限空域",
        "weather_cell": "恶劣天气单元",
        "resource_bottleneck": "机巢资源瓶颈",
    }.get(kind, kind or "未知障碍")


def _display_color(kind: str) -> str:
    return {
        "building_cluster": "#64748b",
        "linear_obstacle": "#facc15",
        "sensitive_area": "#a78bfa",
        "no_fly_zone": "#ef4444",
        "weather_cell": "#fb923c",
        "resource_bottleneck": "#22c55e",
    }.get(kind, "#94a3b8")


def _avoidance_mode(kind: str) -> str:
    return {
        "building_cluster": "soft_cost_side_bypass",
        "linear_obstacle": "altitude_cross_or_lateral_bypass",
        "sensitive_area": "soft_cost_boundary_bypass",
        "no_fly_zone": "hard_constraint_bypass",
        "weather_cell": "risk_weighted_weather_avoidance",
        "resource_bottleneck": "resource_delay_penalty",
    }.get(kind, "monitor")
