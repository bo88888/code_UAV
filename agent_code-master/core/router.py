from typing import Dict, List

from core.schema import SubTask
from core.tool_capabilities import DEFAULT_TOOL_CAPABILITY_MAP


ENVIRONMENT_TASKS = {
    "AIR_01": "airspace_check_service",
    "WEA_01": "weather_check_service",
    "UAV_01": "uav_status_service",
    "DOCK_01": "dock_status_service",
}

ROUTING_TASKS = {
    "ROUTE_COMP_01": "compliance_route_service",
    "ROUTE_WEA_01": "weather_adaptive_dispatch_service",
    "ROUTE_MED_01": "medical_time_window_scheduler_service",
    "ROUTE_AGENT_01": "agentic_task_allocation_service",
}


def _task(
    subtask_id: str,
    tool_name: str,
    dependencies: List[str],
    reason: str,
) -> SubTask:
    capability = DEFAULT_TOOL_CAPABILITY_MAP[tool_name]
    return SubTask(
        subtask_id=subtask_id,
        name=capability.display_name,
        tool_name=tool_name,
        dependencies=dependencies,
        stage=capability.stage,
        capability_id=capability.capability_id,
        reason=reason,
        optional=capability.optional,
        fallback_tools=list(capability.fallback_tools),
        max_retry=capability.max_retry,
    )


def build_low_altitude_tasks(requirement: Dict) -> List[SubTask]:
    """Compatibility helper that builds the default low-altitude DAG."""

    tasks = [
        _task(task_id, tool_name, [], "起飞前并行检查")
        for task_id, tool_name in ENVIRONMENT_TASKS.items()
    ]
    dependencies_by_tool = {
        tool_name: task_id
        for task_id, tool_name in ENVIRONMENT_TASKS.items()
    }

    route_ids = []
    for task_id, tool_name in ROUTING_TASKS.items():
        if (
            tool_name == "medical_time_window_scheduler_service"
            and requirement.get("mission_type") != "emergency_medical"
        ):
            continue
        capability = DEFAULT_TOOL_CAPABILITY_MAP[tool_name]
        dependencies = [
            dependencies_by_tool[name]
            for name in capability.requires_environment
        ]
        tasks.append(
            _task(task_id, tool_name, dependencies, "生成候选配送方案")
        )
        route_ids.append(task_id)

    tasks.append(
        _task(
            "RISK_01",
            "risk_assessment_service",
            route_ids,
            "融合候选方案并评估风险",
        )
    )
    tasks.append(
        _task(
            "REPORT_01",
            "dispatch_report_service",
            ["RISK_01"],
            "生成任务保障摘要",
        )
    )
    return tasks
