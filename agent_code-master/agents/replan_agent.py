from dataclasses import dataclass

from core.schema import ExecutionContext, SubTask


@dataclass
class ReplanDecision:
    action: str
    reason: str
    fallback_tool: str = ""
    retry_delay_seconds: float = 0.0


class ReplanDecisionAgent:
    """Low-altitude recovery policy for airspace, weather, and fleet failures."""

    def decide(
        self,
        context: ExecutionContext,
        task: SubTask,
        message: str,
        registry,
    ) -> ReplanDecision:
        lowered = (message or "").lower()

        if (
            task.tool_name == "compliance_route_service"
            and "airspace restricted" in lowered
            and registry.has_tool("weather_adaptive_dispatch_service")
        ):
            return ReplanDecision(
                action="fallback",
                fallback_tool="weather_adaptive_dispatch_service",
                reason=(
                    "airspace restriction triggered immediate fallback to "
                    "air-ground collaborative dispatch"
                ),
            )

        if (
            task.tool_name == "medical_time_window_scheduler_service"
            and "no available uav" in lowered
            and task.retry_count < task.max_retry
        ):
            return ReplanDecision(
                action="wait_and_retry",
                reason="wait for a medical UAV to return to an available dock",
                retry_delay_seconds=float(
                    task.parameters.get("retry_delay_seconds", 0.05)
                ),
            )

        if task.retry_count < task.max_retry:
            return ReplanDecision(
                action="retry",
                reason=f"retry budget available after failure: {message}",
            )

        for fallback_tool in task.fallback_tools:
            if registry.has_tool(fallback_tool):
                return ReplanDecision(
                    action="fallback",
                    fallback_tool=fallback_tool,
                    reason=f"fallback tool {fallback_tool} is registered",
                )

        if task.optional:
            return ReplanDecision(
                action="skip",
                reason=f"optional task failed and can be skipped: {message}",
            )

        return ReplanDecision(
            action="fail",
            reason=f"required task failed after retry budget: {message}",
        )
