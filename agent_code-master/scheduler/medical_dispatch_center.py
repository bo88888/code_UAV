from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

from agents.cold_chain_agent import ColdChainAgent
from agents.emergency_response_agent import EmergencyResponseAgent
from agents.fleet_allocation_agent import FleetAllocationAgent
from agents.flight_monitor_agent import FlightMonitorAgent
from agents.medical_dispatch_agent import MedicalDispatchAgent
from agents.network_route_agent import NetworkRouteAgent
from agents.node_resource_agent import NodeResourceAgent
from agents.relay_operation_agent import RelayOperationAgent
from core.medical_models import (
    AlertLevel,
    DispatchAlert,
    DispatchEvent,
    DispatchPlan,
    DispatchTask,
    FlightLeg,
    MedicalCargo,
    MedicalTaskStatus,
    isoformat,
    parse_datetime,
    to_primitive,
)
from services.medical_dispatch_repository import MedicalDispatchRepository


class MedicalDispatchCenter:
    """Coordinates medical-network routing, fleet allocation and operational resources."""

    def __init__(self, repository: Optional[MedicalDispatchRepository] = None) -> None:
        self.repository = repository or MedicalDispatchRepository()
        self._lock = RLock()
        self._plans: Dict[str, DispatchPlan] = {}
        self._global_alerts: List[DispatchAlert] = []
        self._build_agents()

    def _build_agents(self) -> None:
        self.nodes = self.repository.nodes()
        self.routes = self.repository.routes()
        self.route_agent = NetworkRouteAgent(self.nodes, self.routes)
        self.resource_agent = NodeResourceAgent(self.nodes)
        self.fleet_agent = FleetAllocationAgent(self.nodes)
        self.relay_agent = RelayOperationAgent(self.nodes, self.resource_agent)
        self.cold_chain_agent = ColdChainAgent(self.nodes)
        self.emergency_agent = EmergencyResponseAgent()
        self.monitor_agent = FlightMonitorAgent(self.cold_chain_agent, self.emergency_agent)
        self.dispatch_agent = MedicalDispatchAgent()

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        task = self._build_task(payload)
        with self._lock:
            plan = self._plan_task(task)
            return to_primitive(plan)

    def submit_batch(self, payloads: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        tasks = [self._build_task(item) for item in payloads]
        ranked = self.dispatch_agent.rank_tasks(tasks)
        results = []
        errors = []
        with self._lock:
            for task in ranked:
                try:
                    results.append(to_primitive(self._plan_task(task)))
                except Exception as exc:  # noqa: BLE001 - API returns task-scoped planning errors.
                    errors.append(
                        {
                            "task_id": task.task_id,
                            "status": MedicalTaskStatus.BLOCKED.value,
                            "error": str(exc),
                            "priority_score": self.dispatch_agent.priority_score(task),
                        }
                    )
        return {
            "dispatch_mode": "priority_aware_multi_task_batch",
            "submitted": len(tasks),
            "planned": len(results),
            "blocked": len(errors),
            "plans": results,
            "errors": errors,
            "fleet": self.repository.fleet_payload(),
            "resource_reservations": self.resource_agent.snapshot(),
        }

    def get_plan(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._plans:
                raise KeyError(f"medical dispatch task not found: {task_id}")
            return to_primitive(self._plans[task_id])

    def state(self) -> Dict[str, Any]:
        with self._lock:
            plans = list(self._plans.values())
            status_counts: Dict[str, int] = {}
            for plan in plans:
                status_counts[plan.status.value] = status_counts.get(plan.status.value, 0) + 1
            return {
                "task_count": len(plans),
                "status_counts": status_counts,
                "tasks": [
                    {
                        "task_id": plan.task.task_id,
                        "status": plan.status.value,
                        "origin_node_id": plan.task.origin_node_id,
                        "destination_node_id": plan.task.destination_node_id,
                        "cargo_type": plan.task.cargo.cargo_type,
                        "priority": plan.task.priority,
                        "route_ids": plan.route_ids,
                        "primary_uav_ids": plan.primary_uav_ids,
                        "backup_uav_ids": plan.backup_uav_ids,
                        "estimated_arrival_time": plan.estimated_arrival_time,
                        "deadline_met": plan.deadline_met,
                    }
                    for plan in plans
                ],
                "fleet": self.repository.fleet_payload(),
                "node_reservations": self.resource_agent.snapshot(),
                "active_alerts": [to_primitive(item) for item in self._global_alerts[-100:]],
            }

    def update_telemetry(self, task_id: str, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._plans:
                raise KeyError(f"medical dispatch task not found: {task_id}")
            plan = self._plans[task_id]
            alerts = self.monitor_agent.evaluate(plan.task, plan, telemetry)
            if alerts:
                plan.alerts.extend(alerts)
                self._global_alerts.extend(alerts)
                if any(item.level == AlertLevel.CRITICAL for item in alerts):
                    plan.status = MedicalTaskStatus.EXCEPTION
                    plan.task.status = MedicalTaskStatus.EXCEPTION
            elif plan.status == MedicalTaskStatus.READY_FOR_DISPATCH:
                plan.status = MedicalTaskStatus.IN_TRANSIT
                plan.task.status = MedicalTaskStatus.IN_TRANSIT
            self._plans[task_id] = plan
            return {
                "task_id": task_id,
                "status": plan.status.value,
                "telemetry": telemetry,
                "alerts": [to_primitive(item) for item in alerts],
                "recommended_actions": [
                    action
                    for alert in alerts
                    for action in alert.recommended_actions
                ],
            }

    def complete_handover(self, task_id: str, handover: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._plans:
                raise KeyError(f"medical dispatch task not found: {task_id}")
            plan = self._plans[task_id]
            now = datetime.now().astimezone()
            plan.status = MedicalTaskStatus.COMPLETED
            plan.task.status = MedicalTaskStatus.COMPLETED
            plan.events.append(
                self._event(
                    plan.task,
                    "HANDOVER_COMPLETED",
                    "handover_agent",
                    "医疗物资已完成签收、封签核验和任务归档。",
                    MedicalTaskStatus.COMPLETED,
                    handover,
                    now,
                )
            )
            fleet = self.repository.fleet()
            for uav_id in set(plan.primary_uav_ids + plan.backup_uav_ids):
                if uav_id not in fleet:
                    continue
                uav = fleet[uav_id]
                uav.status = "IDLE" if uav_id in plan.primary_uav_ids else "STANDBY"
                uav.assigned_task_id = None
                uav.available_at = isoformat(now)
                fleet[uav_id] = uav
            self.repository.update_fleet(fleet)
            self._plans[task_id] = plan
            return {
                "task_id": task_id,
                "status": plan.status.value,
                "handover": handover,
                "completed_at": isoformat(now),
                "trace": [to_primitive(item) for item in plan.events],
            }

    def cancel(self, task_id: str, reason: str) -> Dict[str, Any]:
        with self._lock:
            if task_id not in self._plans:
                raise KeyError(f"medical dispatch task not found: {task_id}")
            plan = self._plans[task_id]
            plan.status = MedicalTaskStatus.CANCELLED
            plan.task.status = MedicalTaskStatus.CANCELLED
            released = self.resource_agent.release_task(task_id)
            plan.events.append(
                self._event(
                    plan.task,
                    "TASK_CANCELLED",
                    "medical_dispatch_center",
                    reason or "任务已取消。",
                    MedicalTaskStatus.CANCELLED,
                    {"released_reservations": released},
                )
            )
            self._plans[task_id] = plan
            return {"task_id": task_id, "status": plan.status.value, "released_reservations": released}

    def reset(self) -> Dict[str, Any]:
        with self._lock:
            self.repository.reload()
            self._plans.clear()
            self._global_alerts.clear()
            self._build_agents()
            return {
                "status": "RESET",
                "fleet": self.repository.fleet_payload(),
                "network_summary": self.repository.network_payload()["summary"],
            }

    def _plan_task(self, task: DispatchTask) -> DispatchPlan:
        now = datetime.now().astimezone()
        task.status = MedicalTaskStatus.VALIDATING
        events = [
            self._event(
                task,
                "TASK_VALIDATED",
                "medical_dispatch_center",
                "任务字段、节点和载荷约束已完成基础校验。",
                task.status,
                {"priority_score": self.dispatch_agent.priority_score(task)},
                now,
            )
        ]
        alerts: List[DispatchAlert] = []

        task.status = MedicalTaskStatus.ROUTE_PLANNING
        route_plan = self.route_agent.plan(
            task.origin_node_id,
            task.destination_node_id,
            task.cargo.cargo_type,
        )
        events.append(
            self._event(
                task,
                "NETWORK_ROUTE_SELECTED",
                "network_route_agent",
                route_plan["network_explanation"],
                task.status,
                {
                    "route_ids": route_plan["route_ids"],
                    "node_path": route_plan["node_path"],
                    "selection_mode": route_plan["selection_mode"],
                },
            )
        )
        if route_plan["cargo_policy_mismatch_routes"]:
            alerts.append(
                self._alert(
                    task,
                    "CARGO_ROUTE_POLICY_REVIEW",
                    AlertLevel.ATTENTION,
                    "部分跨线航段并非该物资的常规班次，需要按应急或临时调拨流程确认。",
                    {
                        "route_ids": route_plan["cargo_policy_mismatch_routes"],
                    },
                )
            )

        ready_at = parse_datetime(task.ready_at, now) if task.ready_at else now
        start_time = max(now, ready_at)
        current_time = start_time
        task.status = MedicalTaskStatus.RESOURCE_RESERVING
        working_fleet = self.repository.fleet()
        legs: List[FlightLeg] = []
        reservations: List[Dict[str, Any]] = []
        relay_operations: List[Dict[str, Any]] = []
        primary_uav_ids: List[str] = []
        preferred_uav_id: Optional[str] = None

        segments = route_plan["segments"]
        try:
            for index, segment in enumerate(segments, start=1):
                leg_id = f"{task.task_id}-LEG-{index:02d}"
                allocation = self.fleet_agent.allocate_leg(
                    task,
                    segment,
                    working_fleet,
                    current_time,
                    preferred_uav_id,
                )
                departure_reservation = self.resource_agent.reserve(
                    node_id=segment.from_node,
                    resource_type="pad",
                    requested_start=allocation["available_start"],
                    duration_minutes=2.0,
                    task_id=task.task_id,
                    leg_id=leg_id,
                )
                reservations.append(departure_reservation)
                departure_time = parse_datetime(departure_reservation["end_time"])
                estimated_arrival = departure_time + timedelta(minutes=allocation["flight_minutes"])
                arrival_reservation = self.resource_agent.reserve(
                    node_id=segment.to_node,
                    resource_type="pad",
                    requested_start=estimated_arrival,
                    duration_minutes=2.0,
                    task_id=task.task_id,
                    leg_id=leg_id,
                )
                reservations.append(arrival_reservation)
                arrival_time = parse_datetime(arrival_reservation["start_time"])
                ground_clear_time = parse_datetime(arrival_reservation["end_time"])
                uav = working_fleet[allocation["uav_id"]]
                uav.available_at = isoformat(ground_clear_time)
                working_fleet[uav.uav_id] = uav
                if uav.uav_id not in primary_uav_ids:
                    primary_uav_ids.append(uav.uav_id)

                leg = FlightLeg(
                    leg_id=leg_id,
                    sequence=index,
                    route_id=segment.route_id,
                    segment_id=segment.segment_id,
                    from_node_id=segment.from_node,
                    to_node_id=segment.to_node,
                    distance_km=segment.distance_km,
                    cruise_altitude_m=min(segment.cruise_altitude_m, segment.max_altitude_m),
                    corridor_width_m=segment.corridor_width_m,
                    airspace_rule=segment.airspace_rule,
                    relay_required=segment.relay_required,
                    assigned_uav_id=uav.uav_id,
                    reposition_required=allocation["reposition_required"],
                    reposition_distance_km=allocation["reposition_distance_km"],
                    departure_time=isoformat(departure_time),
                    arrival_time=isoformat(arrival_time),
                    estimated_duration_minutes=round(
                        (arrival_time - departure_time).total_seconds() / 60.0,
                        2,
                    ),
                    estimated_energy_percent=allocation["energy_percent"],
                    node_operations=[
                        {"type": "departure_pad", "reservation": departure_reservation},
                        {"type": "arrival_pad", "reservation": arrival_reservation},
                    ],
                )
                legs.append(leg)
                events.append(
                    self._event(
                        task,
                        "UAV_ASSIGNED_TO_LEG",
                        "fleet_allocation_agent",
                        f"{uav.uav_id} 已分配至 {segment.segment_id}。",
                        task.status,
                        {
                            "leg_id": leg_id,
                            "uav_id": uav.uav_id,
                            "candidate_ranking": allocation["candidate_ranking"],
                            "reposition_required": allocation["reposition_required"],
                        },
                    )
                )

                next_distance = segments[index].distance_km if index < len(segments) else None
                relay_operation = self.relay_agent.plan(
                    task,
                    leg_id,
                    segment.to_node,
                    ground_clear_time,
                    uav,
                    next_distance,
                )
                if next_distance is not None:
                    relay_operations.append(relay_operation)
                    if relay_operation.get("resource_reservation"):
                        reservations.append(relay_operation["resource_reservation"])
                    current_time = parse_datetime(relay_operation["departure_time"])
                    events.append(
                        self._event(
                            task,
                            "RELAY_OPERATION_PLANNED",
                            "relay_operation_agent",
                            f"{self.nodes[segment.to_node].name} 已安排 {relay_operation['operation_type']}。",
                            MedicalTaskStatus.RELAY_ARRIVED,
                            relay_operation,
                        )
                    )
                else:
                    current_time = ground_clear_time
                working_fleet[uav.uav_id] = uav
                preferred_uav_id = uav.uav_id
        except Exception:
            self.resource_agent.release_task(task.task_id)
            raise

        total_minutes = round((current_time - start_time).total_seconds() / 60.0, 2)
        cold_chain = self.cold_chain_agent.evaluate_plan(
            task,
            total_minutes,
            route_plan["node_path"],
        )
        deadline_met = True
        if task.deadline:
            deadline_met = current_time <= parse_datetime(task.deadline)
        if not deadline_met:
            alerts.append(
                self._alert(
                    task,
                    "DELIVERY_DEADLINE_RISK",
                    AlertLevel.CRITICAL,
                    "预计到达时间超过医疗任务截止时间。",
                    {
                        "estimated_arrival_time": isoformat(current_time),
                        "deadline": task.deadline,
                    },
                )
            )
        if not cold_chain["feasible"]:
            alerts.append(
                self._alert(
                    task,
                    "COLD_CHAIN_PLAN_INFEASIBLE",
                    AlertLevel.CRITICAL,
                    "预计运输时长或接收节点能力不满足冷链约束。",
                    cold_chain,
                )
            )

        backup = self.fleet_agent.reserve_backup(
            task,
            working_fleet,
            primary_uav_ids,
            task.origin_node_id,
            start_time,
        )
        backup_uav_ids = [backup["uav_id"]] if backup else []
        if backup:
            for leg in legs:
                leg.backup_uav_id = backup["uav_id"]
            events.append(
                self._event(
                    task,
                    "BACKUP_UAV_RESERVED",
                    "fleet_allocation_agent",
                    f"{backup['uav_id']} 已作为任务备援机待命。",
                    task.status,
                    backup,
                )
            )

        critical = any(item.level == AlertLevel.CRITICAL for item in alerts)
        status = MedicalTaskStatus.BLOCKED if critical else MedicalTaskStatus.READY_FOR_DISPATCH
        task.status = status
        if critical:
            self.resource_agent.release_task(task.task_id)
        else:
            self.repository.update_fleet(working_fleet)
            events.append(
                self._event(
                    task,
                    "DISPATCH_PLAN_READY",
                    "medical_dispatch_center",
                    "多航段、机队、节点资源、中继和冷链约束已完成联合调度。",
                    status,
                    {
                        "primary_uav_ids": primary_uav_ids,
                        "backup_uav_ids": backup_uav_ids,
                    },
                )
            )

        plan = DispatchPlan(
            task=task,
            status=status,
            node_path=route_plan["node_path"],
            route_ids=route_plan["route_ids"],
            legs=legs,
            primary_uav_ids=primary_uav_ids,
            backup_uav_ids=backup_uav_ids,
            total_distance_km=route_plan["total_distance_km"],
            estimated_total_minutes=total_minutes,
            estimated_arrival_time=isoformat(current_time),
            deadline_met=deadline_met,
            cold_chain=cold_chain,
            resource_reservations=reservations,
            relay_operations=relay_operations,
            events=events,
            alerts=alerts,
            dispatch_summary={},
        )
        plan.dispatch_summary = self.dispatch_agent.build_summary(plan)
        self._plans[task.task_id] = plan
        self._global_alerts.extend(alerts)
        return plan

    def _build_task(self, payload: Dict[str, Any]) -> DispatchTask:
        task_id = str(payload.get("task_id") or f"MED-{uuid.uuid4().hex[:10].upper()}")
        cargo_type = str(payload.get("cargo_type") or "medical_supply")
        defaults = self._cargo_defaults(cargo_type)
        cold_chain_required = bool(payload.get("cold_chain_required", defaults["cold_chain_required"]))
        cargo = MedicalCargo(
            cargo_type=cargo_type,
            cargo_subtype=str(payload.get("cargo_subtype") or ""),
            weight_kg=float(payload.get("cargo_weight_kg", 0.0)),
            quantity=int(payload.get("quantity", 1)),
            temperature_min_c=self._optional_float(payload.get("temperature_min_c", defaults["temperature_min_c"])),
            temperature_max_c=self._optional_float(payload.get("temperature_max_c", defaults["temperature_max_c"])),
            cold_chain_required=cold_chain_required,
            cold_chain_safe_minutes=int(payload.get("cold_chain_safe_minutes", defaults["cold_chain_safe_minutes"])),
            seal_id=str(payload.get("seal_id") or f"SEAL-{task_id}"),
            biosafety_level=str(payload.get("biosafety_level") or "standard"),
        )
        origin = str(payload.get("origin_node_id") or "")
        destination = str(payload.get("destination_node_id") or "")
        if origin not in self.nodes:
            raise ValueError(f"unknown origin_node_id: {origin}")
        if destination not in self.nodes:
            raise ValueError(f"unknown destination_node_id: {destination}")
        if cargo.weight_kg <= 0:
            raise ValueError("cargo_weight_kg must be greater than zero")
        if cargo.weight_kg > 10:
            raise ValueError("cargo_weight_kg exceeds the 10kg medical UAV payload limit")
        priority = max(1, min(int(payload.get("priority", 3)), 5))
        now = datetime.now().astimezone()
        return DispatchTask(
            task_id=task_id,
            origin_node_id=origin,
            destination_node_id=destination,
            cargo=cargo,
            priority=priority,
            requested_at=str(payload.get("requested_at") or isoformat(now)),
            ready_at=str(payload.get("ready_at") or isoformat(now)),
            deadline=str(payload.get("deadline") or ""),
            emergency=bool(payload.get("emergency", priority >= 5)),
            allow_ground_feeder=bool(payload.get("allow_ground_feeder", True)),
            metadata=dict(payload.get("metadata") or {}),
        )

    def _alert(
        self,
        task: DispatchTask,
        alert_type: str,
        level: AlertLevel,
        message: str,
        details: Dict[str, Any],
    ) -> DispatchAlert:
        return DispatchAlert(
            alert_id=f"{task.task_id}-{alert_type}-{uuid.uuid4().hex[:6]}",
            task_id=task.task_id,
            level=level,
            alert_type=alert_type,
            message=message,
            recommended_actions=self.emergency_agent.recommend(alert_type),
            created_at=isoformat(datetime.now().astimezone()),
            details=details,
        )

    @staticmethod
    def _event(
        task: DispatchTask,
        event_type: str,
        actor: str,
        message: str,
        status: MedicalTaskStatus,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> DispatchEvent:
        return DispatchEvent(
            timestamp=isoformat(timestamp or datetime.now().astimezone()),
            event_type=event_type,
            task_id=task.task_id,
            actor=actor,
            message=message,
            status=status.value,
            details=details or {},
        )

    @staticmethod
    def _cargo_defaults(cargo_type: str) -> Dict[str, Any]:
        table = {
            "blood": {"cold_chain_required": True, "temperature_min_c": 2.0, "temperature_max_c": 6.0, "cold_chain_safe_minutes": 180},
            "blood_product": {"cold_chain_required": True, "temperature_min_c": 2.0, "temperature_max_c": 6.0, "cold_chain_safe_minutes": 180},
            "sample": {"cold_chain_required": True, "temperature_min_c": 2.0, "temperature_max_c": 8.0, "cold_chain_safe_minutes": 240},
            "pathology_sample": {"cold_chain_required": False, "temperature_min_c": None, "temperature_max_c": None, "cold_chain_safe_minutes": 240},
            "emergency_medicine": {"cold_chain_required": False, "temperature_min_c": None, "temperature_max_c": None, "cold_chain_safe_minutes": 240},
            "medicine": {"cold_chain_required": False, "temperature_min_c": None, "temperature_max_c": None, "cold_chain_safe_minutes": 360},
            "aed": {"cold_chain_required": False, "temperature_min_c": None, "temperature_max_c": None, "cold_chain_safe_minutes": 360},
            "trauma_supply": {"cold_chain_required": False, "temperature_min_c": None, "temperature_max_c": None, "cold_chain_safe_minutes": 360},
            "medical_supply": {"cold_chain_required": False, "temperature_min_c": None, "temperature_max_c": None, "cold_chain_safe_minutes": 360},
        }
        return table.get(cargo_type, table["medical_supply"])

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        return None if value is None or value == "" else float(value)
