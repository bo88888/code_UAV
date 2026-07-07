"""Multi-UAV coordination helpers.

The module creates a displayable multi-UAV plan from one selected route.  It is
not a full MAPPO policy, but it models the engineering concepts needed by the
platform:
- primary medical carrier;
- relay / escort UAV with height separation;
- standby backup UAV;
- time-space conflict detection and simple delay/altitude-layer resolution.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _clone_sample(sample: Dict[str, Any], altitude_offset: float, delay_seconds: float, role: str) -> Dict[str, Any]:
    out = dict(sample)
    out["altitude_m"] = round(float(out.get("altitude_m", 0.0)) + altitude_offset, 2)
    out["t_seconds"] = round(float(out.get("t_seconds", 0.0)) + delay_seconds, 2)
    out["role"] = role
    return out


def build_multi_uav_plan(
    base_trajectory: List[Dict[str, Any]],
    available_uavs: List[Dict[str, Any]],
    selected_uav_id: str,
) -> Dict[str, Any]:
    """Build a multi-UAV coordination plan for visualization and reporting."""
    if not base_trajectory:
        return {
            "enabled": False,
            "uavs": [],
            "height_time_profile": [],
            "conflict_resolution": [],
            "coordination_summary": "No trajectory samples available.",
        }

    ids = [u.get("uav_id", f"UAV-{i+1}") for i, u in enumerate(available_uavs)] or [selected_uav_id]
    if selected_uav_id and selected_uav_id in ids:
        ids.remove(selected_uav_id)
        ids.insert(0, selected_uav_id)
    while len(ids) < 3:
        ids.append(f"UAV-VIRTUAL-{len(ids)+1:03d}")

    roles = [
        ("primary_medical_carrier", 0.0, 0.0),
        ("relay_or_escort_uav", 16.0, 8.0),
        ("standby_backup_uav", 30.0, 18.0),
    ]
    colors = ["#38bdf8", "#34d399", "#facc15"]
    uav_plans: List[Dict[str, Any]] = []

    for idx, (role, altitude_offset, delay_seconds) in enumerate(roles):
        samples = [
            _clone_sample(s, altitude_offset, delay_seconds, role)
            for s in base_trajectory
        ]
        uav_plans.append(
            {
                "uav_id": ids[idx],
                "role": role,
                "color": colors[idx],
                "altitude_layer_m": round(float(samples[0].get("altitude_m", 0.0)), 1),
                "delay_seconds": delay_seconds,
                "trajectory": samples,
                "assignment": _assignment_text(role),
            }
        )

    conflicts = detect_time_space_conflicts(uav_plans)
    resolution = [
        {
            "type": "height_layering",
            "description": "UAV-2 抬升 16m 并延后 8s，UAV-3 抬升 30m 并延后 18s，避免同一时刻同一空域占用。",
            "resolved_conflicts": len(conflicts),
        }
    ]

    return {
        "enabled": True,
        "uavs": uav_plans,
        "height_time_profile": build_height_time_profile(uav_plans),
        "conflict_resolution": resolution,
        "time_space_conflicts": conflicts,
        "coordination_summary": "主运输机执行医疗载荷配送，中继/护航机保持高度层分离，备用机延迟进入航路形成接管冗余。",
    }


def _assignment_text(role: str) -> str:
    return {
        "primary_medical_carrier": "主运输：负责血液/样本/药品载荷从取货点到配送点。",
        "relay_or_escort_uav": "中继/护航：在主航路上方高度层伴随，提供通信/接力冗余。",
        "standby_backup_uav": "备援：延迟进入航路，主机异常时接管后半段任务。",
    }.get(role, role)


def detect_time_space_conflicts(uav_plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect coarse same-time/same-cell conflicts."""
    occupied: Dict[Any, str] = {}
    conflicts: List[Dict[str, Any]] = []
    for plan in uav_plans:
        for sample in plan.get("trajectory", [])[::4]:
            key = (
                round(float(sample.get("t_seconds", 0.0)) / 5),
                round(float(sample.get("lon", 0.0)) * 1000),
                round(float(sample.get("lat", 0.0)) * 1000),
                round(float(sample.get("altitude_m", 0.0)) / 10),
            )
            if key in occupied:
                conflicts.append(
                    {
                        "time_cell": key[0],
                        "space_cell": key[1:],
                        "uavs": [occupied[key], plan["uav_id"]],
                        "resolution": "altitude_layering_or_delay",
                    }
                )
            else:
                occupied[key] = plan["uav_id"]
    return conflicts


def build_height_time_profile(uav_plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    profile: List[Dict[str, Any]] = []
    for plan in uav_plans:
        samples = plan.get("trajectory", [])
        stride = max(1, len(samples) // 28)
        for sample in samples[::stride]:
            profile.append(
                {
                    "uav_id": plan["uav_id"],
                    "role": plan["role"],
                    "t_seconds": sample.get("t_seconds", 0.0),
                    "altitude_m": sample.get("altitude_m", 0.0),
                    "color": plan.get("color"),
                }
            )
    return profile
