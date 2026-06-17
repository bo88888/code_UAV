import unittest

from experiments.agent_scheduling_benchmark import (
    FailureModel,
    GEOGRAPHIC_PROFILES,
    POLICY_TEMPLATES,
    simulate_once,
)


class AgentSchedulingBenchmarkTests(unittest.TestCase):
    @staticmethod
    def _policy(name):
        return next(policy for policy in POLICY_TEMPLATES if policy.name == name)

    def test_simulation_is_deterministic_for_fixed_seed(self):
        policy = POLICY_TEMPLATES[-1]
        first = simulate_once(policy, 8, 0.08, seed=20260615)
        second = simulate_once(policy, 8, 0.08, seed=20260615)
        self.assertEqual(first, second)

    def test_parallel_capability_dag_reduces_makespan(self):
        serial = simulate_once(
            POLICY_TEMPLATES[0],
            mission_count=8,
            failure_probability=0.0,
            seed=100,
        )
        proposed = simulate_once(
            self._policy("Capability-DAG+Replan"),
            mission_count=8,
            failure_probability=0.0,
            seed=100,
        )
        self.assertLess(proposed["makespan_s"], serial["makespan_s"] * 0.4)
        self.assertEqual(proposed["success_rate"], 1.0)

    def test_capability_priority_improves_weighted_deadline_service(self):
        heft_recovery_weighted = []
        proposed_weighted = []
        for seed in range(20):
            heft_recovery_weighted.append(
                simulate_once(
                    self._policy("HEFT-DAG+Recovery"),
                    mission_count=12,
                    failure_probability=0.20,
                    seed=seed,
                )["priority_weighted_on_time_rate"]
            )
            proposed_weighted.append(
                simulate_once(
                    self._policy("Capability-DAG+Replan"),
                    mission_count=12,
                    failure_probability=0.20,
                    seed=seed,
                )["priority_weighted_on_time_rate"]
            )
        self.assertGreaterEqual(
            sum(proposed_weighted),
            sum(heft_recovery_weighted),
        )

    def test_recovery_controlled_baselines_are_registered(self):
        expected = {
            "Parallel-FIFO+Recovery": "fifo",
            "HEFT-DAG+Recovery": "heft",
            "RL-DAG+Recovery": "rl",
        }
        for name, order in expected.items():
            policy = self._policy(name)
            self.assertEqual(policy.order, order)
            self.assertTrue(policy.use_fallback)
            self.assertTrue(policy.capability_aware_retry)

    def test_capability_recovery_improves_heft_under_failures(self):
        base_success = []
        recovery_success = []
        for seed in range(20):
            base_success.append(
                simulate_once(
                    self._policy("HEFT-DAG"),
                    mission_count=12,
                    failure_probability=0.20,
                    seed=seed,
                )["success_rate"]
            )
            recovery_success.append(
                simulate_once(
                    self._policy("HEFT-DAG+Recovery"),
                    mission_count=12,
                    failure_probability=0.20,
                    seed=seed,
                )["success_rate"]
            )
        self.assertGreaterEqual(sum(recovery_success), sum(base_success))

    def test_correlated_failure_simulation_is_deterministic(self):
        model = FailureModel(
            name="correlated",
            correlation_strength=0.75,
            window_s=4.0,
        )
        first = simulate_once(
            self._policy("Capability-DAG+Replan"),
            mission_count=12,
            failure_probability=0.12,
            seed=77,
            failure_model=model,
        )
        second = simulate_once(
            self._policy("Capability-DAG+Replan"),
            mission_count=12,
            failure_probability=0.12,
            seed=77,
            failure_model=model,
        )
        self.assertEqual(first, second)

    def test_geographic_profile_changes_execution_distribution(self):
        policy = self._policy("Capability-DAG+Replan")
        new_york = simulate_once(
            policy,
            mission_count=12,
            failure_probability=0.10,
            seed=123,
            geographic_profile=GEOGRAPHIC_PROFILES[0],
        )
        san_francisco = simulate_once(
            policy,
            mission_count=12,
            failure_probability=0.10,
            seed=123,
            geographic_profile=GEOGRAPHIC_PROFILES[2],
        )
        self.assertNotEqual(new_york["makespan_s"], san_francisco["makespan_s"])


if __name__ == "__main__":
    unittest.main()
