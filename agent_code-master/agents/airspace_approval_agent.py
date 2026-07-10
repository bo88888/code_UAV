from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable

from core.medical_models import MedicalRoute, isoformat


class AirspaceApprovalAgent:
    """Evaluates fixed-corridor approval requirements without pretending to call a regulator."""

    def __init__(self, routes: Dict[str, MedicalRoute]) -> None:
        self.routes = routes

    def evaluate(
        self,
        route_ids: Iterable[str],
        priority: int,
        emergency: bool,
        external_status: str = "",
    ) -> Dict[str, Any]:
        selected = [self.routes[item] for item in route_ids if item in self.routes]
        rules = sorted({item.airspace_rule for item in selected})
        requires_controlled_approval = any(
            "limited" in rule or "controlled" in rule or "airport" in rule
            for rule in rules
        )
        normalized = external_status.strip().upper()
        if normalized == "DENIED":
            status = "DENIED"
            dispatch_allowed = False
        elif normalized == "APPROVED":
            status = "APPROVED_BY_EXTERNAL_SYSTEM"
            dispatch_allowed = True
        elif emergency or priority >= 5:
            status = "FAST_TRACK_SIMULATION_PENDING_CONFIRMATION"
            dispatch_allowed = True
        elif requires_controlled_approval:
            status = "FIXED_CORRIDOR_SIMULATION_PENDING_CONFIRMATION"
            dispatch_allowed = True
        else:
            status = "ROUTINE_CORRIDOR_SIMULATION"
            dispatch_allowed = True

        now = datetime.now().astimezone()
        return {
            "status": status,
            "dispatch_allowed": dispatch_allowed,
            "route_ids": [item.route_id for item in selected],
            "airspace_rules": rules,
            "requires_controlled_approval": requires_controlled_approval,
            "fast_track": emergency or priority >= 5,
            "evaluated_at": isoformat(now),
            "simulation_valid_until": isoformat(now + timedelta(minutes=30)),
            "production_notice": "当前仅生成审批需求与模拟状态；正式运行必须对接真实低空监管或飞行服务系统。",
        }
