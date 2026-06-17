import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "outputs" / "agent_scheduling_benchmark.json"
OUTPUT_DIR = ROOT / "outputs" / "figures" / "scheduling_paper"

WIDTH = 1800
HEIGHT = 1200
FONT = "Times New Roman, Times, serif"

COLORS = {
    "ink": "#202020",
    "muted": "#5A5A5A",
    "grid": "#D9D9D9",
    "serial": "#555555",
    "fifo": "#377EB8",
    "fifo_rec": "#5DA5DA",
    "heft": "#FF8C00",
    "heft_rec": "#B5651D",
    "rl": "#2A9D8F",
    "rl_rec": "#1B7F79",
    "proposed": "#D62728",
    "green": "#2A9D8F",
    "panel": "#FAFAFA",
}

POLICY_ORDER = [
    "Serial-FIFO",
    "Parallel-FIFO",
    "HEFT-DAG",
    "RL-DAG",
    "Capability-DAG+Replan",
]
POLICY_LABELS = {
    "Serial-FIFO": "Serial-FIFO",
    "Parallel-FIFO": "Parallel-FIFO",
    "HEFT-DAG": "HEFT-DAG",
    "RL-DAG": "RL-DAG",
    "Parallel-FIFO+Recovery": "FIFO+Rec",
    "HEFT-DAG+Recovery": "HEFT+Rec",
    "RL-DAG+Recovery": "RL+Rec",
    "Capability-DAG+Replan": "Proposed",
}
POLICY_COLORS = {
    "Serial-FIFO": COLORS["serial"],
    "Parallel-FIFO": COLORS["fifo"],
    "HEFT-DAG": COLORS["heft"],
    "RL-DAG": COLORS["rl"],
    "Parallel-FIFO+Recovery": COLORS["fifo_rec"],
    "HEFT-DAG+Recovery": COLORS["heft_rec"],
    "RL-DAG+Recovery": COLORS["rl_rec"],
    "Capability-DAG+Replan": COLORS["proposed"],
}
POLICY_DASH = {
    "Serial-FIFO": "10 7",
    "Parallel-FIFO": "4 5",
    "HEFT-DAG": "13 5 3 5",
    "RL-DAG": "2 4",
    "Parallel-FIFO+Recovery": "4 3",
    "HEFT-DAG+Recovery": "9 4 2 4",
    "RL-DAG+Recovery": "2 3",
    "Capability-DAG+Replan": "",
}
POLICY_MARKERS = {
    "Serial-FIFO": "square",
    "Parallel-FIFO": "triangle",
    "HEFT-DAG": "diamond",
    "RL-DAG": "cross",
    "Parallel-FIFO+Recovery": "plus",
    "HEFT-DAG+Recovery": "plus",
    "RL-DAG+Recovery": "plus",
    "Capability-DAG+Replan": "circle",
}

RECOVERY_COMPARISON_POLICIES = (
    "HEFT-DAG",
    "Parallel-FIFO+Recovery",
    "HEFT-DAG+Recovery",
    "RL-DAG+Recovery",
    "Capability-DAG+Replan",
)

GEOGRAPHIC_COMPARISON_POLICIES = (
    "Parallel-FIFO+Recovery",
    "HEFT-DAG+Recovery",
    "RL-DAG+Recovery",
    "Capability-DAG+Replan",
)


def esc(value: Any) -> str:
    return html.escape(str(value))


def text(
    x: float,
    y: float,
    value: Any,
    size: int = 20,
    fill: str = COLORS["ink"],
    weight: int = 400,
    anchor: str = "start",
    rotate: float = 0,
) -> str:
    transform = (
        f' transform="rotate({rotate} {x} {y})"' if rotate else ""
    )
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" fill="{fill}" '
        f'font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" font-family="{FONT}"{transform}>'
        f"{esc(value)}</text>"
    )


def line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke: str,
    width: float = 2,
    dash: str = "",
    opacity: float = 1.0,
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" '
        f'y2="{y2:.2f}" stroke="{stroke}" stroke-width="{width}" '
        f'opacity="{opacity}"{dash_attr}/>'
    )


def rect(
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    stroke: str = "none",
    stroke_width: float = 1,
    opacity: float = 1.0,
) -> str:
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" '
        f'height="{height:.2f}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" opacity="{opacity}"/>'
    )


def polyline(
    points: Sequence[Tuple[float, float]],
    stroke: str,
    width: float,
    dash: str = "",
) -> str:
    point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polyline points="{point_text}" fill="none" stroke="{stroke}" '
        f'stroke-width="{width}" stroke-linejoin="round" '
        f'stroke-linecap="round"{dash_attr}/>'
    )


def polygon(
    points: Sequence[Tuple[float, float]],
    fill: str,
    opacity: float = 1.0,
    stroke: str = "none",
) -> str:
    point_text = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (
        f'<polygon points="{point_text}" fill="{fill}" '
        f'opacity="{opacity}" stroke="{stroke}"/>'
    )


def marker(
    x: float,
    y: float,
    shape: str,
    color: str,
    size: float = 7,
) -> str:
    if shape == "square":
        return rect(
            x - size,
            y - size,
            2 * size,
            2 * size,
            "white",
            color,
            2.5,
        )
    if shape == "triangle":
        return polygon(
            [
                (x, y - size - 1),
                (x - size, y + size),
                (x + size, y + size),
            ],
            "white",
            1.0,
            color,
        )
    if shape == "diamond":
        return polygon(
            [
                (x, y - size - 1),
                (x - size, y),
                (x, y + size + 1),
                (x + size, y),
            ],
            "white",
            1.0,
            color,
        )
    if shape == "cross":
        return (
            f'<g stroke="{color}" stroke-width="2.5">'
            f'<line x1="{x - size:.2f}" y1="{y - size:.2f}" '
            f'x2="{x + size:.2f}" y2="{y + size:.2f}"/>'
            f'<line x1="{x - size:.2f}" y1="{y + size:.2f}" '
            f'x2="{x + size:.2f}" y2="{y - size:.2f}"/>'
            "</g>"
        )
    if shape == "plus":
        return (
            f'<g stroke="{color}" stroke-width="2.5">'
            f'<line x1="{x - size:.2f}" y1="{y:.2f}" '
            f'x2="{x + size:.2f}" y2="{y:.2f}"/>'
            f'<line x1="{x:.2f}" y1="{y - size:.2f}" '
            f'x2="{x:.2f}" y2="{y + size:.2f}"/>'
            "</g>"
        )
    return (
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size}" '
        f'fill="{color}" stroke="white" stroke-width="1.5"/>'
    )


def svg_document(title_value: str, body: Iterable[str]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
            f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
            f"<title>{esc(title_value)}</title>",
            rect(0, 0, WIDTH, HEIGHT, "white"),
            *body,
            "</svg>",
        ]
    )


def header(
    figure_number: str,
    title_value: str,
    subtitle: str,
) -> List[str]:
    return [
        text(70, 55, f"Figure {figure_number}.", 24, COLORS["muted"], 600),
        text(215, 55, title_value, 32, COLORS["ink"], 700),
        text(70, 91, subtitle, 18, COLORS["muted"]),
        line(70, 112, 1730, 112, COLORS["grid"], 2),
    ]


def legend(x: float, y: float) -> List[str]:
    elements = []
    for index, policy in enumerate(POLICY_ORDER):
        column = index % 2
        row = index // 2
        px = x + column * 235
        py = y + row * 34
        color = POLICY_COLORS[policy]
        elements.append(
            line(px, py, px + 52, py, color, 3, POLICY_DASH[policy])
        )
        elements.append(
            marker(
                px + 26,
                py,
                POLICY_MARKERS[policy],
                color,
                5.5,
            )
        )
        elements.append(
            text(px + 66, py + 6, POLICY_LABELS[policy], 16)
        )
    return elements


def _scale(
    value: float,
    domain_min: float,
    domain_max: float,
    range_min: float,
    range_max: float,
) -> float:
    if domain_max == domain_min:
        return (range_min + range_max) / 2
    ratio = (value - domain_min) / (domain_max - domain_min)
    return range_min + ratio * (range_max - range_min)


def line_panel(
    data_by_policy: Dict[str, List[Dict[str, Any]]],
    x: float,
    y: float,
    width: float,
    height: float,
    panel_title: str,
    x_key: str,
    metric: str,
    x_ticks: Sequence[float],
    y_ticks: Sequence[float],
    x_label: str,
    y_label: str,
    percent: bool = False,
    include_ci: bool = True,
    legend_inside: bool = False,
    policies: Sequence[str] = (),
) -> List[str]:
    plotted_policies = tuple(policies) if policies else tuple(POLICY_ORDER)
    elements = [
        text(x + 22, y + 33, panel_title, 21, weight=700),
    ]
    left = x + 88
    right = x + width - 28
    top = y + (126 if legend_inside else 62)
    bottom = y + height - 68
    x_min, x_max = min(x_ticks), max(x_ticks)
    y_min, y_max = min(y_ticks), max(y_ticks)

    for tick in y_ticks:
        py = _scale(tick, y_min, y_max, bottom, top)
        elements.append(line(left, py, right, py, COLORS["grid"], 1))
        label = f"{tick:g}"
        if percent:
            label = f"{tick * 100:.0f}"
        elements.append(
            text(left - 12, py + 5, label, 14, COLORS["muted"], anchor="end")
        )
    for tick in x_ticks:
        px = _scale(tick, x_min, x_max, left, right)
        elements.append(line(px, bottom, px, bottom + 6, COLORS["ink"], 1))
        label = f"{tick:g}"
        if x_key == "failure_probability":
            label = f"{tick * 100:.0f}"
        elements.append(
            text(px, bottom + 25, label, 14, COLORS["muted"], anchor="middle")
        )
    elements.extend(
        [
            line(left, top, left, bottom, COLORS["ink"], 1.4),
            line(left, bottom, right, bottom, COLORS["ink"], 1.4),
            text((left + right) / 2, y + height - 20, x_label, 15, anchor="middle"),
            text(
                x + 22,
                (top + bottom) / 2,
                y_label,
                15,
                anchor="middle",
                rotate=-90,
            ),
        ]
    )

    for policy in plotted_policies:
        records = data_by_policy[policy]
        means = [record[metric]["mean"] for record in records]
        if include_ci:
            upper = []
            lower = []
            for record, value in zip(records, means):
                px = _scale(record[x_key], x_min, x_max, left, right)
                ci = record[metric]["ci95"]
                upper.append(
                    (
                        px,
                        _scale(
                            min(y_max, value + ci),
                            y_min,
                            y_max,
                            bottom,
                            top,
                        ),
                    )
                )
                lower.append(
                    (
                        px,
                        _scale(
                            max(y_min, value - ci),
                            y_min,
                            y_max,
                            bottom,
                            top,
                        ),
                    )
                )
            elements.append(
                polygon(
                    upper + list(reversed(lower)),
                    POLICY_COLORS[policy],
                    opacity=0.10,
                )
            )

        points = []
        for record, value in zip(records, means):
            px = _scale(record[x_key], x_min, x_max, left, right)
            py = _scale(value, y_min, y_max, bottom, top)
            points.append((px, py))
        elements.append(
            polyline(
                points,
                POLICY_COLORS[policy],
                3.0 if policy == "Capability-DAG+Replan" else 2.4,
                POLICY_DASH[policy],
            )
        )
        for px, py in points:
            elements.append(
                marker(
                    px,
                    py,
                    POLICY_MARKERS[policy],
                    POLICY_COLORS[policy],
                    5.5,
                )
            )
    if legend_inside:
        legend_width = 650 if len(plotted_policies) > 4 else 520
        legend_height = 68
        legend_x = x + width - legend_width - 20
        legend_y = y + 46
        columns = 3 if len(plotted_policies) > 4 else 2
        column_width = (legend_width - 24) / columns
        for index, policy in enumerate(plotted_policies):
            column = index % columns
            row = index // columns
            px = legend_x + 12 + column * column_width
            py = legend_y + 20 + row * 28
            color = POLICY_COLORS[policy]
            elements.append(
                line(px, py, px + 42, py, color, 2.5, POLICY_DASH[policy])
            )
            elements.append(
                marker(
                    px + 21,
                    py,
                    POLICY_MARKERS[policy],
                    color,
                    4.5,
                )
            )
            elements.append(
                text(px + 50, py + 5, POLICY_LABELS[policy], 13)
            )
    return elements


def scalability_figure(data: Dict[str, Any]) -> str:
    body = header(
        "4",
        "智能体调度器的扩展性与资源效率",
        "每个点为独立离散事件仿真的均值，阴影表示 95% 置信区间；所有方法使用相同任务实例与服务时延。",
    )
    body.extend(legend(1260, 56))
    body.extend(
        line_panel(
            data["scalability"],
            70,
            145,
            800,
            455,
            "(a) Normalized makespan",
            "mission_count",
            "normalized_makespan",
            data["axes"]["mission_counts"],
            [0.2, 0.4, 0.6, 0.8, 1.0],
            "Concurrent mission workflows",
            "Makespan / Serial-FIFO",
        )
    )
    body.extend(
        line_panel(
            data["scalability"],
            930,
            145,
            800,
            455,
            "(b) Priority-weighted deadline satisfaction",
            "mission_count",
            "priority_weighted_on_time_rate",
            data["axes"]["mission_counts"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Concurrent mission workflows",
            "Weighted on-time ratio (%)",
            percent=True,
        )
    )
    throughput_max = max(
        record["throughput_per_min"]["mean"]
        for records in data["worker_scaling"].values()
        for record in records
    )
    throughput_ceiling = max(10.0, math_ceil(throughput_max, 5.0))
    throughput_ticks = [
        throughput_ceiling * index / 5 for index in range(6)
    ]
    body.extend(
        line_panel(
            data["worker_scaling"],
            70,
            650,
            800,
            455,
            "(c) Scheduling throughput",
            "workers",
            "throughput_per_min",
            data["axes"]["worker_counts"],
            throughput_ticks,
            "Available service workers",
            "Completed missions / min",
        )
    )
    body.extend(
        line_panel(
            data["worker_scaling"],
            930,
            650,
            800,
            455,
            "(d) Worker utilization",
            "workers",
            "utilization",
            data["axes"]["worker_counts"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Available service workers",
            "Busy-time utilization (%)",
            percent=True,
        )
    )

    body.extend(
        [
            text(
                900,
                1165,
                "Lower is better in (a); higher is better in (b)-(d). Serial-FIFO intentionally uses one execution slot.",
                16,
                COLORS["muted"],
                anchor="middle",
            ),
        ]
    )
    return svg_document("智能体调度器扩展性对比", body)


def math_ceil(value: float, step: float) -> float:
    integer = int(value / step)
    if integer * step < value:
        integer += 1
    return integer * step


def grouped_bar_panel(
    ablation: List[Dict[str, Any]],
    x: float,
    y: float,
    width: float,
    height: float,
) -> List[str]:
    elements = [
        text(x + 22, y + 33, "(c) Ablation: effectiveness", 21, weight=700),
    ]
    left, right = x + 78, x + width - 25
    top, bottom = y + 62, y + height - 108
    for tick in [0.0, 0.25, 0.5, 0.75, 1.0]:
        py = _scale(tick, 0, 1, bottom, top)
        elements.append(line(left, py, right, py, COLORS["grid"], 1))
        elements.append(
            text(left - 10, py + 5, f"{tick * 100:.0f}", 14, COLORS["muted"], anchor="end")
        )
    elements.extend(
        [
            line(left, top, left, bottom, COLORS["ink"], 1.4),
            line(left, bottom, right, bottom, COLORS["ink"], 1.4),
            text(x + 20, (top + bottom) / 2, "Rate (%)", 15, anchor="middle", rotate=-90),
        ]
    )
    labels = [
        "Full",
        "No parallel",
        "No replan",
        "No fallback",
        "No urgency",
    ]
    group_width = (right - left) / len(ablation)
    bar_width = group_width * 0.27
    for index, (item, label) in enumerate(zip(ablation, labels)):
        center = left + (index + 0.5) * group_width
        metrics = [
            ("success_rate", COLORS["fifo"]),
            ("priority_weighted_on_time_rate", COLORS["proposed"]),
        ]
        for offset, (metric_name, color) in zip((-0.6, 0.6), metrics):
            value = item[metric_name]["mean"]
            px = center + offset * bar_width
            py = _scale(value, 0, 1, bottom, top)
            elements.append(
                rect(px - bar_width / 2, py, bar_width, bottom - py, color)
            )
            elements.append(
                text(px, py - 7, f"{value * 100:.0f}", 12, color, 700, "middle")
            )
        elements.append(
            text(center, bottom + 24, label, 12, COLORS["muted"], anchor="middle")
        )
    elements.extend(
        [
            rect(right - 230, top + 8, 14, 14, COLORS["fifo"]),
            text(right - 208, top + 21, "Mission success", 13),
            rect(right - 230, top + 31, 14, 14, COLORS["proposed"]),
            text(right - 208, top + 44, "Weighted on-time", 13),
        ]
    )
    return elements


def ablation_latency_panel(
    ablation: List[Dict[str, Any]],
    x: float,
    y: float,
    width: float,
    height: float,
) -> List[str]:
    elements = [
        text(
            x + 22,
            y + 33,
            "(d) Ablation: failure-penalized latency",
            21,
            weight=700,
        ),
        rect(x + width - 286, y + 58, 14, 14, COLORS["proposed"]),
        text(x + width - 262, y + 70, "Full model", 13),
        rect(x + width - 166, y + 58, 14, 14, COLORS["serial"]),
        text(x + width - 142, y + 70, "Ablated", 13),
    ]
    left, right = x + 78, x + width - 25
    top, bottom = y + 62, y + height - 108
    maximum = max(
        item["normalized_penalized_latency"]["mean"]
        + item["normalized_penalized_latency"]["ci95"]
        for item in ablation
    )
    y_max = math_ceil(maximum, 1.0)
    ticks = [y_max * index / 5 for index in range(6)]
    for tick in ticks:
        py = _scale(tick, 0, y_max, bottom, top)
        elements.append(line(left, py, right, py, COLORS["grid"], 1))
        elements.append(
            text(left - 10, py + 5, f"{tick:.1f}", 14, COLORS["muted"], anchor="end")
        )
    elements.extend(
        [
            line(left, top, left, bottom, COLORS["ink"], 1.4),
            line(left, bottom, right, bottom, COLORS["ink"], 1.4),
            text(
                x + 20,
                (top + bottom) / 2,
                "Latency / full model",
                15,
                anchor="middle",
                rotate=-90,
            ),
        ]
    )
    labels = ["Full", "No parallel", "No replan", "No fallback", "No urgency"]
    group_width = (right - left) / len(ablation)
    bar_width = group_width * 0.48
    for index, (item, label) in enumerate(zip(ablation, labels)):
        center = left + (index + 0.5) * group_width
        value = item["normalized_penalized_latency"]["mean"]
        ci = item["normalized_penalized_latency"]["ci95"]
        py = _scale(value, 0, y_max, bottom, top)
        color = COLORS["proposed"] if index == 0 else COLORS["serial"]
        elements.append(
            rect(center - bar_width / 2, py, bar_width, bottom - py, color)
        )
        error_top = _scale(min(y_max, value + ci), 0, y_max, bottom, top)
        error_bottom = _scale(max(0, value - ci), 0, y_max, bottom, top)
        elements.extend(
            [
                line(center, error_top, center, error_bottom, COLORS["ink"], 1.5),
                line(center - 7, error_top, center + 7, error_top, COLORS["ink"], 1.5),
                line(center - 7, error_bottom, center + 7, error_bottom, COLORS["ink"], 1.5),
                text(center, py - 9, f"{value:.2f}×", 13, color, 700, "middle"),
                text(center, bottom + 24, label, 12, COLORS["muted"], anchor="middle"),
            ]
        )
    return elements


def robustness_figure(data: Dict[str, Any]) -> str:
    body = header(
        "5",
        "故障鲁棒性与调度机制消融",
        "故障率表示单次工具调用失败概率；消融实验在 12 个并发任务流和 12% 故障率下进行。",
    )
    body.extend(legend(1260, 56))
    body.extend(
        line_panel(
            data["robustness"],
            70,
            145,
            800,
            455,
            "(a) End-to-end mission success",
            "failure_probability",
            "success_rate",
            data["axes"]["failure_probabilities"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Per-call failure probability (%)",
            "Mission success (%)",
            percent=True,
        )
    )
    body.extend(
        line_panel(
            data["robustness"],
            930,
            145,
            800,
            455,
            "(b) Recovery success after observed failure",
            "failure_probability",
            "recovery_success_rate",
            data["axes"]["failure_probabilities"],
            [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            "Per-call failure probability (%)",
            "Recovered workflows (%)",
            percent=True,
        )
    )
    body.extend(grouped_bar_panel(data["ablation"], 70, 650, 800, 455))
    body.extend(ablation_latency_panel(data["ablation"], 930, 650, 800, 455))

    body.extend(
        [
            text(
                900,
                1165,
                "At 0% failure, recovery success is defined as 100% because no recovery case is observed. Lower is better in (d).",
                16,
                COLORS["muted"],
                anchor="middle",
            ),
        ]
    )
    return svg_document("调度器故障鲁棒性与消融", body)


def _rate_color(value: float) -> str:
    low = (247, 251, 255)
    high = (8, 81, 156)
    value = max(0.0, min(1.0, value))
    rgb = tuple(
        round(low[index] + value * (high[index] - low[index]))
        for index in range(3)
    )
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def _difference_color(value: float, maximum: float = 0.25) -> str:
    value = max(-maximum, min(maximum, value))
    if value >= 0:
        ratio = value / maximum
        low, high = (255, 247, 236), (179, 0, 0)
    else:
        ratio = -value / maximum
        low, high = (247, 251, 255), (8, 81, 156)
    rgb = tuple(
        round(low[index] + ratio * (high[index] - low[index]))
        for index in range(3)
    )
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def heatmap_panel(
    matrix: List[List[float]],
    x: float,
    y: float,
    width: float,
    height: float,
    title_value: str,
    mission_counts: Sequence[int],
    failure_probabilities: Sequence[float],
    difference: bool = False,
) -> List[str]:
    elements = [
        text(x + 22, y + 34, title_value, 20, weight=700),
    ]
    left, right = x + 82, x + width - 25
    top, bottom = y + 70, y + height - 82
    cell_width = (right - left) / len(mission_counts)
    cell_height = (bottom - top) / len(failure_probabilities)
    for row, probability in enumerate(failure_probabilities):
        for column, mission_count in enumerate(mission_counts):
            value = matrix[row][column]
            px = left + column * cell_width
            py = top + row * cell_height
            color = (
                _difference_color(value) if difference else _rate_color(value)
            )
            elements.append(
                rect(px, py, cell_width, cell_height, color, "white", 1.5)
            )
            label = (
                f"{value * 100:+.1f}"
                if difference
                else f"{value * 100:.1f}"
            )
            text_color = "white" if (
                (difference and abs(value) > 0.13)
                or (not difference and value > 0.52)
            ) else COLORS["ink"]
            elements.append(
                text(
                    px + cell_width / 2,
                    py + cell_height / 2 + 6,
                    label,
                    15,
                    text_color,
                    700,
                    "middle",
                )
            )
        elements.append(
            text(
                left - 12,
                top + (row + 0.5) * cell_height + 6,
                f"{probability * 100:.0f}",
                14,
                COLORS["muted"],
                anchor="end",
            )
        )
    for column, mission_count in enumerate(mission_counts):
        elements.append(
            text(
                left + (column + 0.5) * cell_width,
                bottom + 24,
                mission_count,
                14,
                COLORS["muted"],
                anchor="middle",
            )
        )
    elements.extend(
        [
            text((left + right) / 2, y + height - 24, "Concurrent workflows", 15, anchor="middle"),
            text(x + 22, (top + bottom) / 2, "Failure probability (%)", 15, anchor="middle", rotate=-90),
        ]
    )
    return elements


def heatmap_figure(data: Dict[str, Any]) -> str:
    proposed = data["deadline_heatmap"]["Capability-DAG+Replan"]
    heft = data["deadline_heatmap"]["HEFT-DAG"]
    difference = [
        [
            proposed[row][column] - heft[row][column]
            for column in range(len(proposed[row]))
        ]
        for row in range(len(proposed))
    ]
    body = header(
        "6",
        "负载—故障联合压力测试",
        "单元格为优先级加权的截止期满足率（%）；差值图显示 Proposed − HEFT-DAG 的百分点变化。",
    )
    body.extend(
        heatmap_panel(
            heft,
            70,
            165,
            520,
            800,
            "(a) HEFT-DAG",
            data["axes"]["mission_counts"],
            data["axes"]["failure_probabilities"],
        )
    )
    body.extend(
        heatmap_panel(
            proposed,
            640,
            165,
            520,
            800,
            "(b) Capability-DAG+Replan",
            data["axes"]["mission_counts"],
            data["axes"]["failure_probabilities"],
        )
    )
    body.extend(
        heatmap_panel(
            difference,
            1210,
            165,
            520,
            800,
            "(c) Improvement over HEFT-DAG",
            data["axes"]["mission_counts"],
            data["axes"]["failure_probabilities"],
            difference=True,
        )
    )
    body.extend(
        [
            text(330, 1015, "0", 13, COLORS["muted"], anchor="middle"),
            text(1090, 1015, "100", 13, COLORS["muted"], anchor="middle"),
        ]
    )
    # Explicit color swatches avoid external gradients and preserve print output.
    for index in range(20):
        value = index / 19
        body.append(
            rect(360 + index * 35, 995, 35, 22, _rate_color(value))
        )
    body.extend(
        [
            text(710, 1048, "Weighted deadline satisfaction (%)", 15, anchor="middle"),
            text(1260, 1015, "-25", 13, COLORS["muted"], anchor="middle"),
            text(1660, 1015, "+25", 13, COLORS["muted"], anchor="middle"),
        ]
    )
    for index in range(20):
        value = -0.25 + index / 19 * 0.50
        body.append(
            rect(1280 + index * 19, 995, 19, 22, _difference_color(value))
        )
    body.extend(
        [
            text(1470, 1048, "Improvement (percentage points)", 15, anchor="middle"),
            text(
                900,
                1125,
                "The proposed scheduler preserves urgent-mission service under combined queueing pressure and tool failures.",
                18,
                COLORS["muted"],
                600,
                "middle",
            ),
            text(
                900,
                1160,
                "Simulation settings, seeds, confidence intervals, and raw aggregates are stored in outputs/agent_scheduling_benchmark.json.",
                15,
                COLORS["muted"],
                anchor="middle",
            ),
        ]
    )
    return svg_document("调度压力测试热力图", body)


def write_figures() -> List[Path]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figures = {
        "fig4_scheduler_scalability.svg": scalability_figure(data),
        "fig5_scheduler_robustness_ablation.svg": robustness_figure(data),
        "fig6_scheduler_deadline_heatmap.svg": heatmap_figure(data),
    }
    paths = []
    for filename, content in figures.items():
        output_path = OUTPUT_DIR / filename
        output_path.write_text(content, encoding="utf-8")
        paths.append(output_path)
    return paths


if __name__ == "__main__":
    for path_value in write_figures():
        print(path_value)
