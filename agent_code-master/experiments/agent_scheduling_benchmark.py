import argparse
import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "agent_scheduling_benchmark.json"
GEOGRAPHIC_DATA = ROOT / "data" / "geographic_benchmarks.json"


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    dependencies: Tuple[str, ...]
    mean_duration_s: float
    failure_weight: float = 1.0
    optional: bool = False
    fallback_available: bool = False


@dataclass(frozen=True)
class SchedulingPolicy:
    name: str
    order: str
    workers: int
    retry_limit: int
    use_fallback: bool
    skip_optional: bool
    capability_aware_retry: bool = False
    learned_weights: Tuple[float, ...] = ()


@dataclass(frozen=True)
class FailureModel:
    name: str = "independent"
    correlation_strength: float = 0.0
    window_s: float = 4.0
    common_cause_multiplier: float = 1.0


@dataclass(frozen=True)
class GeographicProfile:
    profile_id: str
    label: str
    pickup_name: str
    pickup_latitude: float
    pickup_longitude: float
    delivery_name: str
    delivery_latitude: float
    delivery_longitude: float
    weather_station: str
    mean_wind_mps: float
    p90_wind_mps: float
    wet_hour_fraction: float
    route_distance_km: float
    arrival_interval_multiplier: float
    deadline_multiplier: float


@dataclass
class TaskState:
    status: str = "pending"
    attempts: int = 0
    ready_after_s: float = 0.0
    using_fallback: bool = False


@dataclass
class WorkflowState:
    workflow_id: int
    arrival_s: float
    deadline_s: float
    urgency: int
    tasks: Dict[str, TaskState]
    failed: bool = False
    completed: bool = False
    completion_s: Optional[float] = None
    had_failure: bool = False
    recovery_events: int = 0


TASK_SPECS: Tuple[TaskSpec, ...] = (
    TaskSpec("A1_airspace", (), 0.80, 1.15),
    TaskSpec("A2_weather", (), 1.00, 1.25),
    TaskSpec("A3_uav", (), 0.70, 1.00),
    TaskSpec("A4_dock", (), 0.60, 0.80),
    TaskSpec(
        "B1_compliance",
        ("A1_airspace", "A2_weather", "A3_uav"),
        1.80,
        1.20,
        fallback_available=True,
    ),
    TaskSpec(
        "B2_air_ground",
        ("A2_weather", "A3_uav"),
        1.60,
        0.90,
    ),
    TaskSpec(
        "B3_medical",
        ("A3_uav", "A4_dock"),
        1.40,
        1.10,
        fallback_available=True,
    ),
    TaskSpec(
        "B4_coordfield",
        ("A2_weather", "A3_uav"),
        1.50,
        1.00,
        optional=True,
    ),
    TaskSpec(
        "C1_risk",
        (
            "B1_compliance",
            "B2_air_ground",
            "B3_medical",
            "B4_coordfield",
        ),
        0.90,
        0.75,
    ),
    TaskSpec("R1_report", ("C1_risk",), 0.50, 0.55),
)
TASK_MAP = {spec.task_id: spec for spec in TASK_SPECS}
TASK_INDEX = {spec.task_id: index for index, spec in enumerate(TASK_SPECS)}
MAX_UPWARD_RANK = sum(spec.mean_duration_s for spec in TASK_SPECS)
RECOVERY_DEADLINE_GUARD_S = 0.20
RECOVERY_MAX_DEADLINE_OVERRUN_S = 2.00

FAILURE_CLUSTERS = {
    "A1_airspace": "airspace",
    "A2_weather": "weather",
    "A3_uav": "infrastructure",
    "A4_dock": "infrastructure",
    "B1_compliance": "weather",
    "B2_air_ground": "network",
    "B3_medical": "infrastructure",
    "B4_coordfield": "network",
    "C1_risk": "network",
    "R1_report": "network",
}

POLICY_TEMPLATES: Tuple[SchedulingPolicy, ...] = (
    SchedulingPolicy(
        "Serial-FIFO",
        order="fifo",
        workers=1,
        retry_limit=0,
        use_fallback=False,
        skip_optional=False,
    ),
    SchedulingPolicy(
        "Parallel-FIFO",
        order="fifo",
        workers=4,
        retry_limit=1,
        use_fallback=False,
        skip_optional=True,
    ),
    SchedulingPolicy(
        "HEFT-DAG",
        order="heft",
        workers=4,
        retry_limit=1,
        use_fallback=False,
        skip_optional=True,
    ),
    SchedulingPolicy(
        "RL-DAG",
        order="rl",
        workers=4,
        retry_limit=1,
        use_fallback=False,
        skip_optional=True,
        learned_weights=(1.0, 1.0, 1.0, 0.2, 0.2),
    ),
    SchedulingPolicy(
        "Parallel-FIFO+Recovery",
        order="fifo",
        workers=4,
        retry_limit=1,
        use_fallback=True,
        skip_optional=True,
        capability_aware_retry=True,
    ),
    SchedulingPolicy(
        "HEFT-DAG+Recovery",
        order="heft",
        workers=4,
        retry_limit=1,
        use_fallback=True,
        skip_optional=True,
        capability_aware_retry=True,
    ),
    SchedulingPolicy(
        "RL-DAG+Recovery",
        order="rl",
        workers=4,
        retry_limit=1,
        use_fallback=True,
        skip_optional=True,
        capability_aware_retry=True,
        learned_weights=(1.0, 1.0, 1.0, 0.2, 0.2),
    ),
    SchedulingPolicy(
        "Capability-DAG+Replan",
        order="proposed",
        workers=4,
        retry_limit=1,
        use_fallback=True,
        skip_optional=True,
        capability_aware_retry=True,
    ),
)

ABLATION_POLICIES: Tuple[SchedulingPolicy, ...] = (
    POLICY_TEMPLATES[-1],
    SchedulingPolicy(
        "w/o parallelism",
        order="proposed",
        workers=1,
        retry_limit=1,
        use_fallback=True,
        skip_optional=True,
        capability_aware_retry=True,
    ),
    SchedulingPolicy(
        "w/o replanning",
        order="proposed",
        workers=4,
        retry_limit=0,
        use_fallback=False,
        skip_optional=False,
    ),
    SchedulingPolicy(
        "w/o fallback",
        order="proposed",
        workers=4,
        retry_limit=1,
        use_fallback=False,
        skip_optional=True,
        capability_aware_retry=True,
    ),
    SchedulingPolicy(
        "w/o urgency priority",
        order="heft",
        workers=4,
        retry_limit=1,
        use_fallback=True,
        skip_optional=True,
        capability_aware_retry=True,
    ),
)


def _upward_ranks() -> Dict[str, float]:
    successors: Dict[str, List[str]] = {
        spec.task_id: [] for spec in TASK_SPECS
    }
    for spec in TASK_SPECS:
        for dependency in spec.dependencies:
            successors[dependency].append(spec.task_id)

    ranks: Dict[str, float] = {}

    def calculate(task_id: str) -> float:
        if task_id in ranks:
            return ranks[task_id]
        tail = max(
            (calculate(successor) for successor in successors[task_id]),
            default=0.0,
        )
        ranks[task_id] = TASK_MAP[task_id].mean_duration_s + tail
        return ranks[task_id]

    for spec in TASK_SPECS:
        calculate(spec.task_id)
    return ranks


UPWARD_RANKS = _upward_ranks()


def _haversine_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    radius_km = 6371.0088
    lat_1 = math.radians(latitude_1)
    lat_2 = math.radians(latitude_2)
    delta_lat = lat_2 - lat_1
    delta_lon = math.radians(longitude_2 - longitude_1)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(value))


def load_geographic_profiles() -> Tuple[GeographicProfile, ...]:
    payload = json.loads(GEOGRAPHIC_DATA.read_text(encoding="utf-8"))
    profiles = []
    for item in payload["profiles"]:
        pickup = item["pickup"]
        delivery = item["delivery"]
        profiles.append(
            GeographicProfile(
                profile_id=item["id"],
                label=item["label"],
                pickup_name=pickup["name"],
                pickup_latitude=pickup["latitude"],
                pickup_longitude=pickup["longitude"],
                delivery_name=delivery["name"],
                delivery_latitude=delivery["latitude"],
                delivery_longitude=delivery["longitude"],
                weather_station=item["weather_station"],
                mean_wind_mps=item["mean_wind_mps"],
                p90_wind_mps=item["p90_wind_mps"],
                wet_hour_fraction=item["wet_hour_fraction"],
                route_distance_km=_haversine_km(
                    pickup["latitude"],
                    pickup["longitude"],
                    delivery["latitude"],
                    delivery["longitude"],
                ),
                arrival_interval_multiplier=item[
                    "arrival_interval_multiplier"
                ],
                deadline_multiplier=item["deadline_multiplier"],
            )
        )
    return tuple(profiles)


GEOGRAPHIC_PROFILES = load_geographic_profiles()


def _sample_duration(
    rng: random.Random,
    spec: TaskSpec,
    using_fallback: bool,
    geographic_profile: Optional[GeographicProfile] = None,
) -> float:
    multiplier = 1.28 if using_fallback else 1.0
    if geographic_profile is not None:
        distance_factor = min(
            1.35,
            max(0.85, 0.90 + geographic_profile.route_distance_km / 30.0),
        )
        wind_factor = 1.0 + max(
            0.0,
            geographic_profile.p90_wind_mps - 8.0,
        ) * 0.018
        if spec.task_id.startswith("B"):
            multiplier *= distance_factor * wind_factor
        elif spec.task_id in {"A2_weather", "C1_risk"}:
            multiplier *= 1.0 + geographic_profile.wet_hour_fraction * 0.25
    sampled = rng.gauss(spec.mean_duration_s * multiplier, 0.13 * spec.mean_duration_s)
    return max(0.12, sampled)


def _event_rng(
    seed: int,
    workflow_id: int,
    task_id: str,
    attempt: int,
    using_fallback: bool,
) -> random.Random:
    stable_task_code = sum(
        (index + 1) * ord(character)
        for index, character in enumerate(task_id)
    )
    event_seed = (
        seed * 1_000_003
        + workflow_id * 10_007
        + stable_task_code * 313
        + attempt * 17
        + int(using_fallback) * 97
    )
    return random.Random(event_seed)


def _shared_failure_shock(
    seed: int,
    cluster: str,
    now_s: float,
    failure_probability: float,
    model: FailureModel,
) -> bool:
    if model.name != "correlated" or model.correlation_strength <= 0:
        return False
    cluster_code = sum(
        (index + 1) * ord(character)
        for index, character in enumerate(cluster)
    )
    window_index = int(now_s / max(model.window_s, 0.1))
    shock_rng = random.Random(
        seed * 1_000_033 + cluster_code * 1009 + window_index * 65_537
    )
    shock_probability = min(
        0.95,
        failure_probability
        * model.correlation_strength
        * model.common_cause_multiplier,
    )
    return shock_rng.random() < shock_probability


def _event_failed(
    event_rng: random.Random,
    seed: int,
    task_id: str,
    now_s: float,
    failure_probability: float,
    using_fallback: bool,
    model: FailureModel,
) -> bool:
    spec = TASK_MAP[task_id]
    residual_probability = min(
        0.95,
        failure_probability
        * spec.failure_weight
        * (1.0 - 0.70 * model.correlation_strength)
        * (0.45 if using_fallback else 1.0),
    )
    if event_rng.random() < residual_probability:
        return True
    cluster = FAILURE_CLUSTERS[task_id]
    if not _shared_failure_shock(
        seed,
        cluster,
        now_s,
        failure_probability,
        model,
    ):
        return False
    exposure = 0.25 if using_fallback else 0.92
    if cluster == "network" and task_id == "B2_air_ground":
        exposure *= 0.65
    return event_rng.random() < exposure


def _retry_limit(policy: SchedulingPolicy, task_id: str) -> int:
    if policy.capability_aware_retry:
        if task_id == "B3_medical":
            return 2
        if TASK_MAP[task_id].optional:
            return 0
    return policy.retry_limit


def _deadline_guard(
    workflow: "WorkflowState",
    task_id: str,
    now_s: float,
    delay_s: float,
    using_fallback: bool,
    allow_late: bool = False,
) -> bool:
    remaining_s = UPWARD_RANKS[task_id]
    if using_fallback:
        remaining_s += TASK_MAP[task_id].mean_duration_s * 0.28
    deadline_s = (
        workflow.deadline_s + RECOVERY_MAX_DEADLINE_OVERRUN_S
        if allow_late
        else workflow.deadline_s - RECOVERY_DEADLINE_GUARD_S
    )
    return now_s + delay_s + remaining_s <= deadline_s


def _build_workflows(
    mission_count: int,
    rng: random.Random,
    geographic_profile: Optional[GeographicProfile] = None,
) -> List[WorkflowState]:
    workflows = []
    arrival_multiplier = (
        geographic_profile.arrival_interval_multiplier
        if geographic_profile is not None
        else 1.0
    )
    deadline_multiplier = (
        geographic_profile.deadline_multiplier
        if geographic_profile is not None
        else 1.0
    )
    for workflow_id in range(mission_count):
        arrival_s = (
            workflow_id * 1.20 * arrival_multiplier
            + rng.uniform(-0.10, 0.10)
        )
        arrival_s = max(0.0, arrival_s)
        urgency_roll = rng.random()
        if urgency_roll < 0.25:
            urgency, slack = 3, 7.5 * deadline_multiplier
        elif urgency_roll < 0.65:
            urgency, slack = 2, 10.0 * deadline_multiplier
        else:
            urgency, slack = 1, 13.0 * deadline_multiplier
        workflows.append(
            WorkflowState(
                workflow_id=workflow_id,
                arrival_s=arrival_s,
                deadline_s=arrival_s + slack,
                urgency=urgency,
                tasks={spec.task_id: TaskState() for spec in TASK_SPECS},
            )
        )
    return workflows


def _task_ready(
    workflow: WorkflowState,
    task_id: str,
    now_s: float,
) -> bool:
    task = workflow.tasks[task_id]
    if task.status != "pending":
        return False
    if now_s + 1e-9 < max(workflow.arrival_s, task.ready_after_s):
        return False
    return all(
        workflow.tasks[dependency].status in {"success", "skipped"}
        for dependency in TASK_MAP[task_id].dependencies
    )


def _priority_key(
    policy: SchedulingPolicy,
    workflow: WorkflowState,
    task_id: str,
    now_s: float,
) -> Tuple[float, ...]:
    if policy.order == "heft":
        return (
            workflow.arrival_s,
            -UPWARD_RANKS[task_id],
            float(workflow.workflow_id),
            float(TASK_INDEX[task_id]),
        )
    if policy.order == "proposed":
        task = workflow.tasks[task_id]
        recovery_active = 0.0 if task.attempts > 0 or task.using_fallback else 1.0
        urgency_adjusted_deadline = workflow.deadline_s - 2.50 * workflow.urgency
        return (
            recovery_active,
            urgency_adjusted_deadline,
            -float(workflow.urgency),
            -UPWARD_RANKS[task_id],
            workflow.arrival_s,
            float(TASK_INDEX[task_id]),
        )
    if policy.order == "rl":
        task = workflow.tasks[task_id]
        weights = policy.learned_weights or (1.0, 1.0, 1.0, 0.2, 0.2)
        slack_feature = -max(-1.0, min(2.0, (workflow.deadline_s - now_s) / 13.0))
        features = (
            slack_feature,
            workflow.urgency / 3.0,
            UPWARD_RANKS[task_id] / MAX_UPWARD_RANK,
            -TASK_MAP[task_id].mean_duration_s / 1.8,
            min(task.attempts, 2) / 2.0,
        )
        score = sum(weight * feature for weight, feature in zip(weights, features))
        return (
            -score,
            workflow.arrival_s,
            float(workflow.workflow_id),
            float(TASK_INDEX[task_id]),
        )
    return (
        workflow.arrival_s,
        float(workflow.workflow_id),
        float(TASK_INDEX[task_id]),
    )


def _fail_workflow(
    workflow: WorkflowState,
    now_s: float,
    running: List[Dict[str, Any]],
) -> None:
    workflow.failed = True
    workflow.completion_s = now_s
    for task in workflow.tasks.values():
        if task.status in {"pending", "running"}:
            task.status = "cancelled"
    running[:] = [
        item
        for item in running
        if item["workflow_id"] != workflow.workflow_id
    ]


def simulate_once(
    policy: SchedulingPolicy,
    mission_count: int,
    failure_probability: float,
    seed: int,
    workers_override: Optional[int] = None,
    failure_model: Optional[FailureModel] = None,
    geographic_profile: Optional[GeographicProfile] = None,
) -> Dict[str, float]:
    model = failure_model or FailureModel()
    rng = random.Random(seed)
    workflows = _build_workflows(
        mission_count,
        rng,
        geographic_profile=geographic_profile,
    )
    capacity_workers = (
        workers_override if workers_override is not None else policy.workers
    )
    workers = capacity_workers
    if policy.name == "Serial-FIFO":
        workers = 1

    now_s = 0.0
    running: List[Dict[str, Any]] = []
    busy_time_s = 0.0
    scheduling_decisions = 0

    while not all(workflow.completed or workflow.failed for workflow in workflows):
        if running:
            next_finish = min(item["finish_s"] for item in running)
            if next_finish <= now_s + 1e-9:
                finishing = [
                    item
                    for item in running
                    if abs(item["finish_s"] - next_finish) <= 1e-9
                ]
                running[:] = [
                    item
                    for item in running
                    if abs(item["finish_s"] - next_finish) > 1e-9
                ]
                for item in finishing:
                    workflow = workflows[item["workflow_id"]]
                    if workflow.failed:
                        continue
                    task = workflow.tasks[item["task_id"]]
                    if item["failed"]:
                        workflow.had_failure = True
                        retry_limit = _retry_limit(policy, item["task_id"])
                        retry_delay_s = 0.12 * task.attempts
                        fallback_delay_s = 0.18
                        can_retry_on_time = (
                            not task.using_fallback
                            and task.attempts <= retry_limit
                            and _deadline_guard(
                                workflow,
                                item["task_id"],
                                now_s,
                                retry_delay_s,
                                using_fallback=False,
                            )
                        )
                        can_fallback_on_time = (
                            not task.using_fallback
                            and policy.use_fallback
                            and TASK_MAP[item["task_id"]].fallback_available
                            and _deadline_guard(
                                workflow,
                                item["task_id"],
                                now_s,
                                fallback_delay_s,
                                using_fallback=True,
                            )
                        )
                        can_retry_late = (
                            not task.using_fallback
                            and task.attempts <= retry_limit
                            and _deadline_guard(
                                workflow,
                                item["task_id"],
                                now_s,
                                retry_delay_s,
                                using_fallback=False,
                                allow_late=True,
                            )
                        )
                        can_fallback_late = (
                            not task.using_fallback
                            and policy.use_fallback
                            and TASK_MAP[item["task_id"]].fallback_available
                            and _deadline_guard(
                                workflow,
                                item["task_id"],
                                now_s,
                                fallback_delay_s,
                                using_fallback=True,
                                allow_late=True,
                            )
                        )
                        if can_retry_on_time:
                            task.status = "pending"
                            task.ready_after_s = now_s + retry_delay_s
                            workflow.recovery_events += 1
                        elif can_fallback_on_time or can_fallback_late:
                            task.status = "pending"
                            task.using_fallback = True
                            task.attempts = 0
                            task.ready_after_s = now_s + fallback_delay_s
                            workflow.recovery_events += 1
                        elif can_retry_late:
                            task.status = "pending"
                            task.ready_after_s = now_s + retry_delay_s
                            workflow.recovery_events += 1
                        elif (
                            TASK_MAP[item["task_id"]].optional
                            and policy.skip_optional
                        ):
                            task.status = "skipped"
                            workflow.recovery_events += 1
                        else:
                            task.status = "failed"
                            _fail_workflow(workflow, now_s, running)
                    else:
                        task.status = "success"
                        if item["task_id"] == "R1_report":
                            workflow.completed = True
                            workflow.completion_s = now_s
                continue

        ready: List[Tuple[WorkflowState, str]] = []
        for workflow in workflows:
            if workflow.failed or workflow.completed:
                continue
            for spec in TASK_SPECS:
                if _task_ready(workflow, spec.task_id, now_s):
                    ready.append((workflow, spec.task_id))

        free_workers = workers - len(running)
        if ready and free_workers > 0:
            ready.sort(
                key=lambda item: _priority_key(
                    policy,
                    item[0],
                    item[1],
                    now_s,
                )
            )
            for workflow, task_id in ready[:free_workers]:
                task = workflow.tasks[task_id]
                spec = TASK_MAP[task_id]
                task.status = "running"
                task.attempts += 1
                event_rng = _event_rng(
                    seed,
                    workflow.workflow_id,
                    task_id,
                    task.attempts,
                    task.using_fallback,
                )
                duration_s = _sample_duration(
                    event_rng,
                    spec,
                    task.using_fallback,
                    geographic_profile=geographic_profile,
                )
                running.append(
                    {
                        "finish_s": now_s + duration_s,
                        "workflow_id": workflow.workflow_id,
                        "task_id": task_id,
                        "failed": _event_failed(
                            event_rng,
                            seed,
                            task_id,
                            now_s,
                            failure_probability,
                            task.using_fallback,
                            model,
                        ),
                    }
                )
                busy_time_s += duration_s
                scheduling_decisions += 1
            continue

        future_times = [item["finish_s"] for item in running]
        for workflow in workflows:
            if workflow.failed or workflow.completed:
                continue
            if workflow.arrival_s > now_s + 1e-9:
                future_times.append(workflow.arrival_s)
            for task in workflow.tasks.values():
                if task.status == "pending" and task.ready_after_s > now_s + 1e-9:
                    future_times.append(task.ready_after_s)
        if not future_times:
            break
        now_s = min(future_times)

    terminal_times = [
        workflow.completion_s or now_s for workflow in workflows
    ]
    makespan_s = max(terminal_times, default=0.0)
    successes = [workflow for workflow in workflows if workflow.completed]
    on_time = [
        workflow
        for workflow in successes
        if (workflow.completion_s or math.inf) <= workflow.deadline_s
    ]
    total_urgency_weight = sum(workflow.urgency for workflow in workflows)
    on_time_urgency_weight = sum(workflow.urgency for workflow in on_time)
    recovery_cases = [
        workflow for workflow in workflows if workflow.had_failure
    ]
    recovered = [
        workflow for workflow in recovery_cases if workflow.completed
    ]
    completion_latencies = [
        (workflow.completion_s or now_s) - workflow.arrival_s
        for workflow in successes
    ]
    penalized_latencies = []
    for workflow in workflows:
        elapsed = (workflow.completion_s or now_s) - workflow.arrival_s
        if workflow.completed:
            penalized_latencies.append(elapsed)
        else:
            deadline_slack = workflow.deadline_s - workflow.arrival_s
            penalized_latencies.append(max(elapsed, 3.0 * deadline_slack))

    return {
        "makespan_s": makespan_s,
        "success_rate": len(successes) / mission_count,
        "on_time_rate": len(on_time) / mission_count,
        "priority_weighted_on_time_rate": (
            on_time_urgency_weight / total_urgency_weight
            if total_urgency_weight
            else 0.0
        ),
        "throughput_per_min": (
            len(successes) / makespan_s * 60.0 if makespan_s else 0.0
        ),
        "utilization": (
            min(1.0, busy_time_s / (capacity_workers * makespan_s))
            if makespan_s
            else 0.0
        ),
        "mean_latency_s": (
            mean(completion_latencies) if completion_latencies else makespan_s
        ),
        "failure_penalized_latency_s": mean(penalized_latencies),
        "recovery_success_rate": (
            len(recovered) / len(recovery_cases)
            if recovery_cases
            else 1.0
        ),
        "recovery_case_rate": len(recovery_cases) / mission_count,
        "mean_recovery_events": (
            mean(workflow.recovery_events for workflow in workflows)
            if workflows
            else 0.0
        ),
        "scheduling_decisions": float(scheduling_decisions),
    }


def _summary(values: Iterable[float]) -> Dict[str, float]:
    samples = list(values)
    average = mean(samples) if samples else 0.0
    deviation = stdev(samples) if len(samples) > 1 else 0.0
    return {
        "mean": round(average, 5),
        "std": round(deviation, 5),
        "ci95": round(1.96 * deviation / math.sqrt(max(len(samples), 1)), 5),
        "n": len(samples),
    }


def _run_trials(
    policy: SchedulingPolicy,
    mission_count: int,
    failure_probability: float,
    trials: int,
    seed_base: int,
    workers_override: Optional[int] = None,
    failure_model: Optional[FailureModel] = None,
    geographic_profile: Optional[GeographicProfile] = None,
) -> Dict[str, Dict[str, float]]:
    runs = [
        simulate_once(
            policy,
            mission_count,
            failure_probability,
            seed=seed_base + trial * 104729,
            workers_override=workers_override,
            failure_model=failure_model,
            geographic_profile=geographic_profile,
        )
        for trial in range(trials)
    ]
    return {
        metric: _summary(run[metric] for run in runs)
        for metric in runs[0]
    }


def _copy_policy(policy: SchedulingPolicy, workers: int) -> SchedulingPolicy:
    return SchedulingPolicy(
        name=policy.name,
        order=policy.order,
        workers=workers,
        retry_limit=policy.retry_limit,
        use_fallback=policy.use_fallback,
        skip_optional=policy.skip_optional,
        capability_aware_retry=policy.capability_aware_retry,
        learned_weights=policy.learned_weights,
    )


def _rl_reward(metrics: Dict[str, float]) -> float:
    return (
        4.0 * metrics["success_rate"]
        + 3.0 * metrics["priority_weighted_on_time_rate"]
        - 0.025 * metrics["failure_penalized_latency_s"]
        - 0.004 * metrics["makespan_s"]
    )


def train_rl_policy(
    seed: int,
    generations: int = 7,
    population: int = 10,
) -> Tuple[SchedulingPolicy, Dict[str, Any]]:
    template = next(
        policy for policy in POLICY_TEMPLATES if policy.name == "RL-DAG"
    )
    optimizer_rng = random.Random(seed + 71_001_337)
    center = list(template.learned_weights)
    spread = [0.75 for _ in center]
    training_cases = (
        (8, 0.02),
        (12, 0.08),
        (16, 0.14),
    )
    evaluations = 0

    for generation in range(generations):
        candidates = []
        for candidate_index in range(population):
            weights = tuple(
                optimizer_rng.gauss(center[index], spread[index])
                for index in range(len(center))
            )
            candidate = SchedulingPolicy(
                name=template.name,
                order=template.order,
                workers=template.workers,
                retry_limit=template.retry_limit,
                use_fallback=template.use_fallback,
                skip_optional=template.skip_optional,
                capability_aware_retry=template.capability_aware_retry,
                learned_weights=weights,
            )
            rewards = []
            for case_index, (mission_count, probability) in enumerate(
                training_cases
            ):
                metrics = simulate_once(
                    candidate,
                    mission_count=mission_count,
                    failure_probability=probability,
                    seed=(
                        seed
                        + 60_000_000
                        + generation * 100_000
                        + candidate_index * 1000
                        + case_index
                    ),
                )
                rewards.append(_rl_reward(metrics))
                evaluations += 1
            candidates.append((mean(rewards), weights))

        candidates.sort(key=lambda item: item[0], reverse=True)
        elite = candidates[: max(2, population // 4)]
        center = [
            mean(weights[index] for _, weights in elite)
            for index in range(len(center))
        ]
        spread = [
            max(
                0.08,
                (
                    stdev(weights[index] for _, weights in elite)
                    if len(elite) > 1
                    else spread[index] * 0.7
                ),
            )
            for index in range(len(spread))
        ]

    learned_policy = SchedulingPolicy(
        name=template.name,
        order=template.order,
        workers=template.workers,
        retry_limit=template.retry_limit,
        use_fallback=template.use_fallback,
        skip_optional=template.skip_optional,
        capability_aware_retry=template.capability_aware_retry,
        learned_weights=tuple(round(value, 5) for value in center),
    )
    return learned_policy, {
        "algorithm": "cross-entropy policy search",
        "generations": generations,
        "population": population,
        "training_cases": [
            {
                "mission_count": mission_count,
                "failure_probability": probability,
            }
            for mission_count, probability in training_cases
        ],
        "training_seed_offset": 60_000_000,
        "evaluation_seed_offset": 0,
        "policy_evaluations": evaluations,
        "learned_weights": list(learned_policy.learned_weights),
    }


def run_benchmark(
    trials: int = 50,
    seed: int = 20260615,
) -> Dict[str, Any]:
    started = time.perf_counter()
    mission_counts = [4, 8, 12, 16, 20]
    worker_counts = [1, 2, 4, 6, 8]
    failure_probabilities = [0.0, 0.05, 0.10, 0.15, 0.20]
    correlation_strengths = [0.0, 0.25, 0.50, 0.75, 0.90]
    learned_policy, rl_training = train_rl_policy(seed)
    def with_learned_rl_weights(policy: SchedulingPolicy) -> SchedulingPolicy:
        if policy.order != "rl":
            return policy
        return SchedulingPolicy(
            policy.name,
            order=policy.order,
            workers=policy.workers,
            retry_limit=policy.retry_limit,
            use_fallback=policy.use_fallback,
            skip_optional=policy.skip_optional,
            capability_aware_retry=policy.capability_aware_retry,
            learned_weights=learned_policy.learned_weights,
        )

    policies = tuple(with_learned_rl_weights(policy) for policy in POLICY_TEMPLATES)
    policy_by_name = {policy.name: policy for policy in policies}

    scalability: Dict[str, List[Dict[str, Any]]] = {}
    for policy in policies:
        scalability[policy.name] = []
        for mission_count in mission_counts:
            metrics = _run_trials(
                policy,
                mission_count,
                failure_probability=0.02,
                trials=trials,
                seed_base=seed + mission_count * 1000,
            )
            scalability[policy.name].append(
                {"mission_count": mission_count, **metrics}
            )

    for mission_index, mission_count in enumerate(mission_counts):
        serial_mean = scalability["Serial-FIFO"][mission_index][
            "makespan_s"
        ]["mean"]
        for policy in policies:
            item = scalability[policy.name][mission_index]
            ratio = item["makespan_s"]["mean"] / serial_mean
            item["normalized_makespan"] = {
                "mean": round(ratio, 5),
                "std": round(item["makespan_s"]["std"] / serial_mean, 5),
                "ci95": round(item["makespan_s"]["ci95"] / serial_mean, 5),
                "n": trials,
            }

    worker_scaling: Dict[str, List[Dict[str, Any]]] = {}
    for policy in policies:
        worker_scaling[policy.name] = []
        for workers in worker_counts:
            metrics = _run_trials(
                _copy_policy(policy, workers),
                mission_count=16,
                failure_probability=0.03,
                trials=trials,
                seed_base=(
                    seed
                    + 10_000_000
                    + workers * 1000
                ),
                workers_override=workers,
            )
            worker_scaling[policy.name].append(
                {"workers": workers, **metrics}
            )

    robustness: Dict[str, List[Dict[str, Any]]] = {}
    for policy in policies:
        robustness[policy.name] = []
        for probability_index, probability in enumerate(
            failure_probabilities
        ):
            metrics = _run_trials(
                policy,
                mission_count=12,
                failure_probability=probability,
                trials=trials,
                seed_base=(
                    seed
                    + 20_000_000
                    + probability_index * 100_000
                ),
            )
            robustness[policy.name].append(
                {"failure_probability": probability, **metrics}
            )

    ablation = []
    for policy_index, policy in enumerate(ABLATION_POLICIES):
        metrics = _run_trials(
            policy,
            mission_count=12,
            failure_probability=0.12,
            trials=trials,
            seed_base=seed + 30_000_000,
        )
        ablation.append({"variant": policy.name, **metrics})
    full_latency = ablation[0]["failure_penalized_latency_s"]["mean"]
    for item in ablation:
        item["normalized_penalized_latency"] = {
            "mean": round(
                item["failure_penalized_latency_s"]["mean"] / full_latency,
                5,
            ),
            "std": round(
                item["failure_penalized_latency_s"]["std"] / full_latency,
                5,
            ),
            "ci95": round(
                item["failure_penalized_latency_s"]["ci95"] / full_latency,
                5,
            ),
            "n": trials,
        }

    heatmap: Dict[str, List[List[float]]] = {}
    heatmap_trials = max(30, trials // 2)
    for policy in (
        policy_by_name["HEFT-DAG"],
        policy_by_name["Capability-DAG+Replan"],
    ):
        rows = []
        for probability_index, probability in enumerate(
            failure_probabilities
        ):
            row = []
            for mission_count in mission_counts:
                metrics = _run_trials(
                    policy,
                    mission_count=mission_count,
                    failure_probability=probability,
                    trials=heatmap_trials,
                    seed_base=(
                        seed
                        + 40_000_000
                        + probability_index * 200_000
                        + mission_count * 1000
                    ),
                )
                row.append(
                    metrics["priority_weighted_on_time_rate"]["mean"]
                )
            rows.append(row)
        heatmap[policy.name] = rows

    correlated_failure: Dict[str, List[Dict[str, Any]]] = {}
    correlated_policies = (
        policy_by_name["HEFT-DAG"],
        policy_by_name["Parallel-FIFO+Recovery"],
        policy_by_name["HEFT-DAG+Recovery"],
        policy_by_name["RL-DAG+Recovery"],
        policy_by_name["RL-DAG"],
        policy_by_name["Capability-DAG+Replan"],
    )
    for policy in correlated_policies:
        correlated_failure[policy.name] = []
        for correlation_index, correlation_strength in enumerate(
            correlation_strengths
        ):
            metrics = _run_trials(
                policy,
                mission_count=12,
                failure_probability=0.12,
                trials=trials,
                seed_base=(
                    seed
                    + 50_000_000
                    + correlation_index * 100_000
                ),
                failure_model=FailureModel(
                    name="correlated",
                    correlation_strength=correlation_strength,
                    window_s=4.0,
                ),
            )
            correlated_failure[policy.name].append(
                {
                    "correlation_strength": correlation_strength,
                    **metrics,
                }
            )

    geographic_validation: Dict[str, List[Dict[str, Any]]] = {}
    for policy in correlated_policies:
        geographic_validation[policy.name] = []
        for profile_index, profile in enumerate(GEOGRAPHIC_PROFILES):
            common_cause_multiplier = (
                0.80
                + 0.50 * profile.wet_hour_fraction
                + 0.035 * max(0.0, profile.p90_wind_mps - 8.0)
            )
            metrics = _run_trials(
                policy,
                mission_count=12,
                failure_probability=0.10,
                trials=trials,
                seed_base=(
                    seed
                    + 55_000_000
                    + profile_index * 100_000
                ),
                failure_model=FailureModel(
                    name="correlated",
                    correlation_strength=0.70,
                    window_s=4.0,
                    common_cause_multiplier=common_cause_multiplier,
                ),
                geographic_profile=profile,
            )
            geographic_validation[policy.name].append(
                {
                    "profile_id": profile.profile_id,
                    "label": profile.label,
                    **metrics,
                }
            )

    return {
        "experiment": "multi_agent_scheduling_benchmark",
        "methodology": {
            "type": "seeded_discrete_event_simulation",
            "seed": seed,
            "trials_per_point": trials,
            "heatmap_trials_per_point": heatmap_trials,
            "workflow_nodes": len(TASK_SPECS),
            "workflow_dag": {
                spec.task_id: list(spec.dependencies) for spec in TASK_SPECS
            },
            "confidence_interval": "mean +/- 1.96 * sample_std / sqrt(n)",
            "deadline_model": (
                "arrival plus urgency-dependent slack of 7.5, 10.0, or 13.0 s"
            ),
            "duration_model": (
                "Gaussian service time, coefficient of variation 0.13, "
                "clipped at 0.12 s"
            ),
            "failure_model": (
                "independent residual failures plus shared weather, "
                "airspace, network, and infrastructure shocks in fixed "
                "time windows"
            ),
            "correlated_failure_model": {
                "base_failure_probability": 0.12,
                "correlation_strengths": correlation_strengths,
                "shared_window_s": 4.0,
                "clusters": FAILURE_CLUSTERS,
                "fallback_common_shock_exposure": 0.25,
            },
            "rl_training": rl_training,
            "geographic_data_path": str(GEOGRAPHIC_DATA.relative_to(ROOT)),
            "note": (
                "These are reproducible simulation results for scheduler-level "
                "evaluation. Geographic profiles use real facility coordinates "
                "and fixed historical weather summaries, but are not physical "
                "UAV flight-test measurements."
            ),
        },
        "policies": [
            {
                "name": policy.name,
                "order": policy.order,
                "workers": policy.workers,
                "retry_limit": policy.retry_limit,
                "use_fallback": policy.use_fallback,
                "skip_optional": policy.skip_optional,
                "capability_aware_retry": policy.capability_aware_retry,
                "learned_weights": list(policy.learned_weights),
            }
            for policy in policies
        ],
        "geographic_profiles": [
            {
                "profile_id": profile.profile_id,
                "label": profile.label,
                "pickup_name": profile.pickup_name,
                "delivery_name": profile.delivery_name,
                "route_distance_km": round(profile.route_distance_km, 3),
                "weather_station": profile.weather_station,
                "mean_wind_mps": profile.mean_wind_mps,
                "p90_wind_mps": profile.p90_wind_mps,
                "wet_hour_fraction": profile.wet_hour_fraction,
            }
            for profile in GEOGRAPHIC_PROFILES
        ],
        "axes": {
            "mission_counts": mission_counts,
            "worker_counts": worker_counts,
            "failure_probabilities": failure_probabilities,
            "correlation_strengths": correlation_strengths,
        },
        "scalability": scalability,
        "worker_scaling": worker_scaling,
        "robustness": robustness,
        "ablation": ablation,
        "deadline_heatmap": heatmap,
        "correlated_failure": correlated_failure,
        "geographic_validation": geographic_validation,
        "runtime_s": round(time.perf_counter() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260615)
    args = parser.parse_args()

    result = run_benchmark(trials=args.trials, seed=args.seed)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "runtime_s": result["runtime_s"],
                "trials_per_point": args.trials,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
