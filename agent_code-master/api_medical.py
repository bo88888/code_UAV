from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from services.medical_dispatch_service import medical_dispatch_service


router = APIRouter(prefix="/api/v1/medical", tags=["medical-dispatch"])


class MedicalDispatchRequest(BaseModel):
    task_id: str = ""
    origin_node_id: str
    destination_node_id: str
    cargo_type: str = "medical_supply"
    cargo_subtype: str = ""
    cargo_weight_kg: float = Field(gt=0, le=10)
    quantity: int = Field(default=1, ge=1)
    priority: int = Field(default=3, ge=1, le=5)
    emergency: bool = False
    requested_at: str = ""
    ready_at: str = ""
    deadline: str = ""
    cold_chain_required: Optional[bool] = None
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    cold_chain_safe_minutes: Optional[int] = Field(default=None, ge=1)
    seal_id: str = ""
    biosafety_level: str = "standard"
    allow_ground_feeder: bool = True
    airspace_approval_status: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        payload = self.model_dump(exclude_none=True)
        if not payload.get("task_id"):
            payload.pop("task_id", None)
        return payload


class MedicalDispatchBatchRequest(BaseModel):
    tasks: List[MedicalDispatchRequest] = Field(min_length=1, max_length=100)


class AirspaceEvaluationRequest(BaseModel):
    route_ids: List[str] = Field(min_length=1)
    priority: int = Field(default=3, ge=1, le=5)
    emergency: bool = False
    external_status: str = ""


class TelemetryRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    uav_id: str
    leg_id: str = ""
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    altitude_m: float = 0.0
    speed_kmh: float = 0.0
    battery_percent: float = 100.0
    route_deviation_m: float = 0.0
    communication_ok: bool = True
    remote_id_ok: bool = True
    temperature_c: Optional[float] = None
    seal_closed: bool = True


class HandoverRequest(BaseModel):
    receiver_name: str
    receiver_role: str = "medical_staff"
    signed_at: str = ""
    seal_verified: bool = True
    cargo_integrity_verified: bool = True
    temperature_verified: bool = True
    remarks: str = ""


class CancelRequest(BaseModel):
    reason: str = ""


@router.get("/network")
def get_medical_network():
    return medical_dispatch_service.network()


@router.get("/fleet")
def get_medical_fleet():
    return medical_dispatch_service.fleet()


@router.get("/dispatch/state")
def get_dispatch_state():
    return medical_dispatch_service.state()


@router.get("/dispatch/tasks/{task_id}")
def get_dispatch_task(task_id: str):
    try:
        return medical_dispatch_service.task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/airspace/evaluate")
def evaluate_airspace(request: AirspaceEvaluationRequest):
    return medical_dispatch_service.airspace(request.model_dump())


@router.post("/dispatch/plan")
def plan_medical_dispatch(request: MedicalDispatchRequest):
    try:
        return medical_dispatch_service.plan(request.to_payload())
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/dispatch/batch")
def plan_medical_dispatch_batch(request: MedicalDispatchBatchRequest):
    try:
        return medical_dispatch_service.batch(item.to_payload() for item in request.tasks)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/dispatch/tasks/{task_id}/telemetry")
def update_medical_telemetry(task_id: str, request: TelemetryRequest):
    try:
        return medical_dispatch_service.telemetry(
            task_id,
            request.model_dump(exclude_none=True),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/dispatch/tasks/{task_id}/handover")
def complete_medical_handover(task_id: str, request: HandoverRequest):
    try:
        return medical_dispatch_service.handover(
            task_id,
            request.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/dispatch/tasks/{task_id}/cancel")
def cancel_medical_task(task_id: str, request: CancelRequest):
    try:
        return medical_dispatch_service.cancel(task_id, request.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/dispatch/reset")
def reset_medical_dispatch():
    return medical_dispatch_service.reset()
