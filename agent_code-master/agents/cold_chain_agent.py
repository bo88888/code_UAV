from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from core.medical_models import AlertLevel, DispatchAlert, DispatchTask, MedicalNode, isoformat


class ColdChainAgent:
    """Validates cold-chain feasibility and evaluates temperature telemetry."""

    def __init__(self, nodes: Dict[str, MedicalNode]) -> None:
        self.nodes = nodes

    def evaluate_plan(
        self,
        task: DispatchTask,
        estimated_total_minutes: float,
        node_path: List[str],
    ) -> dict:
        cargo = task.cargo
        required_box = self.required_box(task)
        safe_minutes = max(int(cargo.cold_chain_safe_minutes), 1)
        margin = round(safe_minutes - estimated_total_minutes, 2)
        destination = self.nodes[task.destination_node_id]
        issues = []
        if cargo.cold_chain_required and not destination.supports_cold_chain:
            issues.append("destination_has_no_cold_storage")
        if cargo.cold_chain_required and margin < 0:
            issues.append("cold_chain_safe_time_exceeded")
        relay_without_storage = [
            node_id
            for node_id in node_path[1:-1]
            if not self.nodes[node_id].supports_cold_chain
        ]
        return {
            "required": cargo.cold_chain_required,
            "required_box_type": required_box,
            "temperature_range_c": [cargo.temperature_min_c, cargo.temperature_max_c],
            "safe_minutes": safe_minutes,
            "estimated_exposure_minutes": round(estimated_total_minutes, 2),
            "remaining_margin_minutes": margin,
            "destination_cold_storage_ready": destination.supports_cold_chain,
            "sealed_transfer_through_non_storage_relays": relay_without_storage,
            "feasible": not issues,
            "issues": issues,
            "sampling_interval_seconds": 60,
            "trace_binding": {
                "task_id": task.task_id,
                "seal_id": cargo.seal_id,
            },
        }

    def evaluate_temperature(
        self,
        task: DispatchTask,
        temperature_c: Optional[float],
        timestamp: Optional[datetime] = None,
    ) -> Optional[DispatchAlert]:
        if not task.cargo.cold_chain_required or temperature_c is None:
            return None
        low = task.cargo.temperature_min_c
        high = task.cargo.temperature_max_c
        if low is None or high is None or low <= temperature_c <= high:
            return None
        return DispatchAlert(
            alert_id=f"{task.task_id}-TEMP-{int((timestamp or datetime.now()).timestamp())}",
            task_id=task.task_id,
            level=AlertLevel.CRITICAL,
            alert_type="COLD_CHAIN_TEMPERATURE_OUT_OF_RANGE",
            message=f"冷链温度 {temperature_c}℃ 超出允许范围 {low}–{high}℃。",
            recommended_actions=[
                "优先选择最近具备冷链交接能力的医疗节点备降",
                "通知接收医院和调度中心准备人工核验",
                "保留温度曲线、电子封签和开箱记录",
            ],
            created_at=isoformat(timestamp or datetime.now().astimezone()),
            details={
                "temperature_c": temperature_c,
                "minimum_c": low,
                "maximum_c": high,
                "seal_id": task.cargo.seal_id,
            },
        )

    @staticmethod
    def required_box(task: DispatchTask) -> str:
        cargo = task.cargo
        if not cargo.cold_chain_required:
            return "ambient"
        if (
            cargo.temperature_min_c is not None
            and cargo.temperature_max_c is not None
            and cargo.temperature_min_c >= 2
            and cargo.temperature_max_c <= 6
        ):
            return "2_6C"
        return "2_8C"
