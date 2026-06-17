from core.schema import ExecutionContext


class ReportAgent:
    def _assess_quality(self, context: ExecutionContext) -> dict:
        issues = list(context.metadata.get("input_validation_issues", []))
        task_summary = []

        for task in context.subtasks:
            message = (
                context.metadata.get(f"error_{task.subtask_id}")
                or context.metadata.get(f"last_error_{task.subtask_id}")
                or context.metadata.get(f"blocked_{task.subtask_id}", {}).get(
                    "reason", ""
                )
            )
            task_summary.append(
                {
                    "subtask_id": task.subtask_id,
                    "name": task.name,
                    "tool_name": task.tool_name,
                    "stage": task.stage,
                    "status": task.status.value,
                    "retry_count": task.retry_count,
                    "dependencies": task.dependencies,
                    "reason": task.reason,
                    "optional": task.optional,
                    "message": message,
                }
            )
            if task.status.value in {"FAILED", "BLOCKED"} and not task.optional:
                issues.append(f"{task.subtask_id} {task.status.value.lower()}")

        solution = context.metadata.get("final_dispatch_solution", {})
        risk = context.tool_results.get("RISK_01")
        dispatch_allowed = bool(
            risk and risk.success and risk.output.get("dispatch_allowed", False)
        )
        if not solution:
            issues.append("no feasible dispatch solution")
        if not dispatch_allowed:
            issues.append("risk assessment did not authorize dispatch")

        return {
            "pass": len(issues) == 0,
            "issues": issues,
            "task_summary": task_summary,
        }

    def run(self, context: ExecutionContext) -> ExecutionContext:
        context.quality_report = self._assess_quality(context)
        report_tool = context.tool_results.get("REPORT_01")
        risk_tool = context.tool_results.get("RISK_01")
        mission_ready = context.quality_report["pass"]

        context.final_report = {
            "code": 200 if mission_ready else 409,
            "msg": "任务已具备派发条件" if mission_ready else "任务需人工复核或继续重规划",
            "task_id": context.request.task_id,
            "mission_status": "READY_FOR_DISPATCH"
            if mission_ready
            else "BLOCKED",
            "mission": context.parsed_requirement,
            "recommended_solution": context.metadata.get(
                "final_dispatch_solution", {}
            ),
            "candidate_solutions": context.metadata.get(
                "candidate_dispatch_solutions", []
            ),
            "risk_assessment": risk_tool.output
            if risk_tool and risk_tool.success
            else {},
            "dispatch_brief": report_tool.output
            if report_tool and report_tool.success
            else {},
            "execution_status": context.quality_report,
            "orchestration": {
                "plan": context.plan_rationale,
                "trace": context.execution_trace,
                "replan_events": context.replan_events,
                "skipped": context.skipped_tools,
            },
        }
        return context
