from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.medical_models import DispatchTask, MedicalNode, RouteSegment, UAVState, isoformat, parse_datetime


class FleetAllocationAgent:
    """Assigns real fleet resources to route legs using location, battery and cargo constraints."""

    def __init__(self, nodes: Dict[str, MedicalNode]) -> None:
        self.nodes = nodes

    def allocate_leg(
        self,
        task: DispatchTask,
        segment: RouteSegment,
        fleet: Dict[str, UAVState],
        earliest_start: datetime,
        preferred_uav_id: Optional[str] = None,
    ) -> dict:
        candidates = []
        for uav in fleet.values():
            evaluation = self._evaluate(task, segment, uav, earliest_start, preferred_uav_id)
            if evaluation["feasible"]:
                candidates.append(evaluation)
        if not candidates:
            raise ValueError(
                f"no feasible UAV for {segment.segment_id}: payload, range, battery or cold-box constraints"
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        selected = candidates[0]
        uav = fleet[selected["uav_id"]]
        start_time = selected["available_start"]
        duration = selected["flight_minutes"]
        arrival_time = start_time + timedelta(minutes=duration)

        uav.status = "RESERVED"
        uav.assigned_task_id = task.task_id
        uav.current_node_id = segment.to_node
        uav.battery_percent = round(
            max(0.0, uav.battery_percent - selected["energy_percent"]), 2
        )
        uav.available_at = isoformat(arrival_time)
        fleet[uav.uav_id] = uav

        return {
            "uav_id": uav.uav_id,
            "score": round(selected["score"], 3),
            "available_start": start_time,
            "arrival_time": arrival_time,
            "flight_minutes": round(duration, 2),
            "energy_percent": round(selected["energy_percent"], 2),
            "reposition_required": selected["reposition_required"],
            "reposition_distance_km": round(selected["reposition_distance_km"], 3),
            "reposition_minutes": round(selected["reposition_minutes"], 2),
            "battery_after_percent": uav.battery_percent,
            "candidate_ranking": [
                {
                    "uav_id": item["uav_id"],
                    "score": round(item["score"], 3),
                    "wait_minutes": round(item["wait_minutes"], 2),
                    "reposition_distance_km": round(item["reposition_distance_km"], 3),
                    "battery_percent": item["battery_percent"],
                }
                for item in candidates
            ],
        }

    def reserve_backup(
        self,
        task: DispatchTask,
        fleet: Dict[str, UAVState],
        excluded_uav_ids: List[str],
        origin_node_id: str,
        start_time: datetime,
        reserve_until: datetime,
    ) -> Optional[dict]:
        if task.priority < 4 and not task.emergency:
            return None
        candidates = []
        for uav in fleet.values():
            if uav.uav_id in excluded_uav_ids:
                continue
            if not self._basic_capability(task, uav):
                continue
            available = parse_datetime(uav.available_at, start_time) if uav.available_at else start_time
            wait = max(0.0, (available - start_time).total_seconds() / 60.0)
            reposition = self._node_distance(uav.current_node_id, origin_node_id)
            score = uav.battery_percent - wait * 2.0 - reposition * 1.5
            candidates.append((score, uav, wait, reposition))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        score, uav, wait, reposition = candidates[0]
        uav.status = "RESERVED"
        uav.assigned_task_id = task.task_id
        uav.available_at = isoformat(reserve_until)
        fleet[uav.uav_id] = uav
        return {
            "uav_id": uav.uav_id,
            "role": "standby_backup",
            "score": round(score, 3),
            "current_node_id": uav.current_node_id,
            "activation_delay_minutes": round(wait + reposition / max(uav.cruise_speed_kmh, 1.0) * 60.0, 2),
            "battery_percent": uav.battery_percent,
            "reserved_until": isoformat(reserve_until),
        }

    def _evaluate(
        self,
        task: DispatchTask,
        segment: RouteSegment,
        uav: UAVState,
        earliest_start: datetime,
        preferred_uav_id: Optional[str],
    ) -> dict:
        feasible = self._basic_capability(task, uav)
        if segment.distance_km > uav.loaded_range_km:
            feasible = False
        available_time = parse_datetime(uav.available_at, earliest_start) if uav.available_at else earliest_start
        wait_minutes = max(0.0, (available_time - earliest_start).total_seconds() / 60.0)
        reposition_distance = self._node_distance(uav.current_node_id, segment.from_node)
        if reposition_distance > uav.empty_range_km:
            feasible = False
        reposition_minutes = reposition_distance / max(uav.cruise_speed_kmh, 1.0) * 60.0
        available_start = max(available_time, earliest_start) + timedelta(minutes=reposition_minutes)
        energy_percent = self._energy_percent(segment.distance_km, reposition_distance, uav)
        if uav.battery_percent < energy_percent + 15.0:
            feasible = False

        score = 0.0
        score += 42.0 if uav.current_node_id == segment.from_node else 0.0
        score += 18.0 if uav.status in {"IDLE", "STANDBY"} else 0.0
        score += min(uav.battery_percent, 100.0) * 0.35
        score -= wait_minutes * 1.8
        score -= reposition_distance * 2.2
        score -= uav.flight_hours * 0.01
        if preferred_uav_id and uav.uav_id == preferred_uav_id:
            score += 22.0
        if task.emergency:
            score += 8.0 if uav.status == "STANDBY" else 0.0

        flight_minutes = segment.distance_km / max(uav.cruise_speed_kmh, 1.0) * 60.0 + 2.0
        return {
            "uav_id": uav.uav_id,
            "feasible": feasible,
            "score": score,
            "available_start": available_start,
            "wait_minutes": wait_minutes,
            "reposition_required": reposition_distance > 0.05,
            "reposition_distance_km": reposition_distance,
            "reposition_minutes": reposition_minutes,
            "flight_minutes": flight_minutes,
            "energy_percent": energy_percent,
            "battery_percent": uav.battery_percent,
        }

    def _basic_capability(self, task: DispatchTask, uav: UAVState) -> bool:
        if uav.maintenance_status != "NORMAL":
            return False
        if uav.status in {"MAINTENANCE", "UNAVAILABLE"}:
            return False
        if task.cargo.weight_kg > uav.payload_capacity_kg:
            return False
        if task.cargo.cargo_type not in uav.supported_cargo_types:
            return False
        required_box = self._required_box(task)
        return required_box in uav.cold_box_types

    @staticmethod
    def _required_box(task: DispatchTask) -> str:
        if not task.cargo.cold_chain_required:
            return "ambient"
        low = task.cargo.temperature_min_c
        high = task.cargo.temperature_max_c
        if low is not None and high is not None and low >= 2 and high <= 6:
            return "2_6C"
        return "2_8C"

    @staticmethod
    def _energy_percent(distance_km: float, reposition_km: float, uav: UAVState) -> float:
        loaded = distance_km / max(uav.loaded_range_km, 0.1) * 72.0
        empty = reposition_km / max(uav.empty_range_km, 0.1) * 45.0
        return round(loaded + empty + 4.0, 2)

    def _node_distance(self, first_id: str, second_id: str) -> float:
        if first_id == second_id:
            return 0.0
        first = self.nodes.get(first_id)
        second = self.nodes.get(second_id)
        if not first or not second:
            return 999.0
        return self._haversine(first.longitude, first.latitude, second.longitude, second.latitude)

    @staticmethod
    def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        radius = 6371.0088
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        value = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))
