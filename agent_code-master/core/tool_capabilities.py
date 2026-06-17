from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ToolCapability:
    """Describes a callable low-altitude service and its recovery policy."""

    tool_name: str
    display_name: str
    stage: str
    modes: List[str]
    output_schema: List[str]
    requires_environment: List[str] = field(default_factory=list)
    optional: bool = False
    fallback_tools: List[str] = field(default_factory=list)
    failure_strategy: str = "fail"
    max_retry: int = 1

    @property
    def capability_id(self) -> str:
        return self.tool_name


DEFAULT_TOOL_CAPABILITIES: List[ToolCapability] = [
    ToolCapability(
        tool_name="airspace_check_service",
        display_name="空域与禁飞区合规校验",
        stage="environment_check",
        modes=["intelligent_coordination", "standard_flight", "bad_weather_mode"],
        output_schema=["is_clear", "no_fly_zones", "altitude_limit_m"],
    ),
    ToolCapability(
        tool_name="weather_check_service",
        display_name="气象风险与风力评估",
        stage="environment_check",
        modes=["intelligent_coordination", "standard_flight", "bad_weather_mode"],
        output_schema=[
            "wind_speed_mps",
            "precipitation_mm_h",
            "visibility_km",
            "is_flyable",
        ],
    ),
    ToolCapability(
        tool_name="uav_status_service",
        display_name="无人机载重、电量与健康状态检查",
        stage="environment_check",
        modes=["intelligent_coordination", "standard_flight", "bad_weather_mode"],
        output_schema=["available_uavs", "fleet_readiness", "capacity_satisfied"],
    ),
    ToolCapability(
        tool_name="dock_status_service",
        display_name="机巢与充换电资源检查",
        stage="environment_check",
        modes=["intelligent_coordination", "standard_flight", "bad_weather_mode"],
        output_schema=["available_docks", "charging_slots", "estimated_turnaround_mins"],
    ),
    ToolCapability(
        tool_name="compliance_route_service",
        display_name="DRL-LLM 合规航线规划",
        stage="route_planning",
        modes=["intelligent_coordination", "standard_flight", "bad_weather_mode"],
        output_schema=[
            "waypoints_3d",
            "flight_distance_km",
            "estimated_duration_mins",
            "estimated_energy_kj",
            "compliance_score",
            "collision_risk",
        ],
        requires_environment=[
            "airspace_check_service",
            "weather_check_service",
            "uav_status_service",
        ],
        fallback_tools=["weather_adaptive_dispatch_service"],
    ),
    ToolCapability(
        tool_name="weather_adaptive_dispatch_service",
        display_name="NN 气象自适应空地协同调度",
        stage="route_planning",
        modes=["intelligent_coordination", "bad_weather_mode"],
        output_schema=[
            "assigned_vehicle_type",
            "adjusted_route",
            "weather_delay_mins",
            "estimated_duration_mins",
            "estimated_energy_kj",
            "time_window_met",
        ],
        requires_environment=["weather_check_service", "uav_status_service"],
    ),
    ToolCapability(
        tool_name="medical_time_window_scheduler_service",
        display_name="TWA-MILP 医疗时间窗调度",
        stage="route_planning",
        modes=["intelligent_coordination", "bad_weather_mode"],
        output_schema=[
            "uav_id",
            "dispatch_sequence",
            "eta",
            "time_window_met",
            "estimated_duration_mins",
            "estimated_energy_kj",
        ],
        requires_environment=["uav_status_service", "dock_status_service"],
        fallback_tools=["weather_adaptive_dispatch_service"],
        max_retry=2,
    ),
    ToolCapability(
        tool_name="agentic_task_allocation_service",
        display_name="CoordField 智能体任务分配",
        stage="route_planning",
        modes=["intelligent_coordination", "bad_weather_mode"],
        output_schema=[
            "assignments",
            "task_coverage_rate",
            "response_time_mins",
            "reallocation_count",
            "estimated_energy_kj",
            "time_window_met",
        ],
        requires_environment=["uav_status_service", "weather_check_service"],
        optional=True,
        failure_strategy="skip",
    ),
    ToolCapability(
        tool_name="risk_assessment_service",
        display_name="多方案综合风险评估",
        stage="risk_assessment",
        modes=["intelligent_coordination", "standard_flight", "bad_weather_mode"],
        output_schema=[
            "risk_level",
            "risk_score",
            "dispatch_allowed",
            "recommended_subtask_id",
            "risk_factors",
        ],
    ),
    ToolCapability(
        tool_name="dispatch_report_service",
        display_name="任务保障摘要生成",
        stage="report",
        modes=["intelligent_coordination", "standard_flight", "bad_weather_mode"],
        output_schema=["mission_status", "dispatch_brief", "command_actions"],
    ),
]


DEFAULT_TOOL_CAPABILITY_MAP: Dict[str, ToolCapability] = {
    capability.tool_name: capability for capability in DEFAULT_TOOL_CAPABILITIES
}
