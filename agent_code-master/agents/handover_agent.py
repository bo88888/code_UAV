from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from core.medical_models import DispatchPlan, isoformat, to_primitive


class HandoverAgent:
    """Validates medical cargo sign-off, seal, integrity and temperature evidence."""

    def verify(self, plan: DispatchPlan | Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        serialized = to_primitive(plan) if isinstance(plan, DispatchPlan) else plan
        task = serialized.get("task", {})
        cargo = task.get("cargo", {})
        receiver_name = str(payload.get("receiver_name") or "").strip()
        if not receiver_name:
            raise ValueError("receiver_name is required for medical handover")
        seal_verified = bool(payload.get("seal_verified", False))
        cargo_integrity_verified = bool(payload.get("cargo_integrity_verified", False))
        temperature_verified = bool(payload.get("temperature_verified", False))
        if not seal_verified:
            raise ValueError("medical cargo seal verification failed")
        if not cargo_integrity_verified:
            raise ValueError("medical cargo integrity verification failed")
        if bool(cargo.get("cold_chain_required")) and not temperature_verified:
            raise ValueError("cold-chain cargo requires temperature verification before completion")
        now = datetime.now().astimezone()
        return {
            "receiver_name": receiver_name,
            "receiver_role": str(payload.get("receiver_role") or "medical_staff"),
            "signed_at": str(payload.get("signed_at") or isoformat(now)),
            "seal_id": str(cargo.get("seal_id") or ""),
            "seal_verified": seal_verified,
            "cargo_integrity_verified": cargo_integrity_verified,
            "temperature_verified": temperature_verified,
            "remarks": str(payload.get("remarks") or ""),
            "handover_result": "ACCEPTED",
            "trace_binding": {
                "task_id": str(task.get("task_id") or ""),
                "destination_node_id": str(task.get("destination_node_id") or ""),
                "cargo_type": str(cargo.get("cargo_type") or ""),
            },
        }
