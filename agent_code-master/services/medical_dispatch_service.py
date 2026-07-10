from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Iterable

from scheduler.medical_dispatch_center import MedicalDispatchCenter
from services.medical_dispatch_repository import MedicalDispatchRepository


class MedicalDispatchService:
    """Thread-safe facade used by FastAPI endpoints and future frontend clients."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.repository = MedicalDispatchRepository()
        self.center = MedicalDispatchCenter(self.repository)

    def network(self) -> Dict[str, Any]:
        return self.repository.network_payload()

    def fleet(self) -> Dict[str, Any]:
        return {"fleet": self.repository.fleet_payload()}

    def plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.center.submit(payload)

    def batch(self, payloads: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        return self.center.submit_batch(payloads)

    def state(self) -> Dict[str, Any]:
        return self.center.state()

    def task(self, task_id: str) -> Dict[str, Any]:
        return self.center.get_plan(task_id)

    def telemetry(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.center.update_telemetry(task_id, payload)

    def handover(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.center.complete_handover(task_id, payload)

    def cancel(self, task_id: str, reason: str) -> Dict[str, Any]:
        return self.center.cancel(task_id, reason)

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            return self.center.reset()


medical_dispatch_service = MedicalDispatchService()
