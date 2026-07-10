from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from core.medical_models import DispatchPlan, DispatchTask, parse_datetime


class MedicalDispatchAgent:
    """Ranks concurrent medical tasks and summarizes multi-agent scheduling decisions."""

    def rank_tasks(self, tasks: Iterable[DispatchTask]) -> List[DispatchTask]:
        return sorted(tasks, key=self._sort_key)

    def priority_score(self, task: DispatchTask) -> float:
        score = float(max(1, min(task.priority, 5)) * 100)
        if task.emergency:
            score += 1000.0
        cargo_bonus = {
            "blood": 180.0,
            "blood_product": 180.0,
            "aed": 170.0,
            "emergency_medicine": 160.0,
            "trauma_supply": 150.0,
            "pathology_sample": 80.0,
            "sample": 60.0,
            "medicine": 50.0,
            "medical_supply": 30.0,
        }
        score += cargo_bonus.get(task.cargo.cargo_type, 20.0)
        if task.deadline:
            deadline = parse_datetime(task.deadline)
            remaining_minutes = (deadline - datetime.now().astimezone()).total_seconds() / 60.0
            if remaining_minutes <= 30:
                score += 150.0
            elif remaining_minutes <= 60:
                score += 80.0
        if task.cargo.cold_chain_required:
            score += 40.0
        return round(score, 2)

    def build_summary(self, plan: DispatchPlan) -> Dict[str, Any]:
        roles = []
        for uav_id in plan.primary_uav_ids:
            roles.append({"uav_id": uav_id, "role": "primary_or_relay_carrier"})
        for uav_id in plan.backup_uav_ids:
            roles.append({"uav_id": uav_id, "role": "standby_backup"})
        return {
            "task_priority_score": self.priority_score(plan.task),
            "network_mode": "multi_leg_medical_network" if len(plan.legs) > 1 else "fixed_corridor_direct",
            "route_ids": plan.route_ids,
            "node_path": plan.node_path,
            "uav_roles": roles,
            "relay_count": len(plan.relay_operations),
            "resource_reservation_count": len(plan.resource_reservations),
            "cold_chain_required": plan.task.cargo.cold_chain_required,
            "deadline_met": plan.deadline_met,
            "decision_basis": [
                "医疗任务优先级与截止时间",
                "L1-L8固定医疗航线网络",
                "无人机位置、载重、续航、电量和可用时间",
                "起降机位与中继换电资源",
                "冷链安全余量和接收节点能力",
            ],
        }

    def _sort_key(self, task: DispatchTask) -> tuple:
        deadline = parse_datetime(task.deadline, datetime.max.astimezone()) if task.deadline else datetime.max.astimezone()
        return (-self.priority_score(task), deadline, task.requested_at or task.task_id)
