from typing import Dict, Iterable, List, Optional, Tuple

from core.schema import ExecutionContext, SubTask
from core.tool_capabilities import DEFAULT_TOOL_CAPABILITIES, ToolCapability


ENV_TASK_IDS = {
    "airspace_check_service": "AIR_01",
    "weather_check_service": "WEA_01",
    "uav_status_service": "UAV_01",
    "dock_status_service": "DOCK_01",
}

ROUTE_TASK_IDS = {
    "compliance_route_service": "ROUTE_COMP_01",
    "weather_adaptive_dispatch_service": "ROUTE_WEA_01",
    "medical_time_window_scheduler_service": "ROUTE_MED_01",
    "agentic_task_allocation_service": "ROUTE_AGENT_01",
}


class DecomposeAgent:
    """Build the low-altitude environment, routing, risk, and report DAG."""

    def __init__(self, registry=None):
        self.registry = registry

    def _capabilities(self) -> Iterable[ToolCapability]:
        if self.registry is not None:
            return self.registry.list_capabilities().values()
        return DEFAULT_TOOL_CAPABILITIES

    def _is_registered(self, tool_name: str) -> bool:
        return self.registry is None or self.registry.has_tool(tool_name)

    def _capability(self, tool_name: str) -> Optional[ToolCapability]:
        for capability in self._capabilities():
            if capability.tool_name == tool_name:
                return capability
        return None

    def _matching_capabilities(self, stage: str, mode: str) -> List[ToolCapability]:
        return [
            capability
            for capability in self._capabilities()
            if capability.stage == stage
            and mode in capability.modes
            and self._is_registered(capability.tool_name)
        ]

    def _build_task(
        self,
        subtask_id: str,
        capability: ToolCapability,
        dependencies: Optional[List[str]] = None,
        parameters: Optional[Dict] = None,
        reason: str = "",
    ) -> SubTask:
        return SubTask(
            subtask_id=subtask_id,
            name=capability.display_name,
            tool_name=capability.tool_name,
            dependencies=dependencies or [],
            parameters=parameters or {},
            stage=capability.stage,
            capability_id=capability.capability_id,
            reason=reason,
            optional=capability.optional,
            fallback_tools=list(capability.fallback_tools),
            max_retry=capability.max_retry,
        )

    def _build_env_check_tasks(
        self, context: ExecutionContext, mode: str
    ) -> Tuple[List[SubTask], Dict[str, str]]:
        tasks = []
        task_by_tool = {}
        for capability in self._matching_capabilities("environment_check", mode):
            subtask_id = ENV_TASK_IDS[capability.tool_name]
            tasks.append(
                self._build_task(
                    subtask_id,
                    capability,
                    reason="并行执行起飞前环境、设备与保障资源检查。",
                )
            )
            task_by_tool[capability.tool_name] = subtask_id
        return tasks, task_by_tool

    def _route_dependencies(
        self, capability: ToolCapability, env_task_by_tool: Dict[str, str]
    ) -> List[str]:
        return [
            env_task_by_tool[tool_name]
            for tool_name in capability.requires_environment
            if tool_name in env_task_by_tool
        ]

    def _build_routing_tasks(
        self,
        context: ExecutionContext,
        mode: str,
        env_task_by_tool: Dict[str, str],
    ) -> List[SubTask]:
        mission_type = context.parsed_requirement.get("mission_type")
        selected_tools = [
            "compliance_route_service",
            "weather_adaptive_dispatch_service",
            "agentic_task_allocation_service",
        ]
        if mission_type == "emergency_medical":
            selected_tools.insert(2, "medical_time_window_scheduler_service")

        reasons = {
            "compliance_route_service": "生成 DRL-LLM 合规、能耗感知的基准航线。",
            "weather_adaptive_dispatch_service": "生成动态气象下的空地协同备选方案。",
            "medical_time_window_scheduler_service": "医疗急件需要 TWA-MILP 严格时间窗调度。",
            "agentic_task_allocation_service": "使用 CoordField 形成异构无人机任务分配对比方案。",
        }

        tasks = []
        for tool_name in selected_tools:
            capability = self._capability(tool_name)
            if capability is None or not self._is_registered(tool_name):
                context.skipped_tools.append(
                    {
                        "tool_name": tool_name,
                        "stage": "route_planning",
                        "reason": "capability or service is not registered",
                    }
                )
                continue
            tasks.append(
                self._build_task(
                    ROUTE_TASK_IDS[tool_name],
                    capability,
                    dependencies=self._route_dependencies(
                        capability, env_task_by_tool
                    ),
                    reason=reasons[tool_name],
                )
            )
        return tasks

    def _build_risk_task(
        self, context: ExecutionContext, mode: str, route_task_ids: List[str]
    ) -> List[SubTask]:
        capabilities = self._matching_capabilities("risk_assessment", mode)
        if not capabilities:
            context.metadata["decompose_error"] = (
                "risk_assessment_service is not registered"
            )
            return []
        return [
            self._build_task(
                "RISK_01",
                capabilities[0],
                dependencies=route_task_ids,
                reason="融合各论文算法输出，评估合规、气象、时效和能耗风险。",
            )
        ]

    def _build_report_task(
        self, context: ExecutionContext, mode: str, risk_task_ids: List[str]
    ) -> List[SubTask]:
        capabilities = self._matching_capabilities("report", mode)
        if not capabilities:
            context.metadata["decompose_error"] = (
                "dispatch_report_service is not registered"
            )
            return []
        return [
            self._build_task(
                "REPORT_01",
                capabilities[0],
                dependencies=risk_task_ids,
                reason="根据风险评估结果生成指挥中心任务保障摘要。",
            )
        ]

    def run(self, context: ExecutionContext) -> ExecutionContext:
        context.metadata["decompose_strategy"] = "low_altitude_capability_dag_v1"
        context.skipped_tools = []
        mode = context.parsed_requirement.get(
            "dispatch_mode", "intelligent_coordination"
        )

        env_tasks, env_task_by_tool = self._build_env_check_tasks(context, mode)
        route_tasks = self._build_routing_tasks(context, mode, env_task_by_tool)
        risk_tasks = self._build_risk_task(
            context, mode, [task.subtask_id for task in route_tasks]
        )
        report_tasks = self._build_report_task(
            context, mode, [task.subtask_id for task in risk_tasks]
        )
        context.subtasks = env_tasks + route_tasks + risk_tasks + report_tasks
        return context
