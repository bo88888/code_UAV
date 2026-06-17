import unittest

from experiments.algorithm_comparison import (
    build_local_registry,
    run_comparison,
    run_local_mission,
)
from agents.orchestrator_agent import OrchestratorAgent
from config import REQUIREMENT_XML_PATH
from core.schema import ExecutionContext, TaskRequest


class LowAltitudePipelineTests(unittest.IsolatedAsyncioTestCase):
    def test_requirement_parsing_and_dag(self):
        context = ExecutionContext(
            request=TaskRequest(
                task_id="TEST_DAG",
                requirement_xml_path=REQUIREMENT_XML_PATH,
            )
        )
        context = OrchestratorAgent(build_local_registry()).prepare(context)
        self.assertEqual(context.parsed_requirement["cargo_weight_kg"], 2.5)
        self.assertEqual(
            context.parsed_requirement["mission_type"], "emergency_medical"
        )
        self.assertEqual(
            [len(batch["tasks"]) for batch in context.plan_rationale],
            [4, 4, 1, 1],
        )

    async def test_normal_mission_selects_feasible_solution(self):
        context = await run_local_mission("normal")
        self.assertEqual(
            context.final_report["mission_status"], "READY_FOR_DISPATCH"
        )
        self.assertEqual(
            len(context.metadata["candidate_dispatch_solutions"]), 4
        )
        self.assertTrue(
            context.metadata["final_dispatch_solution"]["time_window_met"]
        )

    async def test_airspace_restriction_triggers_ground_fallback(self):
        context = await run_local_mission("airspace_restricted")
        self.assertIn(
            "fallback_selected",
            [event["event"] for event in context.replan_events],
        )
        self.assertEqual(
            context.metadata["final_dispatch_solution"][
                "assigned_vehicle_type"
            ],
            "ground_vehicle",
        )

    async def test_uav_wait_and_retry_recovers_medical_scheduler(self):
        context = await run_local_mission("no_available_uav_once")
        self.assertIn(
            "wait_and_retry",
            [event["event"] for event in context.replan_events],
        )
        medical = context.tool_results["ROUTE_MED_01"]
        self.assertTrue(medical.success)
        self.assertEqual(medical.output["solver_status"], "OPTIMAL")

    async def test_persistent_uav_shortage_falls_back_to_ground(self):
        context = await run_local_mission("no_available_uav")
        self.assertEqual(
            context.final_report["mission_status"], "READY_FOR_DISPATCH"
        )
        self.assertEqual(
            context.metadata["final_dispatch_solution"][
                "assigned_vehicle_type"
            ],
            "ground_vehicle",
        )
        actions = [event["event"] for event in context.replan_events]
        self.assertIn("fallback_selected", actions)
        self.assertIn("skip", actions)

    async def test_algorithm_comparison(self):
        result = await run_comparison()
        self.assertEqual(
            result["orchestration_result"]["mission_success_rate"], 1.0
        )
        self.assertGreater(
            result["scheduling_comparison"]["speedup"], 2.0
        )
        self.assertIn(
            "TWA-MILP Medical Scheduler", result["algorithm_results"]
        )


if __name__ == "__main__":
    unittest.main()
