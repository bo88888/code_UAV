from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from threading import RLock
from typing import Dict, List

from core.medical_models import MedicalNode, isoformat, parse_datetime


class NodeResourceAgent:
    """Reserves pads, battery-swap slots, cold cabinets and handover windows."""

    def __init__(self, nodes: Dict[str, MedicalNode]) -> None:
        self.nodes = nodes
        self._reservations: Dict[str, List[dict]] = defaultdict(list)
        self._lock = RLock()

    def reserve(
        self,
        node_id: str,
        resource_type: str,
        requested_start: datetime,
        duration_minutes: float,
        task_id: str,
        leg_id: str,
    ) -> dict:
        if node_id not in self.nodes:
            raise ValueError(f"unknown node for reservation: {node_id}")
        capacity = self._capacity(self.nodes[node_id], resource_type)
        if capacity <= 0:
            raise ValueError(f"node {node_id} has no {resource_type} capacity")
        duration = timedelta(minutes=max(duration_minutes, 0.5))
        with self._lock:
            start = requested_start
            for _ in range(180):
                end = start + duration
                overlaps = [
                    item
                    for item in self._reservations[node_id]
                    if item["resource_type"] == resource_type
                    and self._overlap(start, end, parse_datetime(item["start_time"]), parse_datetime(item["end_time"]))
                ]
                if len(overlaps) < capacity:
                    reservation = {
                        "reservation_id": f"{task_id}-{leg_id}-{resource_type}-{len(self._reservations[node_id]) + 1}",
                        "task_id": task_id,
                        "leg_id": leg_id,
                        "node_id": node_id,
                        "node_name": self.nodes[node_id].name,
                        "resource_type": resource_type,
                        "capacity": capacity,
                        "start_time": isoformat(start),
                        "end_time": isoformat(end),
                        "delay_minutes": round((start - requested_start).total_seconds() / 60.0, 2),
                    }
                    self._reservations[node_id].append(reservation)
                    return reservation
                start += timedelta(minutes=1)
        raise ValueError(f"unable to reserve {resource_type} at {node_id} within 180 minutes")

    def release_task(self, task_id: str) -> int:
        removed = 0
        with self._lock:
            for node_id, items in list(self._reservations.items()):
                kept = [item for item in items if item["task_id"] != task_id]
                removed += len(items) - len(kept)
                self._reservations[node_id] = kept
        return removed

    def snapshot(self) -> dict:
        with self._lock:
            return {
                node_id: list(items)
                for node_id, items in self._reservations.items()
            }

    @staticmethod
    def _overlap(first_start: datetime, first_end: datetime, second_start: datetime, second_end: datetime) -> bool:
        return first_start < second_end and second_start < first_end

    @staticmethod
    def _capacity(node: MedicalNode, resource_type: str) -> int:
        mapping = {
            "pad": node.pad_count,
            "charging_slot": node.charging_slots,
            "battery_swap_slot": node.battery_swap_slots,
            "cold_storage_slot": node.cold_storage_slots,
            "handover_cabinet": node.handover_cabinets,
        }
        return int(mapping.get(resource_type, 0))
