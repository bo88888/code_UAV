from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Iterable

from agents.airspace_approval_agent import AirspaceApprovalAgent
from agents.handover_agent import HandoverAgent
from scheduler.medical_dispatch_center import MedicalDispatchCenter
from services.medical_dispatch_repository import MedicalDispatchRepository


class MedicalDispatchService:
    """Thread-safe facade used by FastAPI endpoints and future frontend clients."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.repository = MedicalDispatchRepository()
        self.center = MedicalDispatchCenter(self.repository)
        self.airspace_agent = AirspaceApprovalAgent(self.repository.routes())
        self.handover_agent = HandoverAgent()
        self._airspace_approvals: Dict[str, Dict[str, Any]] = {}

    def network(self) -> Dict[str, Any]:
        return self.repository.network_payload()

    def fleet(self) -> Dict[str, Any]:
        return {"fleet": self.repository.fleet_payload()}

    def plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = self.center.submit(payload)
        approval = self.airspace_agent.evaluate(
            result.get("route_ids", []),
            int(result.get("task", {}).get("priority", 3)),
            bool(result.get("task", {}).get("emergency", False)),
            str(payload.get("airspace_approval_status") or ""),
        )
        task_id = str(result.get("task", {}).get("task_id") or "")
        self._airspace_approvals[task_id] = approval
        result["airspace_approval"] = approval
        if not approval["dispatch_allowed"]:
            self.cancel(task_id, "空域审批被拒绝，已释放任务资源。")
            result["status"] = "BLOCKED"
            result["task"]["status"] = "BLOCKED"
        return result

    def batch(self, payloads: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        payload_list = list(payloads)
        result = self.center.submit_batch(payload_list)
        payload_by_id = {
            str(item.get("task_id") or ""): item
            for item in payload_list
            if item.get("task_id")
        }
        for plan in result.get("plans", []):
            task = plan.get("task", {})
            task_id = str(task.get("task_id") or "")
            source = payload_by_id.get(task_id, {})
            approval = self.airspace_agent.evaluate(
                plan.get("route_ids", []),
                int(task.get("priority", 3)),
                bool(task.get("emergency", False)),
                str(source.get("airspace_approval_status") or ""),
            )
            self._airspace_approvals[task_id] = approval
            plan["airspace_approval"] = approval
        return result

    def airspace(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.airspace_agent.evaluate(
            payload.get("route_ids", []),
            int(payload.get("priority", 3)),
            bool(payload.get("emergency", False)),
            str(payload.get("external_status") or ""),
        )

    def state(self) -> Dict[str, Any]:
        result = self.center.state()
        result["airspace_approvals"] = dict(self._airspace_approvals)
        return result

    def task(self, task_id: str) -> Dict[str, Any]:
        result = self.center.get_plan(task_id)
        result["airspace_approval"] = self._airspace_approvals.get(task_id, {})
        return result

    def telemetry(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.center.update_telemetry(task_id, payload)

    def handover(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        plan = self.center.get_plan(task_id)
        verified = self.handover_agent.verify(plan, payload)
        return self.center.complete_handover(task_id, verified)

    def cancel(self, task_id: str, reason: str) -> Dict[str, Any]:
        plan = self.center.get_plan(task_id)
        result = self.center.cancel(task_id, reason)
        fleet = self.repository.fleet()
        affected = set(plan.get("primary_uav_ids", []) + plan.get("backup_uav_ids", []))
        for uav_id in affected:
            if uav_id not in fleet:
                continue
            uav = fleet[uav_id]
            if uav.assigned_task_id != task_id:
                continue
            uav.status = "IDLE" if uav_id in plan.get("primary_uav_ids", []) else "STANDBY"
            uav.assigned_task_id = None
            uav.available_at = None
            fleet[uav_id] = uav
        self.repository.update_fleet(fleet)
        return result

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            self._airspace_approvals.clear()
            result = self.center.reset()
            self.airspace_agent = AirspaceApprovalAgent(self.repository.routes())
            return result


medical_dispatch_service = MedicalDispatchService()
