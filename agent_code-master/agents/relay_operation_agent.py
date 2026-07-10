from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

from agents.node_resource_agent import NodeResourceAgent
from core.medical_models import DispatchTask, MedicalNode, UAVState, isoformat


class RelayOperationAgent:
    """Plans battery swap, fleet handoff, communication check and emergency-landing readiness."""

    def __init__(self, nodes: Dict[str, MedicalNode], resource_agent: NodeResourceAgent) -> None:
        self.nodes = nodes
        self.resource_agent = resource_agent

    def plan(
        self,
        task: DispatchTask,
        leg_id: str,
        node_id: str,
        arrival_time: datetime,
        uav: UAVState,
        next_leg_distance_km: Optional[float],
    ) -> dict:
        node = self.nodes[node_id]
        if next_leg_distance_km is None:
            return {
                "node_id": node_id,
                "operation_type": "final_arrival",
                "arrival_time": isoformat(arrival_time),
                "departure_time": None,
                "duration_minutes": 0.0,
                "battery_before_percent": uav.battery_percent,
                "battery_after_percent": uav.battery_percent,
                "requires_new_uav": False,
            }

        required_percent = next_leg_distance_km / max(uav.loaded_range_km, 0.1) * 72.0 + 19.0
        must_swap = uav.battery_percent < required_percent or node.node_type == "relay"
        if not must_swap:
            inspection_minutes = 1.5
            departure = arrival_time + timedelta(minutes=inspection_minutes)
            return {
                "node_id": node_id,
                "node_name": node.name,
                "operation_type": "technical_check",
                "arrival_time": isoformat(arrival_time),
                "departure_time": isoformat(departure),
                "duration_minutes": inspection_minutes,
                "battery_before_percent": uav.battery_percent,
                "battery_after_percent": uav.battery_percent,
                "communication_check": "PASSED",
                "cold_chain_handover": "NOT_REQUIRED",
                "requires_new_uav": False,
            }

        if not node.supports_battery_swap or node.battery_swap_slots <= 0:
            handoff_minutes = 3.0
            departure = arrival_time + timedelta(minutes=handoff_minutes)
            uav.available_at = isoformat(arrival_time)
            return {
                "node_id": node_id,
                "node_name": node.name,
                "operation_type": "fleet_handoff_required",
                "arrival_time": isoformat(arrival_time),
                "departure_time": isoformat(departure),
                "duration_minutes": handoff_minutes,
                "battery_before_percent": uav.battery_percent,
                "battery_after_percent": uav.battery_percent,
                "communication_check": "PASSED" if node.communication_mode else "MANUAL_CONFIRMATION_REQUIRED",
                "cold_chain_handover": "SEALED_BOX_TRANSFER",
                "requires_new_uav": True,
                "handoff_reason": "current UAV battery cannot safely complete the next leg and this node has no battery-swap slot",
            }

        reservation = self.resource_agent.reserve(
            node_id=node_id,
            resource_type="battery_swap_slot",
            requested_start=arrival_time,
            duration_minutes=4.0,
            task_id=task.task_id,
            leg_id=leg_id,
        )
        start = datetime.fromisoformat(reservation["start_time"])
        departure = datetime.fromisoformat(reservation["end_time"])
        before = uav.battery_percent
        uav.status = "BATTERY_SWAPPING"
        uav.battery_percent = 100.0
        uav.available_at = isoformat(departure)
        return {
            "node_id": node_id,
            "node_name": node.name,
            "operation_type": "battery_swap_and_safety_check",
            "arrival_time": isoformat(arrival_time),
            "operation_start_time": isoformat(start),
            "departure_time": isoformat(departure),
            "duration_minutes": round((departure - arrival_time).total_seconds() / 60.0, 2),
            "queue_delay_minutes": reservation["delay_minutes"],
            "battery_before_percent": before,
            "battery_after_percent": 100.0,
            "communication_check": "PASSED" if node.communication_mode else "MANUAL_CONFIRMATION_REQUIRED",
            "weather_check": "PASSED" if node.weather_station else "REMOTE_DATA_ONLY",
            "emergency_landing_ready": True,
            "requires_new_uav": False,
            "resource_reservation": reservation,
        }
