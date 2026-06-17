from typing import Any, Dict, List

from core.schema import ExecutionContext


ALGORITHM_NAMES = {
    "compliance_route_service": "DRL-LLM Compliance Trajectory",
    "weather_adaptive_dispatch_service": "NN Weather-Adaptive Air-Ground",
    "medical_time_window_scheduler_service": "TWA-MILP Medical Scheduler",
    "agentic_task_allocation_service": "CoordField Agentic Allocation",
}


def _solution_score(output: Dict[str, Any]) -> float:
    feasible = output.get("time_window_met", True)
    compliance = float(output.get("compliance_score", 0.85))
    energy = float(output.get("estimated_energy_kj", 600.0))
    delay = float(output.get("weather_delay_mins", 0.0))
    coverage = float(output.get("task_coverage_rate", 1.0))
    return round(
        (50.0 if feasible else 0.0)
        + compliance * 25.0
        + coverage * 15.0
        - min(energy / 100.0, 10.0)
        - min(delay, 15.0),
        3,
    )


class PostprocessAgent:
    """Rank route/scheduling candidates and choose a dispatch solution."""

    def run(self, context: ExecutionContext) -> ExecutionContext:
        candidates: List[Dict[str, Any]] = []
        for subtask_id, result in context.tool_results.items():
            if not result.success or result.tool_name not in ALGORITHM_NAMES:
                continue
            candidate = dict(result.output)
            candidate.update(
                {
                    "subtask_id": subtask_id,
                    "tool_name": result.tool_name,
                    "algorithm_used": ALGORITHM_NAMES[result.tool_name],
                }
            )
            candidate["solution_score"] = _solution_score(candidate)
            candidates.append(candidate)

        candidates.sort(key=lambda item: item["solution_score"], reverse=True)
        final_solution = dict(candidates[0]) if candidates else {}

        risk_result = context.tool_results.get("RISK_01")
        if risk_result and risk_result.success:
            recommended_id = risk_result.output.get("recommended_subtask_id")
            recommended = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate["subtask_id"] == recommended_id
                ),
                None,
            )
            if recommended is not None:
                final_solution = dict(recommended)

        context.metadata["candidate_dispatch_solutions"] = candidates
        context.metadata["final_dispatch_solution"] = final_solution
        context.metadata["postprocess_summary"] = {
            "candidate_count": len(candidates),
            "selected_subtask_id": final_solution.get("subtask_id", ""),
            "selected_algorithm": final_solution.get("algorithm_used", ""),
        }
        return context
