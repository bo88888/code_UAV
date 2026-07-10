from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from agents.cold_chain_agent import ColdChainAgent
from agents.emergency_response_agent import EmergencyResponseAgent
from core.medical_models import AlertLevel, DispatchAlert, DispatchPlan, DispatchTask, isoformat


class FlightMonitorAgent:
    """Evaluates RemoteID, route, battery, communication, altitude and cold-chain telemetry."""

    def __init__(
        self,
        cold_chain_agent: ColdChainAgent,
        emergency_agent: EmergencyResponseAgent,
    ) -> None:
        self.cold_chain_agent = cold_chain_agent
        self.emergency_agent = emergency_agent

    def evaluate(
        self,
        task: DispatchTask,
        plan: DispatchPlan,
        telemetry: Dict[str, Any],
    ) -> List[DispatchAlert]:
        now = datetime.now().astimezone()
        alerts: List[DispatchAlert] = []
        route_deviation_m = float(telemetry.get("route_deviation_m", 0.0) or 0.0)
        battery_percent = float(telemetry.get("battery_percent", 100.0) or 0.0)
        communication_ok = bool(telemetry.get("communication_ok", True))
        remote_id_ok = bool(telemetry.get("remote_id_ok", True))
        altitude_m = float(telemetry.get("altitude_m", 0.0) or 0.0)
        allowed_altitude_m = self._allowed_altitude(plan, telemetry)

        if route_deviation_m >= 10.0:
            alerts.append(
                self._alert(
                    task.task_id,
                    "ROUTE_DEVIATION",
                    AlertLevel.RESTRICTED if route_deviation_m < 30 else AlertLevel.CRITICAL,
                    f"航线偏离 {route_deviation_m:.1f}m，超过10m监控阈值。",
                    now,
                    {"route_deviation_m": route_deviation_m},
                )
            )
        if battery_percent < 20.0:
            alerts.append(
                self._alert(
                    task.task_id,
                    "LOW_BATTERY",
                    AlertLevel.CRITICAL,
                    f"无人机电量 {battery_percent:.1f}%，低于20%安全阈值。",
                    now,
                    {"battery_percent": battery_percent},
                )
            )
        if not communication_ok:
            alerts.append(
                self._alert(
                    task.task_id,
                    "COMMUNICATION_LOST",
                    AlertLevel.CRITICAL,
                    "5G-A主通信链路异常，需要切换北斗备份链路。",
                    now,
                    {"communication_ok": False},
                )
            )
        if not remote_id_ok:
            alerts.append(
                self._alert(
                    task.task_id,
                    "REMOTE_ID_MISSING",
                    AlertLevel.RESTRICTED,
                    "RemoteID身份或状态广播缺失。",
                    now,
                    {"remote_id_ok": False},
                )
            )
        if allowed_altitude_m > 0 and altitude_m > allowed_altitude_m:
            alerts.append(
                self._alert(
                    task.task_id,
                    "ALTITUDE_VIOLATION",
                    AlertLevel.CRITICAL,
                    f"当前高度 {altitude_m:.1f}m 超过航段限高 {allowed_altitude_m:.1f}m。",
                    now,
                    {"altitude_m": altitude_m, "allowed_altitude_m": allowed_altitude_m},
                )
            )
        temperature_alert = self.cold_chain_agent.evaluate_temperature(
            task,
            telemetry.get("temperature_c"),
            now,
        )
        if temperature_alert:
            alerts.append(self.emergency_agent.enrich(temperature_alert))
        return alerts

    def _alert(
        self,
        task_id: str,
        alert_type: str,
        level: AlertLevel,
        message: str,
        now: datetime,
        details: Dict[str, Any],
    ) -> DispatchAlert:
        alert = DispatchAlert(
            alert_id=f"{task_id}-{alert_type}-{int(now.timestamp())}",
            task_id=task_id,
            level=level,
            alert_type=alert_type,
            message=message,
            recommended_actions=[],
            created_at=isoformat(now),
            details=details,
        )
        return self.emergency_agent.enrich(alert)

    @staticmethod
    def _allowed_altitude(plan: DispatchPlan, telemetry: Dict[str, Any]) -> float:
        leg_id = telemetry.get("leg_id")
        if leg_id:
            for leg in plan.legs:
                if leg.leg_id == leg_id:
                    return leg.cruise_altitude_m
        if plan.legs:
            return max(item.cruise_altitude_m for item in plan.legs)
        return 0.0
