import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

from agents.orchestrator_agent import OrchestratorAgent
from agents.postprocess_agent import PostprocessAgent
from agents.replan_agent import ReplanDecisionAgent
from agents.report_agent import ReportAgent
from config import REQUIREMENT_XML_PATH, TOOL_SERVICE_MAP
from core.schema import ExecutionContext, TaskRequest, ToolResult
from mcp.registry import ToolRegistry
from mcp.wrapper import MCPWrapper
from scheduler.scheduler_center import IntelligentScheduler
from services.low_altitude_service.app import infer


class LocalLowAltitudeInvoker:
    """Run the same MCP payloads in-process for deterministic experiments."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def invoke_many(self, context, subtasks):
        results = []
        for task in subtasks:
            capability = self.registry.get_capability(task.tool_name)
            request = MCPWrapper.build_request(
                context, task, capability.output_schema
            )
            response = infer(
                {
                    "task_id": request.task_id,
                    "subtask_id": request.subtask_id,
                    "tool_name": request.tool_name,
                    "input_data": request.input_data,
                    "parameters": request.parameters,
                    "output_schema": request.output_schema,
                }
            )
            results.append(
                ToolResult(
                    subtask_id=response["subtask_id"],
                    tool_name=response["tool_name"],
                    success=response["success"],
                    output=response["output"],
                    message=response.get("message", ""),
                )
            )
        await asyncio.sleep(0)
        return results


def build_local_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_name in TOOL_SERVICE_MAP:
        registry.register(tool_name, "local://low-altitude")
    return registry


async def run_local_mission(
    scenario: str = "normal",
    requirement_xml_path: str = REQUIREMENT_XML_PATH,
) -> ExecutionContext:
    request = TaskRequest(
        task_id=f"EXPERIMENT_{scenario.upper()}",
        requirement_xml_path=requirement_xml_path,
        output_requirements={
            "format": "json",
            "need_orchestration_trace": True,
        },
    )
    context = ExecutionContext(request=request)
    registry = build_local_registry()
    context = OrchestratorAgent(registry).prepare(
        context, overrides={"simulation_scenario": scenario}
    )
    scheduler = IntelligentScheduler(
        LocalLowAltitudeInvoker(registry), ReplanDecisionAgent()
    )
    context = await scheduler.run_async(context)
    context = PostprocessAgent().run(context)
    return ReportAgent().run(context)


def _round_mean(values: Iterable[float]) -> float:
    values = list(values)
    return round(mean(values), 3) if values else 0.0


def _scheduling_comparison() -> Dict[str, Any]:
    latency_ms = {
        "AIR_01": 80,
        "WEA_01": 100,
        "UAV_01": 70,
        "DOCK_01": 60,
        "ROUTE_COMP_01": 180,
        "ROUTE_WEA_01": 160,
        "ROUTE_MED_01": 140,
        "ROUTE_AGENT_01": 150,
        "RISK_01": 90,
        "REPORT_01": 50,
    }
    serial = sum(latency_ms.values())
    dag = (
        max(latency_ms[key] for key in ("AIR_01", "WEA_01", "UAV_01", "DOCK_01"))
        + max(
            latency_ms[key]
            for key in (
                "ROUTE_COMP_01",
                "ROUTE_WEA_01",
                "ROUTE_MED_01",
                "ROUTE_AGENT_01",
            )
        )
        + latency_ms["RISK_01"]
        + latency_ms["REPORT_01"]
    )
    return {
        "model": "deterministic_service_latency",
        "serial_makespan_ms": serial,
        "capability_dag_makespan_ms": dag,
        "speedup": round(serial / dag, 3),
        "parallel_time_saved_percent": round((serial - dag) / serial * 100, 2),
    }


def _scenario_algorithm_metrics(
    candidates: List[Dict[str, Any]],
    risk_factors: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Keep one comparable record per algorithm for plotting."""

    metrics: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        algorithm = candidate["algorithm_used"]
        if algorithm in metrics:
            continue

        is_ground = candidate.get("assigned_vehicle_type") == "ground_vehicle"
        air_risk = any(
            factor in {"temporary_airspace_restriction", "adverse_weather"}
            for factor in risk_factors
        )
        effective_feasible = bool(
            candidate.get("time_window_met", True)
            and (not air_risk or is_ground)
        )
        metrics[algorithm] = {
            "duration_mins": round(
                float(candidate.get("estimated_duration_mins", 0.0)), 3
            ),
            "energy_kj": round(
                float(candidate.get("estimated_energy_kj", 0.0)), 3
            ),
            "compliance_score": round(
                float(candidate.get("compliance_score", 0.0)), 3
            ),
            "time_window_met": bool(
                candidate.get("time_window_met", True)
            ),
            "effective_feasible": effective_feasible,
            "vehicle_type": candidate.get(
                "assigned_vehicle_type", "uav"
            ),
        }
    return metrics


async def run_comparison(
    scenarios: List[str] = None,
) -> Dict[str, Any]:
    scenarios = scenarios or [
        "normal",
        "bad_weather",
        "airspace_restricted",
        "no_available_uav_once",
    ]
    contexts = [await run_local_mission(scenario) for scenario in scenarios]
    aggregate: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "runs": 0,
            "deadline_met": 0,
            "selected": 0,
            "durations": [],
            "energies": [],
            "compliance": [],
        }
    )
    scenario_results = []

    for scenario, context in zip(scenarios, contexts):
        candidates = context.metadata.get("candidate_dispatch_solutions", [])
        selected = context.metadata.get("final_dispatch_solution", {})
        risk_assessment = context.final_report.get("risk_assessment", {})
        seen_algorithms = set()
        for candidate in candidates:
            algorithm = candidate["algorithm_used"]
            if algorithm in seen_algorithms:
                continue
            seen_algorithms.add(algorithm)
            metrics = aggregate[algorithm]
            metrics["runs"] += 1
            metrics["deadline_met"] += int(
                candidate.get("time_window_met", True)
            )
            metrics["selected"] += int(
                candidate.get("subtask_id") == selected.get("subtask_id")
            )
            metrics["durations"].append(
                float(candidate.get("estimated_duration_mins", 0.0))
            )
            metrics["energies"].append(
                float(candidate.get("estimated_energy_kj", 0.0))
            )
            metrics["compliance"].append(
                float(candidate.get("compliance_score", 0.0))
            )

        scenario_results.append(
            {
                "scenario": scenario,
                "mission_status": context.final_report["mission_status"],
                "selected_algorithm": selected.get("algorithm_used", ""),
                "selected_vehicle": selected.get(
                    "assigned_vehicle_type", "uav"
                ),
                "risk_level": context.final_report.get(
                    "risk_assessment", {}
                ).get("risk_level"),
                "risk_factors": risk_assessment.get("risk_factors", []),
                "algorithm_metrics": _scenario_algorithm_metrics(
                    candidates,
                    risk_assessment.get("risk_factors", []),
                ),
                "replan_actions": [
                    event.get("event") for event in context.replan_events
                ],
            }
        )

    algorithm_results = {}
    for algorithm, metrics in aggregate.items():
        algorithm_results[algorithm] = {
            "scenario_success_rate": round(
                metrics["runs"] / len(scenarios), 3
            ),
            "deadline_met_rate": round(
                metrics["deadline_met"] / max(metrics["runs"], 1), 3
            ),
            "selected_count": metrics["selected"],
            "average_duration_mins": _round_mean(metrics["durations"]),
            "average_energy_kj": _round_mean(metrics["energies"]),
            "average_compliance_score": _round_mean(metrics["compliance"]),
        }

    return {
        "experiment": "low_altitude_multi_algorithm_comparison",
        "scenarios": scenario_results,
        "algorithm_results": algorithm_results,
        "orchestration_result": {
            "mission_success_rate": round(
                sum(
                    item["mission_status"] == "READY_FOR_DISPATCH"
                    for item in scenario_results
                )
                / len(scenario_results),
                3,
            ),
            "fallback_scenarios": sum(
                "fallback_selected" in item["replan_actions"]
                for item in scenario_results
            ),
            "wait_retry_scenarios": sum(
                "wait_and_retry" in item["replan_actions"]
                for item in scenario_results
            ),
        },
        "scheduling_comparison": _scheduling_comparison(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="outputs/algorithm_comparison.json",
        help="JSON output path",
    )
    args = parser.parse_args()
    result = asyncio.run(run_comparison())
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
