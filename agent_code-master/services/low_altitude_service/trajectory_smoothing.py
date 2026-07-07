"""Trajectory smoothing utilities for low-altitude UAV routes.

The implementation is dependency-free.  It exposes a practical minimum-snap-like
quintic smoother: every discrete waypoint segment is interpolated with the
quintic smooth-step basis 10t^3 - 15t^4 + 6t^5, which makes velocity and
acceleration approach zero at segment boundaries.  It is not a full quadratic
programming minimum-snap solver, but it produces continuous, flyable samples
from A* waypoints and records enough metadata for later replacement by a real
ROS/minimum-snap planner.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List


def _smoothstep5(t: float) -> float:
    """Quintic minimum-snap-like blend coefficient."""
    return 10 * t**3 - 15 * t**4 + 6 * t**5


def _distance_approx_m(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    lon_scale = 111_320 * math.cos(math.radians((float(a["lat"]) + float(b["lat"])) / 2))
    lat_scale = 110_540
    dx = (float(b["lon"]) - float(a["lon"])) * lon_scale
    dy = (float(b["lat"]) - float(a["lat"])) * lat_scale
    dz = float(b.get("altitude_m", 0.0)) - float(a.get("altitude_m", 0.0))
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def smooth_trajectory(
    waypoints: Iterable[Dict[str, Any]],
    samples_per_segment: int = 10,
    nominal_speed_mps: float = 14.0,
) -> Dict[str, Any]:
    """Create continuous trajectory samples from discrete waypoints.

    Args:
        waypoints: route waypoints containing lon/lat/altitude_m.
        samples_per_segment: interpolation density for every segment.
        nominal_speed_mps: used for approximate timestamp assignment.

    Returns:
        A dict with smoothed_trajectory, trajectory_metrics and smoothing_profile.
    """
    pts = [dict(p) for p in waypoints]
    if len(pts) < 2:
        return {
            "smoothed_trajectory": pts,
            "trajectory_metrics": {
                "segment_count": max(len(pts) - 1, 0),
                "sample_count": len(pts),
                "continuous_path_length_m": 0.0,
                "max_turn_angle_deg": 0.0,
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
    last = None

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
