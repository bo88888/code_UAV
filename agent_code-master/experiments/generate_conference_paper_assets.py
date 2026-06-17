import json
from pathlib import Path
from typing import Iterable, List, Tuple

from experiments.generate_scheduler_paper_figures import (
    COLORS,
    POLICY_COLORS,
    POLICY_DASH,
    POLICY_LABELS,
    POLICY_MARKERS,
    POLICY_ORDER,
    GEOGRAPHIC_COMPARISON_POLICIES,
    RECOVERY_COMPARISON_POLICIES,
    ablation_latency_panel,
    _scale,
    grouped_bar_panel,
    heatmap_panel,
    legend,
    line,
    line_panel,
    marker,
    polygon,
    rect,
    text,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "outputs" / "agent_scheduling_benchmark.json"
OUTPUT_DIR = ROOT / "paper" / "ICCC_conference_paper" / "figures"


def document(
    width: int,
    height: int,
    title_value: str,
    body: Iterable[str],
) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">',
            f"<title>{title_value}</title>",
            rect(0, 0, width, height, "white"),
            *body,
            "</svg>",
        ]
    )


def arrow(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str = "#2C5F8A",
    width: float = 3,
) -> List[str]:
    dx = x2 - x1
    dy = y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1.0)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    head_x, head_y = x2 - 15 * ux, y2 - 15 * uy
    return [
        line(x1, y1, head_x, head_y, color, width),
        polygon(
            [
                (x2, y2),
                (head_x + 7 * px, head_y + 7 * py),
                (head_x - 7 * px, head_y - 7 * py),
            ],
            color,
        ),
    ]


def node(
    x: float,
    y: float,
    width: float,
    height: float,
    title_value: str,
    detail: str,
    border: str,
    fill: str,
) -> List[str]:
    return [
        rect(x, y, width, height, fill, border, 2),
        text(x + 16, y + 32, title_value, 19, weight=700),
        text(x + 16, y + 61, detail, 14, COLORS["muted"]),
    ]


def architecture_figure() -> str:
    width, height = 1800, 900
    body: List[str] = []
    top_nodes = [
        (45, "Mission request", "points, cargo, priority, window"),
        (325, "Semantic agent", "XML parsing and normalization"),
        (605, "Capability registry", "dependencies, retry, fallback"),
        (885, "DAG planner", "ready batches and critical paths"),
        (1165, "Scheduler", "urgency-aware parallel queue"),
        (1445, "MCP invoker", "typed service requests and results"),
    ]
    for x, title_value, detail in top_nodes:
        body.extend(
            node(
                x,
                45,
                240,
                92,
                title_value,
                detail,
                "#2166AC",
                "#F3F7FB",
            )
        )
    for index in range(len(top_nodes) - 1):
        body.extend(
            arrow(
                top_nodes[index][0] + 240,
                91,
                top_nodes[index + 1][0],
                91,
            )
        )

    body.extend(
        node(
            1165,
            190,
            520,
            92,
            "Recovery policy",
            "retry | wait-and-retry | registered fallback | optional skip",
            "#C43C39",
            "#FFF5F4",
        )
    )
    body.extend(arrow(1425, 137, 1425, 190, "#C43C39", 2.5))
    body.extend(arrow(1165, 236, 1055, 137, "#C43C39", 2.5))
    body.append(
        text(
            1090,
            220,
            "failure feedback",
            14,
            "#C43C39",
            700,
            "end",
        )
    )

    body.extend(
        [
            text(45, 365, "A. Checks", 21, "#2166AC", 700),
            text(45, 555, "B. Algorithms", 21, "#E68613", 700),
            text(45, 755, "C. Decision", 21, "#7B52AB", 700),
        ]
    )

    env_nodes = [
        (230, "A1 Airspace", "no-fly zones / altitude"),
        (560, "A2 Weather", "wind / rain / visibility"),
        (890, "A3 UAV status", "battery / payload / health"),
        (1220, "A4 Dock status", "charging / turnaround"),
    ]
    route_nodes = [
        (230, "B1 DRL-LLM", "compliance-aware trajectory"),
        (560, "B2 Air-ground", "weather-adaptive dispatch"),
        (890, "B3 TWA-MILP", "medical time-window schedule"),
        (1220, "B4 CoordField", "agentic task allocation"),
    ]
    for x, title_value, detail in env_nodes:
        body.extend(
            node(
                x,
                325,
                270,
                98,
                title_value,
                detail,
                "#2166AC",
                "#F5F9FC",
            )
        )
    for x, title_value, detail in route_nodes:
        body.extend(
            node(
                x,
                515,
                270,
                98,
                title_value,
                detail,
                "#E68613",
                "#FFF8EF",
            )
        )
    dependencies = [
        (230 + 135, 515, 230 + 135),
        (560 + 135, 515, 560 + 135),
        (890 + 135, 515, 890 + 135),
        (1220 + 135, 515, 1220 + 135),
    ]
    for x1, y2, x2 in dependencies:
        body.extend(arrow(x1, 423, x2, y2, "#2166AC", 2.2))

    body.extend(
        node(
            340,
            715,
            330,
            98,
            "Risk assessment",
            "compliance, weather, deadline, energy",
            "#7B52AB",
            "#F8F5FB",
        )
    )
    body.extend(
        node(
            755,
            715,
            330,
            98,
            "Candidate selection",
            "rank feasible plans and select vehicle",
            "#7B52AB",
            "#F8F5FB",
        )
    )
    body.extend(
        node(
            1170,
            715,
            330,
            98,
            "Auditable report",
            "plan, trace, recovery events, status",
            "#7B52AB",
            "#F8F5FB",
        )
    )
    body.extend(arrow(670, 764, 755, 764, "#7B52AB", 2.5))
    body.extend(arrow(1085, 764, 1170, 764, "#7B52AB", 2.5))
    for x, _, _ in route_nodes:
        body.append(line(x + 135, 613, x + 135, 665, "#E68613", 2))
    body.append(line(365, 665, 1355, 665, "#E68613", 2))
    body.extend(arrow(505, 665, 505, 715, "#E68613", 2.5))
    body.append(
        text(
            1710,
            355,
            "previous_results",
            15,
            COLORS["muted"],
            600,
            "end",
        )
    )
    body.append(
        text(
            1710,
            380,
            "couples upstream context",
            14,
            COLORS["muted"],
            anchor="end",
        )
    )
    return document(width, height, "Capability-aware orchestration architecture", body)


def scenario_figure() -> str:
    width, height = 900, 760
    body: List[str] = [
        rect(25, 80, 850, 645, "#F8FAFB", "#303841", 1.5),
        rect(25, 20, 850, 42, "#F3F7FB", "#AAB7C2", 1),
        text(
            450,
            47,
            "Blood plasma 2.5 kg | priority 4 | 10:00--10:30 | wind <= 10 m/s | altitude <= 120 m",
            16,
            weight=700,
            anchor="middle",
        ),
    ]
    for index in range(1, 10):
        x = 25 + index * 85
        body.append(line(x, 80, x, 725, "#E5E9ED", 1))
    for index in range(1, 7):
        y = 80 + index * 92
        body.append(line(25, y, 875, y, "#E5E9ED", 1))

    roads = [
        [(35, 625), (220, 585), (420, 615), (610, 565), (860, 615)],
        [(55, 170), (245, 250), (445, 220), (625, 300), (855, 240)],
        [(245, 90), (235, 285), (270, 500), (260, 715)],
        [(640, 90), (610, 280), (650, 505), (630, 715)],
    ]
    for points in roads:
        point_text = " ".join(f"{x},{y}" for x, y in points)
        body.append(
            f'<polyline points="{point_text}" fill="none" stroke="white" '
            'stroke-width="22" stroke-linejoin="round"/>'
        )
        body.append(
            f'<polyline points="{point_text}" fill="none" stroke="#B7C0C8" '
            'stroke-width="3" stroke-linejoin="round"/>'
        )

    buildings = [
        (130, 170), (275, 275), (390, 135), (505, 235),
        (705, 155), (740, 440), (480, 520), (155, 500),
    ]
    for x, y in buildings:
        body.append(rect(x, y, 75, 48, "#DCE3E8", "#ADB8C2", 1))
        body.append(line(x + 10, y + 16, x + 65, y + 16, "#BBC5CD", 1))

    body.extend(
        [
            rect(55, 340, 110, 78, "white", "#C43C39", 2),
            rect(98, 353, 24, 52, "#C43C39"),
            rect(82, 370, 56, 20, "#C43C39"),
            text(110, 445, "Hospital A", 18, weight=700, anchor="middle"),
            text(110, 467, "pickup", 14, COLORS["muted"], anchor="middle"),
            rect(730, 525, 110, 78, "white", "#2166AC", 2),
            rect(773, 538, 24, 52, "#2166AC"),
            rect(757, 555, 56, 20, "#2166AC"),
            text(785, 630, "Clinic B", 18, weight=700, anchor="middle"),
            text(785, 652, "delivery", 14, COLORS["muted"], anchor="middle"),
            polygon(
                [(365, 300), (520, 245), (665, 350), (590, 495), (390, 470), (325, 375)],
                "#F5C7C7",
                0.78,
                "#C43C39",
            ),
            text(500, 370, "Temporary no-fly zone", 17, "#C43C39", 700, "middle"),
            polygon(
                [(585, 90), (865, 90), (865, 260), (735, 315), (620, 225)],
                "#DCEAF2",
                0.9,
                "#66869A",
            ),
            text(735, 155, "Adverse weather area", 16, "#4A6678", 700, "middle"),
        ]
    )

    uav_route = [(160, 355), (285, 245), (420, 185), (560, 220), (665, 385), (730, 555)]
    ground_route = [(150, 410), (285, 545), (455, 655), (625, 650), (730, 580)]
    for points, color, dash_value in (
        (uav_route, "#2166AC", ""),
        (ground_route, "#E68613", "12 7"),
    ):
        point_text = " ".join(f"{x},{y}" for x, y in points)
        dash = f' stroke-dasharray="{dash_value}"' if dash_value else ""
        body.append(
            f'<polyline points="{point_text}" fill="none" stroke="{color}" '
            f'stroke-width="5" stroke-linejoin="round"{dash}/>'
        )
        body.extend(arrow(points[-2][0], points[-2][1], points[-1][0], points[-1][1], color, 5))
    body.extend(
        [
            text(425, 165, "UAV candidate route", 16, "#2166AC", 700, "middle"),
            text(470, 696, "Air-ground fallback route", 16, "#E68613", 700, "middle"),
        ]
    )
    return document(width, height, "Emergency medical delivery scenario", body)


def figure_note(lines: Tuple[str, str], y: float, height: float = 64) -> List[str]:
    return [
        rect(25, y, 850, height, "#F7F7F7", "#B8B8B8", 1),
        text(450, y + 25, lines[0], 15, COLORS["ink"], 600, "middle"),
        text(450, y + 49, lines[1], 14, COLORS["muted"], 400, "middle"),
    ]


def scalability_figure(data: dict) -> str:
    width, height = 900, 1100
    body: List[str] = []
    body.extend(
        line_panel(
            data["scalability"],
            25,
            20,
            850,
            520,
            "(a) Normalized makespan",
            "mission_count",
            "normalized_makespan",
            data["axes"]["mission_counts"],
            [0.2, 0.4, 0.6, 0.8, 1.0],
            "Concurrent mission workflows",
            "Makespan / Serial-FIFO",
            legend_inside=True,
        )
    )
    body.extend(
        line_panel(
            data["scalability"],
            25,
            560,
            850,
            520,
            "(b) Priority-weighted deadline satisfaction",
            "mission_count",
            "priority_weighted_on_time_rate",
            data["axes"]["mission_counts"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Concurrent mission workflows",
            "Weighted on-time ratio (%)",
            percent=True,
            legend_inside=True,
        )
    )
    return document(width, height, "Scheduler scalability results", body)


def resource_figure(data: dict) -> str:
    width, height = 900, 1100
    body: List[str] = []
    body.extend(
        line_panel(
            data["worker_scaling"],
            25,
            20,
            850,
            520,
            "(a) Scheduling throughput",
            "workers",
            "throughput_per_min",
            data["axes"]["worker_counts"],
            [0, 8, 16, 24, 32, 40],
            "Available service workers",
            "Completed missions / min",
            legend_inside=True,
        )
    )
    body.extend(
        line_panel(
            data["worker_scaling"],
            25,
            560,
            850,
            520,
            "(b) Worker utilization",
            "workers",
            "utilization",
            data["axes"]["worker_counts"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Available service workers",
            "Busy-time utilization (%)",
            percent=True,
            legend_inside=True,
        )
    )
    return document(width, height, "Scheduler resource efficiency", body)


def robustness_figure(data: dict) -> str:
    width, height = 900, 1100
    body: List[str] = []
    body.extend(
        line_panel(
            data["robustness"],
            25,
            20,
            850,
            520,
            "(a) End-to-end mission success",
            "failure_probability",
            "success_rate",
            data["axes"]["failure_probabilities"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Per-call failure probability (%)",
            "Mission success (%)",
            percent=True,
            legend_inside=True,
            policies=RECOVERY_COMPARISON_POLICIES,
        )
    )
    body.extend(
        line_panel(
            data["robustness"],
            25,
            560,
            850,
            520,
            "(b) Recovery success after observed failure",
            "failure_probability",
            "recovery_success_rate",
            data["axes"]["failure_probabilities"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Per-call failure probability (%)",
            "Recovered workflows (%)",
            percent=True,
            legend_inside=True,
            policies=RECOVERY_COMPARISON_POLICIES,
        )
    )
    return document(width, height, "Robustness and ablation results", body)


def ablation_figure(data: dict) -> str:
    width, height = 900, 1000
    body = [
        item.replace("(c) Ablation", "(a) Ablation")
        for item in grouped_bar_panel(data["ablation"], 25, 20, 850, 470)
    ]
    body.extend(
        item.replace("(d) Ablation", "(b) Ablation")
        for item in ablation_latency_panel(
            data["ablation"], 25, 510, 850, 470
        )
    )
    return document(width, height, "Scheduling mechanism ablation", body)


def geographic_deadline_panel(
    data: dict,
    x: float,
    y: float,
    width: float,
    height: float,
) -> List[str]:
    policies = GEOGRAPHIC_COMPARISON_POLICIES
    profiles = data["geographic_profiles"]
    body = [
        text(x + 22, y + 33, "(b) Geographic weighted deadline service", 21, weight=700),
    ]
    left = x + 88
    right = x + width - 28
    top = y + 82
    bottom = y + height - 92
    y_max = 0.40
    for tick in [0.0, 0.10, 0.20, 0.30, 0.40]:
        py = _scale(tick, 0, y_max, bottom, top)
        body.append(line(left, py, right, py, COLORS["grid"], 1))
        body.append(
            text(left - 12, py + 5, f"{tick * 100:.0f}", 14, COLORS["muted"], anchor="end")
        )
    body.extend(
        [
            line(left, top, left, bottom, COLORS["ink"], 1.4),
            line(left, bottom, right, bottom, COLORS["ink"], 1.4),
            text(x + 22, (top + bottom) / 2, "Weighted on-time ratio (%)", 15, anchor="middle", rotate=-90),
        ]
    )
    group_width = (right - left) / len(profiles)
    bar_width = group_width * 0.16
    for profile_index, profile in enumerate(profiles):
        center = left + (profile_index + 0.5) * group_width
        for policy_index, policy in enumerate(policies):
            record = data["geographic_validation"][policy][profile_index]
            value = record["priority_weighted_on_time_rate"]["mean"]
            px = center + (policy_index - 1.5) * bar_width * 1.15
            py = _scale(value, 0, y_max, bottom, top)
            body.append(
                rect(
                    px - bar_width / 2,
                    py,
                    bar_width,
                    bottom - py,
                    POLICY_COLORS[policy],
                )
            )
            body.append(
                text(
                    px,
                    py - 7,
                    f"{value * 100:.0f}",
                    12,
                    POLICY_COLORS[policy],
                    700,
                    "middle",
                )
            )
        body.append(
            text(center, bottom + 25, profile["label"], 14, COLORS["muted"], anchor="middle")
        )
    legend_x = right - 650
    for index, policy in enumerate(policies):
        px = legend_x + index * 160
        body.append(rect(px, y + 50, 14, 14, POLICY_COLORS[policy]))
        body.append(text(px + 22, y + 63, POLICY_LABELS[policy], 13))
    return body


def correlated_geography_figure(data: dict) -> str:
    width, height = 1180, 1100
    validation_policies = RECOVERY_COMPARISON_POLICIES
    body: List[str] = []
    body.extend(
        line_panel(
            data["correlated_failure"],
            25,
            20,
            1130,
            520,
            "(a) Common-cause failure deadline service",
            "correlation_strength",
            "priority_weighted_on_time_rate",
            data["axes"]["correlation_strengths"],
            [0.0, 0.1, 0.2, 0.3, 0.4],
            "Common-cause correlation strength",
            "Weighted on-time ratio (%)",
            percent=True,
            legend_inside=True,
            policies=validation_policies,
        )
    )
    body.extend(
        geographic_deadline_panel(
            data,
            25,
            560,
            1130,
            520,
        )
    )
    return document(width, height, "Correlated failure and geographic validation", body)


def pressure_figure(data: dict) -> str:
    width, height = 1800, 760
    proposed = data["deadline_heatmap"]["Capability-DAG+Replan"]
    heft = data["deadline_heatmap"]["HEFT-DAG"]
    difference = [
        [
            proposed[row][column] - heft[row][column]
            for column in range(len(proposed[row]))
        ]
        for row in range(len(proposed))
    ]
    body: List[str] = []
    body.extend(
        heatmap_panel(
            heft,
            25,
            20,
            560,
            700,
            "(a) HEFT-DAG",
            data["axes"]["mission_counts"],
            data["axes"]["failure_probabilities"],
        )
    )
    body.extend(
        heatmap_panel(
            proposed,
            620,
            20,
            560,
            700,
            "(b) Capability-DAG+Replan",
            data["axes"]["mission_counts"],
            data["axes"]["failure_probabilities"],
        )
    )
    body.extend(
        heatmap_panel(
            difference,
            1215,
            20,
            560,
            700,
            "(c) Proposed minus HEFT-DAG",
            data["axes"]["mission_counts"],
            data["axes"]["failure_probabilities"],
            difference=True,
        )
    )
    return document(width, height, "Load and failure pressure test", body)


def write_assets() -> List[Path]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = {
        "scheduler_scalability.svg": scalability_figure(data),
        "scheduler_resource_efficiency.svg": resource_figure(data),
        "scheduler_robustness.svg": robustness_figure(data),
        "scheduler_ablation.svg": ablation_figure(data),
        "scheduler_correlated_geography.svg": correlated_geography_figure(data),
        "scheduler_pressure.svg": pressure_figure(data),
    }
    paths = []
    for filename, content in assets.items():
        path = OUTPUT_DIR / filename
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


if __name__ == "__main__":
    for output_path in write_assets():
        print(output_path)
