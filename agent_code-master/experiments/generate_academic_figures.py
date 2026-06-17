import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "outputs" / "algorithm_comparison.json"
OUTPUT_DIR = ROOT / "outputs" / "figures" / "academic"

WIDTH = 1920
HEIGHT = 1080
FONT = "Microsoft YaHei, Arial, sans-serif"

COLORS = {
    "ink": "#17212B",
    "muted": "#5C6B78",
    "grid": "#D7DEE5",
    "panel": "#F7F9FB",
    "blue": "#2166AC",
    "cyan": "#00A6A6",
    "orange": "#E68613",
    "purple": "#7B52AB",
    "red": "#C43C39",
    "green": "#238B45",
    "road": "#B7C0C8",
    "building": "#DCE3E8",
}

ALGORITHMS = [
    "DRL-LLM Compliance Trajectory",
    "TWA-MILP Medical Scheduler",
    "CoordField Agentic Allocation",
    "NN Weather-Adaptive Air-Ground",
]
ALGORITHM_LABELS = {
    "DRL-LLM Compliance Trajectory": "DRL-LLM",
    "TWA-MILP Medical Scheduler": "TWA-MILP",
    "CoordField Agentic Allocation": "CoordField",
    "NN Weather-Adaptive Air-Ground": "NN Air-Ground",
}
ALGORITHM_COLORS = {
    "DRL-LLM Compliance Trajectory": COLORS["blue"],
    "TWA-MILP Medical Scheduler": COLORS["cyan"],
    "CoordField Agentic Allocation": COLORS["purple"],
    "NN Weather-Adaptive Air-Ground": COLORS["orange"],
}
SCENARIOS = [
    ("normal", "正常场景"),
    ("bad_weather", "恶劣天气"),
    ("airspace_restricted", "临时禁飞"),
    ("no_available_uav_once", "无人机短缺"),
]


def esc(value: Any) -> str:
    return html.escape(str(value))


def text(
    x: float,
    y: float,
    value: Any,
    size: int = 24,
    fill: str = COLORS["ink"],
    weight: int = 400,
    anchor: str = "start",
    italic: bool = False,
) -> str:
    style = "italic" if italic else "normal"
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
        f'font-weight="{weight}" font-style="{style}" '
        f'text-anchor="{anchor}" font-family="{FONT}">{esc(value)}</text>'
    )


def rect(
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str = "white",
    stroke: str = "none",
    stroke_width: float = 1,
    radius: float = 0,
    dash: str = "",
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="{radius}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{stroke_width}"{dash_attr}/>'
    )


def line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke: str = COLORS["ink"],
    width: float = 2,
    dash: str = "",
    marker: str = "",
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    marker_attr = f' marker-end="url(#{marker})"' if marker else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{stroke}" stroke-width="{width}"{dash_attr}{marker_attr}/>'
    )


def circle(
    cx: float,
    cy: float,
    radius: float,
    fill: str,
    stroke: str = "none",
    stroke_width: float = 1,
) -> str:
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{stroke_width}"/>'
    )


def path(
    data: str,
    stroke: str,
    width: float = 3,
    fill: str = "none",
    dash: str = "",
    marker: str = "",
    opacity: float = 1.0,
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    marker_attr = f' marker-end="url(#{marker})"' if marker else ""
    return (
        f'<path d="{data}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{width}" opacity="{opacity}"{dash_attr}{marker_attr}/>'
    )


def polygon(
    points: str,
    fill: str,
    stroke: str = "none",
    stroke_width: float = 1,
    opacity: float = 1.0,
    dash: str = "",
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" opacity="{opacity}"{dash_attr}/>'
    )


def svg_document(
    title_value: str,
    body: Iterable[str],
    extra_defs: Iterable[str] = (),
) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
            f'height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
            f"<title>{esc(title_value)}</title>",
            "<defs>",
            '<marker id="arrow-blue" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">',
            f'<path d="M0,0 L10,5 L0,10 z" fill="{COLORS["blue"]}"/>',
            "</marker>",
            '<marker id="arrow-orange" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">',
            f'<path d="M0,0 L10,5 L0,10 z" fill="{COLORS["orange"]}"/>',
            "</marker>",
            '<pattern id="weather-hatch" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">',
            '<rect width="12" height="12" fill="#EAF1F5"/>',
            '<line x1="0" y1="0" x2="0" y2="12" stroke="#7894A6" stroke-width="4"/>',
            "</pattern>",
            *extra_defs,
            "</defs>",
            rect(0, 0, WIDTH, HEIGHT, "white"),
            *body,
            "</svg>",
        ]
    )


def figure_header(
    number: str, title_value: str, subtitle: str
) -> List[str]:
    return [
        text(70, 62, f"Figure {number}.", 24, COLORS["muted"], 600),
        text(205, 62, title_value, 34, COLORS["ink"], 700),
        text(70, 98, subtitle, 20, COLORS["muted"]),
        line(70, 122, 1850, 122, COLORS["grid"], 2),
    ]


def _metric_value(
    scenario: Dict[str, Any],
    algorithm: str,
    key: str,
) -> Optional[float]:
    metrics = scenario.get("algorithm_metrics", {}).get(algorithm)
    if metrics is None:
        return None
    return float(metrics[key])


def _draw_line_panel(
    data: Dict[str, Any],
    x: float,
    y: float,
    width: float,
    height: float,
    title_value: str,
    key: str,
    y_min: float,
    y_max: float,
    ticks: List[float],
    unit: str,
) -> List[str]:
    elements = [
        rect(x, y, width, height, "white", COLORS["grid"], 1.5, 4),
        text(x + 28, y + 42, title_value, 24, COLORS["ink"], 700),
    ]
    plot_left = x + 115
    plot_right = x + width - 35
    plot_top = y + 75
    plot_bottom = y + height - 82
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    for tick in ticks:
        py = plot_bottom - (tick - y_min) / (y_max - y_min) * plot_height
        elements.append(line(plot_left, py, plot_right, py, COLORS["grid"], 1))
        label = f"{tick:g}{unit}"
        elements.append(
            text(plot_left - 16, py + 7, label, 16, COLORS["muted"], anchor="end")
        )
    elements.append(line(plot_left, plot_top, plot_left, plot_bottom, COLORS["ink"], 1.5))
    elements.append(line(plot_left, plot_bottom, plot_right, plot_bottom, COLORS["ink"], 1.5))

    x_positions = [
        plot_left + index * plot_width / (len(SCENARIOS) - 1)
        for index in range(len(SCENARIOS))
    ]
    scenario_map = {
        scenario["scenario"]: scenario for scenario in data["scenarios"]
    }
    for index, (_, label) in enumerate(SCENARIOS):
        px = x_positions[index]
        elements.append(line(px, plot_bottom, px, plot_bottom + 7, COLORS["ink"], 1))
        elements.append(
            text(px, plot_bottom + 31, label, 14, COLORS["muted"], anchor="middle")
        )

    for algorithm in ALGORITHMS:
        color = ALGORITHM_COLORS[algorithm]
        previous_point: Optional[Tuple[float, float]] = None
        for index, (scenario_id, _) in enumerate(SCENARIOS):
            scenario = scenario_map[scenario_id]
            value = _metric_value(scenario, algorithm, key)
            px = x_positions[index]
            if value is None:
                elements.extend(
                    [
                        line(px - 7, plot_bottom - 15, px + 7, plot_bottom - 1, color, 2),
                        line(px - 7, plot_bottom - 1, px + 7, plot_bottom - 15, color, 2),
                    ]
                )
                previous_point = None
                continue
            py = plot_bottom - (value - y_min) / (y_max - y_min) * plot_height
            if previous_point is not None:
                elements.append(
                    line(
                        previous_point[0],
                        previous_point[1],
                        px,
                        py,
                        color,
                        3,
                    )
                )
            feasible = bool(
                scenario["algorithm_metrics"][algorithm]["effective_feasible"]
            )
            elements.append(
                circle(
                    px,
                    py,
                    7,
                    color if feasible else "white",
                    color,
                    3,
                )
            )
            previous_point = (px, py)
    return elements


def algorithm_line_figure(data: Dict[str, Any]) -> str:
    body = figure_header(
        "1",
        "多场景算法性能折线对比",
        "所有数据点均由 outputs/algorithm_comparison.json 自动读取；实心点表示可行，空心点表示不满足场景约束。",
    )
    body.extend(
        _draw_line_panel(
            data,
            70,
            160,
            870,
            380,
            "(a) 任务完成时间",
            "duration_mins",
            10,
            30,
            [10, 15, 20, 25, 30],
            " min",
        )
    )
    body.extend(
        _draw_line_panel(
            data,
            980,
            160,
            870,
            380,
            "(b) 估算能耗",
            "energy_kj",
            350,
            850,
            [350, 450, 550, 650, 750, 850],
            "",
        )
    )
    body.extend(
        _draw_line_panel(
            data,
            70,
            585,
            870,
            380,
            "(c) 合规评分",
            "compliance_score",
            0.80,
            1.00,
            [0.80, 0.85, 0.90, 0.95, 1.00],
            "",
        )
    )

    x = 1010
    y = 625
    body.extend(
        [
            rect(980, 585, 870, 380, COLORS["panel"], COLORS["grid"], 1.5, 4),
            text(1010, 630, "(d) 图例与约束含义", 24, weight=700),
        ]
    )
    for index, algorithm in enumerate(ALGORITHMS):
        py = y + 60 + index * 52
        color = ALGORITHM_COLORS[algorithm]
        body.append(line(x, py, x + 65, py, color, 3))
        body.append(circle(x + 32, py, 7, color, color, 2))
        body.append(text(x + 85, py + 7, ALGORITHM_LABELS[algorithm], 19))
    body.extend(
        [
            circle(1018, 876, 7, COLORS["blue"], COLORS["blue"], 2),
            text(1042, 883, "满足空域、气象和时间窗约束", 17),
            circle(1018, 916, 7, "white", COLORS["blue"], 3),
            text(1042, 923, "算法返回数值解，但被场景约束判定为不可行", 17),
            line(1011, 948, 1025, 962, COLORS["red"], 2),
            line(1011, 962, 1025, 948, COLORS["red"], 2),
            text(1042, 962, "故障处理后仍无有效输出", 17),
            text(
                960,
                1032,
                "该对比将数值最优性与运行可行性分开评价，体现多智能体编排的必要性。",
                19,
                COLORS["muted"],
                anchor="middle",
                italic=True,
            ),
        ]
    )
    return svg_document("多场景算法性能折线对比", body)


def _hospital_icon(x: float, y: float, label: str) -> List[str]:
    return [
        rect(x, y, 150, 105, "white", COLORS["red"], 2.5, 4),
        rect(x + 61, y + 18, 28, 68, COLORS["red"]),
        rect(x + 40, y + 39, 70, 26, COLORS["red"]),
        text(x + 75, y + 132, label, 20, COLORS["ink"], 700, "middle"),
    ]


def _clinic_icon(x: float, y: float, label: str) -> List[str]:
    return [
        rect(x, y, 140, 95, "white", COLORS["blue"], 2.5, 4),
        rect(x + 58, y + 19, 24, 58, COLORS["blue"]),
        rect(x + 40, y + 36, 60, 24, COLORS["blue"]),
        text(x + 70, y + 122, label, 20, COLORS["ink"], 700, "middle"),
    ]


def academic_scenario_figure() -> str:
    body = figure_header(
        "2",
        "低空应急医疗配送任务场景",
        "包含空域、气象、载具资源与时间窗约束的平面任务示意图。",
    )
    map_x, map_y, map_w, map_h = 70, 165, 1390, 815
    body.extend(
        [
            rect(map_x, map_y, map_w, map_h, "#F8FAFB", COLORS["ink"], 1.5, 2),
            text(1495, 190, "任务参数", 25, weight=700),
            rect(1485, 210, 365, 330, "white", COLORS["grid"], 1.5, 4),
            text(1515, 255, "载荷", 18, COLORS["muted"]),
            text(1635, 255, "血浆，2.5 kg", 18, weight=600),
            text(1515, 300, "优先级", 18, COLORS["muted"]),
            text(1635, 300, "高（4级）", 18, weight=600),
            text(1515, 345, "就绪时间", 18, COLORS["muted"]),
            text(1635, 345, "10:00", 18, weight=600),
            text(1515, 390, "截止时间", 18, COLORS["muted"]),
            text(1635, 390, "10:30", 18, weight=600),
            text(1515, 435, "风速上限", 18, COLORS["muted"]),
            text(1635, 435, "≤ 10 m/s", 18, weight=600),
            text(1515, 480, "高度上限", 18, COLORS["muted"]),
            text(1635, 480, "≤ 120 m", 18, weight=600),
            text(1495, 590, "图例", 25, weight=700),
            rect(1485, 610, 365, 305, "white", COLORS["grid"], 1.5, 4),
        ]
    )

    for grid_index in range(1, 10):
        gx = map_x + grid_index * map_w / 10
        body.append(line(gx, map_y, gx, map_y + map_h, "#E7ECEF", 1))
    for grid_index in range(1, 8):
        gy = map_y + grid_index * map_h / 8
        body.append(line(map_x, gy, map_x + map_w, gy, "#E7ECEF", 1))

    roads = [
        "M 95 850 C 330 780, 470 875, 690 790 S 1090 720, 1425 805",
        "M 160 230 C 410 350, 600 280, 820 390 S 1180 450, 1420 330",
        "M 410 180 C 380 400, 500 590, 470 960",
        "M 1050 180 C 980 380, 1110 590, 1040 960",
    ]
    for road in roads:
        body.append(path(road, "white", 26))
        body.append(path(road, COLORS["road"], 3))

    buildings = [
        (250, 270, 95, 75),
        (365, 355, 110, 70),
        (580, 225, 120, 85),
        (750, 300, 90, 75),
        (890, 240, 120, 90),
        (1170, 260, 105, 75),
        (1250, 510, 125, 90),
        (760, 690, 125, 85),
        (550, 640, 110, 80),
        (250, 670, 120, 90),
    ]
    for bx, by, bw, bh in buildings:
        body.append(rect(bx, by, bw, bh, COLORS["building"], "#AEBBC5", 1, 2))
        body.append(line(bx + 12, by + 18, bx + bw - 12, by + 18, "#BBC7CF", 1))
        body.append(line(bx + 12, by + 38, bx + bw - 12, by + 38, "#BBC7CF", 1))

    body.extend(_hospital_icon(125, 430, "医院 A / 取货点"))
    body.extend(_clinic_icon(1260, 665, "诊所 B / 配送点"))

    body.extend(
        [
            polygon(
                "690,400 930,335 1070,455 1000,620 745,600 640,495",
                "#F8D7D7",
                COLORS["red"],
                2.5,
                0.85,
                "12 7",
            ),
            text(850, 475, "临时禁飞区", 20, COLORS["red"], 700, "middle"),
            text(850, 505, "NFZ-01", 17, COLORS["red"], anchor="middle"),
            polygon(
                "955,170 1435,170 1435,430 1190,510 1005,365",
                "url(#weather-hatch)",
                "#66869A",
                2,
                0.85,
            ),
            text(1215, 235, "恶劣气象区域", 19, "#4A6678", 700, "middle"),
            text(1215, 265, "风速 / 降水 / 能见度", 15, "#4A6678", anchor="middle"),
            path(
                "M 275 455 C 450 365, 560 285, 675 300 C 880 325, 1080 650, 1270 695",
                COLORS["blue"],
                5,
                "none",
                "",
                "arrow-blue",
            ),
            text(585, 275, "无人机候选航线", 18, COLORS["blue"], 700),
            path(
                "M 260 540 C 420 710, 680 905, 1020 850 C 1150 830, 1220 760, 1280 735",
                COLORS["orange"],
                5,
                "none",
                "14 8",
                "arrow-orange",
            ),
            text(710, 900, "空地协同降级路线", 18, COLORS["orange"], 700),
            circle(270, 455, 8, COLORS["blue"]),
            circle(1280, 695, 8, COLORS["blue"]),
            circle(260, 540, 8, COLORS["orange"]),
            circle(1280, 735, 8, COLORS["orange"]),
            text(112, 960, "Longitude 114.05°E", 15, COLORS["muted"]),
            text(1240, 960, "Longitude 114.15°E", 15, COLORS["muted"]),
            text(82, 190, "Latitude 22.64°N", 15, COLORS["muted"]),
            text(82, 955, "Latitude 22.54°N", 15, COLORS["muted"]),
        ]
    )

    legend_items = [
        ("无人机候选航线", COLORS["blue"], ""),
        ("地面降级路线", COLORS["orange"], "14 8"),
        ("临时禁飞区", COLORS["red"], "12 7"),
        ("恶劣气象区域", "#66869A", ""),
    ]
    for index, (label, color, dash) in enumerate(legend_items):
        ly = 660 + index * 55
        if index == 3:
            body.append(rect(1515, ly - 15, 58, 28, "url(#weather-hatch)", "#66869A", 1))
        elif index == 2:
            body.append(rect(1515, ly - 15, 58, 28, "#F8D7D7", color, 2, 0, dash))
        else:
            body.append(line(1515, ly, 1573, ly, color, 4, dash))
        body.append(text(1595, ly + 7, label, 18))
    body.append(
        text(
            960,
            1035,
            "该图用于表达环境检查与路线规划服务所消费的任务约束，不代表真实地理底图。",
            18,
            COLORS["muted"],
            anchor="middle",
            italic=True,
        )
    )
    return svg_document("低空应急医疗配送任务场景", body)


def _node(
    x: float,
    y: float,
    width: float,
    height: float,
    title_value: str,
    detail: str,
    border: str,
    fill: str = "white",
) -> List[str]:
    return [
        rect(x, y, width, height, fill, border, 2, 4),
        text(x + 18, y + 34, title_value, 19, COLORS["ink"], 700),
        text(x + 18, y + 66, detail, 15, COLORS["muted"]),
    ]


def academic_framework_figure() -> str:
    body = figure_header(
        "3",
        "能力感知多智能体算法服务编排框架",
        "统一协调需求理解、能力注册、依赖调度、算法服务调用与异常重规划。",
    )
    body.extend(
        [
            text(70, 175, "输入与语义层", 20, COLORS["blue"], 700),
            text(70, 355, "编排与控制层", 20, COLORS["green"], 700),
            text(70, 610, "低空算法服务层", 20, COLORS["orange"], 700),
            text(70, 910, "决策与输出层", 20, COLORS["purple"], 700),
        ]
    )
    body.extend(
        _node(245, 145, 300, 115, "Mission request", "points, cargo, priority, time window", COLORS["blue"], "#F2F7FC")
    )
    body.extend(
        _node(665, 145, 300, 115, "UnderstandingAgent", "XML parsing and semantic normalization", COLORS["blue"], "#F2F7FC")
    )
    body.extend(
        _node(1085, 145, 300, 115, "Capability registry", "stage, dependency, output and fallback", COLORS["blue"], "#F2F7FC")
    )
    body.extend(
        _node(1505, 145, 300, 115, "ExecutionContext", "shared mission state and trace", COLORS["blue"], "#F2F7FC")
    )
    for x1, x2 in [(545, 665), (965, 1085), (1385, 1505)]:
        body.append(line(x1, 202, x2, 202, COLORS["blue"], 2.5, marker="arrow-blue"))

    control_nodes = [
        (245, "DecomposeAgent", "generate A/B/C/R DAG"),
        (575, "PlanningAgent", "dependency batches"),
        (905, "IntelligentScheduler", "parallel ready queue"),
        (1235, "InvokerAgent + MCP", "protocolized service calls"),
        (1565, "ReplanAgent", "retry / wait / fallback / skip"),
    ]
    for x, title_value, detail in control_nodes:
        body.extend(_node(x, 330, 260, 115, title_value, detail, COLORS["green"], "#F4FAF6"))
    for index in range(len(control_nodes) - 1):
        x1 = control_nodes[index][0] + 260
        x2 = control_nodes[index + 1][0]
        body.append(line(x1, 387, x2, 387, COLORS["green"], 2.5, marker="arrow-blue"))
    body.append(
        path(
            "M 1695 445 C 1695 520, 1040 535, 1040 445",
            COLORS["red"],
            2.5,
            "none",
            "9 6",
            "arrow-blue",
        )
    )
    body.append(text(1390, 520, "failure feedback and dynamic replanning", 16, COLORS["red"], 700, "middle"))

    env_nodes = [
        (130, "A1 Airspace", "no-fly zone / altitude"),
        (400, "A2 Weather", "wind / rain / visibility"),
        (670, "A3 UAV status", "battery / payload / health"),
        (940, "A4 Dock status", "charging / turnaround"),
    ]
    for x, title_value, detail in env_nodes:
        body.extend(_node(x, 585, 230, 105, title_value, detail, COLORS["blue"], "#F6F9FC"))
    body.append(text(60, 650, "A", 28, COLORS["blue"], 700))

    route_nodes = [
        (130, "B1 DRL-LLM", "compliance trajectory"),
        (400, "B2 NN Air-Ground", "weather-adaptive dispatch"),
        (670, "B3 TWA-MILP", "medical time-window schedule"),
        (940, "B4 CoordField", "agentic task allocation"),
    ]
    for x, title_value, detail in route_nodes:
        body.extend(_node(x, 735, 230, 105, title_value, detail, COLORS["orange"], "#FFF8EF"))
    body.append(text(60, 800, "B", 28, COLORS["orange"], 700))

    for index in range(4):
        x = env_nodes[index][0] + 115
        body.append(line(x, 690, x, 735, COLORS["blue"], 2, marker="arrow-blue"))

    body.extend(
        [
            rect(1235, 585, 570, 255, "#FBFBFC", COLORS["grid"], 1.5, 4),
            text(1265, 625, "Service coupling through previous_results", 20, COLORS["ink"], 700),
            text(1265, 667, "• B1 reads A1 + A2 + A3", 17),
            text(1265, 704, "• B2 reads A2 + A3", 17),
            text(1265, 741, "• B3 reads A3 + A4", 17),
            text(1265, 778, "• B4 reads A2 + A3", 17),
            text(1265, 817, "MCP input/output schemas isolate algorithms from orchestration.", 15, COLORS["muted"]),
        ]
    )
    body.append(line(1170, 662, 1235, 662, COLORS["orange"], 2, marker="arrow-orange"))
    body.append(line(1170, 787, 1235, 787, COLORS["orange"], 2, marker="arrow-orange"))

    body.extend(
        _node(430, 890, 330, 115, "C1 Risk assessment", "compliance + weather + deadline + energy", COLORS["purple"], "#F8F5FB")
    )
    body.extend(
        _node(975, 890, 330, 115, "Solution selection", "rank feasible candidates and select vehicle", COLORS["purple"], "#F8F5FB")
    )
    body.extend(
        _node(1520, 890, 300, 115, "Command report", "recommended plan, trace and replan events", COLORS["purple"], "#F8F5FB")
    )
    body.append(line(760, 947, 975, 947, COLORS["purple"], 2.5, marker="arrow-blue"))
    body.append(line(1305, 947, 1520, 947, COLORS["purple"], 2.5, marker="arrow-blue"))
    for x, _, _ in route_nodes:
        body.append(line(x + 115, 840, x + 115, 868, COLORS["orange"], 1.5))
    body.append(line(245, 868, 1055, 868, COLORS["orange"], 1.5))
    body.append(line(595, 868, 595, 890, COLORS["orange"], 2, marker="arrow-orange"))
    body.append(
        text(
            960,
            1050,
            "核心贡献：在专业优化算法之外增加服务级编排、运行可行性判定与异常恢复能力。",
            18,
            COLORS["muted"],
            anchor="middle",
            italic=True,
        )
    )
    return svg_document("能力感知多智能体算法服务编排框架", body)


def write_figures() -> List[Path]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figures = {
        "algorithm_scenario_line_comparison.svg": algorithm_line_figure(data),
        "low_altitude_delivery_scenario_academic.svg": academic_scenario_figure(),
        "multi_agent_algorithm_framework_academic.svg": academic_framework_figure(),
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
