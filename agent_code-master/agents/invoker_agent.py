from typing import Dict, List

from clients.async_http_client import AsyncHTTPClient
from core.schema import ExecutionContext, SubTask, ToolResult
from mcp.registry import ToolRegistry
from mcp.wrapper import MCPWrapper


class InvokerAgent:
    """Invoke low-altitude tools through the MCP-style HTTP protocol."""

    def __init__(self, registry: ToolRegistry, timeout: int = 60):
        self.registry = registry
        self.client = AsyncHTTPClient(timeout=timeout)

    def output_schema(self, tool_name: str) -> List[str]:
        try:
            return list(self.registry.get_capability(tool_name).output_schema)
        except KeyError:
            pass

        schema_map: Dict[str, List[str]] = {
            "airspace_check_service": [
                "is_clear",
                "no_fly_zones",
                "altitude_limit_m",
            ],
            "weather_check_service": [
                "wind_speed_mps",
                "precipitation_mm_h",
                "visibility_km",
                "is_flyable",
            ],
            "uav_status_service": [
                "available_uavs",
                "fleet_readiness",
                "capacity_satisfied",
            ],
            "dock_status_service": [
                "available_docks",
                "charging_slots",
                "estimated_turnaround_mins",
            ],
            "compliance_route_service": [
                "waypoints_3d",
                "flight_distance_km",
                "estimated_duration_mins",
                "estimated_energy_kj",
                "compliance_score",
                "collision_risk",
            ],
            "weather_adaptive_dispatch_service": [
                "assigned_vehicle_type",
                "adjusted_route",
                "weather_delay_mins",
                "estimated_duration_mins",
                "estimated_energy_kj",
                "time_window_met",
            ],
            "medical_time_window_scheduler_service": [
                "uav_id",
                "dispatch_sequence",
                "eta",
                "time_window_met",
                "estimated_duration_mins",
                "estimated_energy_kj",
            ],
            "agentic_task_allocation_service": [
                "assignments",
                "task_coverage_rate",
                "response_time_mins",
                "reallocation_count",
                "estimated_energy_kj",
                "time_window_met",
            ],
            "risk_assessment_service": [
                "risk_level",
                "risk_score",
                "dispatch_allowed",
                "recommended_subtask_id",
                "risk_factors",
            ],
            "dispatch_report_service": [
                "mission_status",
                "dispatch_brief",
                "command_actions",
            ],
        }
        return schema_map.get(tool_name, [])

    async def invoke_one(
        self, context: ExecutionContext, subtask: SubTask
    ) -> ToolResult:
        request = MCPWrapper.build_request(
            context, subtask, self.output_schema(subtask.tool_name)
        )
        service_url = self.registry.get(subtask.tool_name)
        response = await self.client.post_mcp(service_url, request)
        return ToolResult(
            subtask_id=response.subtask_id,
            tool_name=response.tool_name,
            success=response.success,
            output=response.output,
            confidence=response.confidence,
            message=response.message,
        )

    async def invoke_many(
        self, context: ExecutionContext, subtasks: List[SubTask]
    ):
        return await self.client.gather(
            self.invoke_one(context, task) for task in subtasks
        )
