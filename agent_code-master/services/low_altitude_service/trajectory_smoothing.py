"""Trajectory smoothing utilities for low-altitude UAV routes.

This module is dependency-free. It exposes a practical minimum-snap-like
quintic smoother: every discrete waypoint segment is interpolated with the
quintic smooth-step basis 10t^3 - 15t^4 + 6t^5, which makes velocity and
acceleration approach zero at segment boundaries.

The smoother intentionally accepts multiple waypoint formats because the legacy
project has used both dict-style nodes and compact list/tuple waypoints. This
keeps all ROUTE tools compatible while still returning one standard frontend
format: {id, lon, lat, altitude_m, name}.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional


def _smoothstep5(t: float) -> float:
    """Quintic minimum-snap-like blend coefficient."""
    return 10 * t**3 - 15 * t**4 + 6 * t**5


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_waypoint(point: Any, index: int) -> Optional[Dict[str, Any]]:
    """Normalize legacy waypoint representations into dicts.

    Supported inputs:
    - {"lon": ..., "lat": ..., "altitude_m": ...}
    - {"lng": ..., "lat": ..., "alt": ...}
    - {"location": {"lon": ..., "lat": ...}, "altitude_m": ...}
    - [lon, lat, altitude]
    - (lon, lat, altitude)
    """
    if isinstance(point, dict):
        location = point.get("location") if isinstance(point.get("location"), dict) else {}
        lon = point.get("lon", point.get("lng", location.get("lon", location.get("lng"))))
        lat = point.get("lat", location.get("lat"))
        altitude = point.get(
            "altitude_m",
            point.get("alt", point.get("altitude", location.get("altitude_m", 0.0))),
        )
        if lon is None or lat is None:
            coords = point.get("coordinates") or point.get("coord") or point.get("point")
            if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                lon, lat = coords[0], coords[1]
                altitude = coords[2] if len(coords) >= 3 else altitude
        if lon is None or lat is None:
            return None
        return {
            "id": point.get("id", point.get("node_id", point.get("sample_id", f"WP_{index:03d}"))),
            "name": point.get("name", point.get("label", f"waypoint_{index:03d}")),
            "lon": round(_coerce_float(lon), 7),
            "lat": round(_coerce_float(lat), 7),
            "altitude_m": round(_coerce_float(altitude, 0.0), 2),
        }

    if isinstance(point, (list, tuple)):
        if len(point) >= 3 and all(isinstance(x, (int, float, str)) for x in point[:3]):
            return {
                "id": f"WP_{index:03d}",
                "name": f"waypoint_{index:03d}",
                "lon": round(_coerce_float(point[0]), 7),
                "lat": round(_coerce_float(point[1]), 7),
                "altitude_m": round(_coerce_float(point[2], 0.0), 2),
            }
        if len(point) >= 2 and all(isinstance(x, (int, float, str)) for x in point[:2]):
            return {
                "id": f"WP_{index:03d}",
                "name": f"waypoint_{index:03d}",
                "lon": round(_coerce_float(point[0]), 7),
                "lat": round(_coerce_float(point[1]), 7),
                "altitude_m": 0.0,
            }
        # Some legacy values are list-like pairs, e.g. [("lon", 114), ...].
        try:
            maybe_dict = dict(point)
            return _normalize_waypoint(maybe_dict, index)
        except Exception:
            return None

    return None


def normalize_waypoints(waypoints: Iterable[Any]) -> List[Dict[str, Any]]:
    """Normalize and filter waypoint inputs."""
    normalized: List[Dict[str, Any]] = []
    for idx, point in enumerate(waypoints or []):
        item = _normalize_waypoint(point, idx)
        if item is not None:
            normalized.append(item)
    return normalized


def _distance_approx_m(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    lon_scale = 111_320 * math.cos(math.radians((float(a["lat"]) + float(b["lat"])) / 2))
    lat_scale = 110_540
    dx = (float(b["lon"]) - float(a["lon"])) * lon_scale
    dy = (float(b["lat"]) - float(a["lat"])) * lat_scale
    dz = float(b.get("altitude_m", 0.0)) - float(a.get("altitude_m", 0.0))
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def smooth_trajectory(
    waypoints: Iterable[Any],
    samples_per_segment: int = 10,
    nominal_speed_mps: float = 14.0,
) -> Dict[str, Any]:
    """Create continuous trajectory samples from discrete waypoints."""
    pts = normalize_waypoints(waypoints)
    if len(pts) < 2:
        return {
            "smoothed_trajectory": pts,
            "trajectory_metrics": {
                "segment_count": max(len(pts) - 1, 0),
                "sample_count": len(pts),
                "continuous_path_length_m": 0.0,
                "max_turn_angle_deg": 0.0,
                "normalization_warning": "fewer_than_two_valid_waypoints",
            },
            "smoothing_profile": {
                "method": "quintic_minimum_snap_like",
                "basis": "10t^3 - 15t^4 + 6t^5",
                "samples_per_segment": samples_per_segment,
                "ros_ready": True,
            },
        }

    samples: List[Dict[str, Any]] = []
    elapsed = 0.0
    length_m = 0.0
    last: Optional[Dict[str, Any]] = None

    for seg_idx in range(len(pts) - 1):
        a, b = pts[seg_idx], pts[seg_idx + 1]
        seg_len = _distance_approx_m(a, b)
        steps = max(3, samples_per_segment)
        for i in range(steps):
            if seg_idx > 0 and i == 0:
                continue
            u = i / (steps - 1)
            s = _smoothstep5(u)
            sample = {
                "sample_id": f"SMOOTH_{len(samples):03d}",
                "segment_index": seg_idx,
                "lon": round(float(a["lon"]) + (float(b["lon"]) - float(a["lon"])) * s, 7),
                "lat": round(float(a["lat"]) + (float(b["lat"]) - float(a["lat"])) * s, 7),
                "altitude_m": round(float(a.get("altitude_m", 0.0)) + (float(b.get("altitude_m", 0.0)) - float(a.get("altitude_m", 0.0))) * s, 2),
                "t_seconds": round(elapsed + (seg_len / max(nominal_speed_mps, 1.0)) * u, 2),
                "phase": "minimum_snap_smooth",
            }
            if last is not None:
                length_m += _distance_approx_m(last, sample)
            samples.append(sample)
            last = sample
        elapsed += seg_len / max(nominal_speed_mps, 1.0)

    return {
        "smoothed_trajectory": samples,
        "trajectory_metrics": {
            "segment_count": len(pts) - 1,
            "sample_count": len(samples),
            "continuous_path_length_m": round(length_m, 2),
            "max_turn_angle_deg": _max_turn_angle(pts),
            "input_waypoint_count": len(pts),
        },
        "smoothing_profile": {
            "method": "quintic_minimum_snap_like",
            "basis": "10t^3 - 15t^4 + 6t^5",
            "samples_per_segment": samples_per_segment,
            "nominal_speed_mps": nominal_speed_mps,
            "ros_ready": True,
            "replacement_hint": "Can be replaced by a real ROS minimum_snap_trajectory_generation node.",
        },
    }


def _max_turn_angle(pts: List[Dict[str, Any]]) -> float:
    angles: List[float] = []
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        v1 = (float(a["lon"]) - float(b["lon"]), float(a["lat"]) - float(b["lat"]))
        v2 = (float(c["lon"]) - float(b["lon"]), float(c["lat"]) - float(b["lat"]))
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 == 0 or n2 == 0:
            continue
        cosv = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        angles.append(math.degrees(math.acos(cosv)))
    return round(max(angles), 2) if angles else 0.0


def make_ros_node_graph() -> Dict[str, Any]:
    """Return an engineering-oriented ROS-style node graph for frontend display."""
    return {
        "framework": "ROS-compatible logical architecture",
        "nodes": [
            {"name": "mission_dispatch_node", "role": "任务接收、任务状态机、调度命令发布"},
            {"name": "obstacle_map_node", "role": "建筑群/高压线/敏感区/禁飞区转局部占据图"},
            {"name": "astar_3d_planner_node", "role": "三维 A* 搜索，输出离散航点"},
            {"name": "minimum_snap_smoother_node", "role": "离散航点转连续可飞轨迹"},
            {"name": "multi_uav_coordination_node", "role": "多 UAV 高度分层、延时避让和备援协同"},
            {"name": "telemetry_visualization_node", "role": "轨迹、障碍物、风险和回放可视化"},
        ],
        "topics": [
            "/mission_request",
            "/obstacle_map",
            "/astar_waypoints",
            "/smoothed_trajectory",
            "/multi_uav_plan",
            "/telemetry",
        ],
    }
