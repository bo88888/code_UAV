from typing import List

from core.schema import ExecutionContext, SubTask
from mcp.protocol import MCPRequest


class MCPWrapper:
    """Build a protocol request with mission semantics and upstream outputs."""

    @staticmethod
    def build_request(
        context: ExecutionContext,
        subtask: SubTask,
        output_schema: List[str],
    ) -> MCPRequest:
        previous_results = {
            subtask_id: result.output
            for subtask_id, result in context.tool_results.items()
            if result.success
        }

        return MCPRequest(
            task_id=context.request.task_id,
            subtask_id=subtask.subtask_id,
            tool_name=subtask.tool_name,
            input_data={
                "mission": context.parsed_requirement,
                "xml_config": context.parsed_requirement,
                "delivery_points": context.parsed_requirement.get(
                    "delivery_points", []
                ),
                "cargo_weight_kg": context.parsed_requirement.get(
                    "cargo_weight_kg", 0.0
                ),
                "priority": context.parsed_requirement.get("priority", 1),
                "environmental_constraints": context.parsed_requirement.get(
                    "environmental_constraints", {}
                ),
                "previous_results": previous_results,
                "metadata": context.metadata,
                "orchestration": {
                    "stage": subtask.stage,
                    "capability_id": subtask.capability_id,
                    "reason": subtask.reason,
                    "optional": subtask.optional,
                    "dependencies": subtask.dependencies,
                },
            },
            parameters=subtask.parameters,
            output_schema=output_schema,
        )
