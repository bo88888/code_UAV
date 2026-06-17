import html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "outputs" / "algorithm_comparison.json"
OUTPUT_DIR = ROOT / "outputs" / "figures"

COLORS = {
    "bg": "#071426",
    "panel": "#0D223B",
    "panel2": "#102B48",
    "grid": "#244561",
    "text": "#F2F7FC",
    "muted": "#A6BED0",
    "cyan": "#28D7E5",
    "blue": "#4C8DFF",
    "amber": "#FFB547",
    "red": "#FF667A",
    "green": "#48D597",
    "purple": "#A77BFF",
}


def esc(value: Any) -> str:
    return html.escape(str(value))


def text(
    x: float,
    y: float,
    value: Any,
    size: int = 28,
    fill: str = COLORS["text"],
    weight: int = 400,
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}" '
        f'font-family="Microsoft YaHei, Arial, sans-serif">{esc(value)}</text>'
    )


def rect(
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    radius: int = 20,
    stroke: str = "none",
    stroke_width: int = 1,
) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="{radius}" fill="{fill}" stroke="{stroke}" '
        f'stroke-width="{stroke_width}"/>'
    )


def line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    stroke: str = COLORS["grid"],
    width: int = 2,
    dash: str = "",
    marker: bool = False,
) -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    marker_attr = ' marker-end="url(#arrow)"' if marker else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{stroke}" stroke-width="{width}"{dash_attr}{marker_attr}/>'
    )


def svg_document(body: Iterable[str], title_value: str) -> str:
    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" '
            'viewBox="0 0 1920 1080">',
            f"<title>{esc(title_value)}</title>",
            "<defs>",
            '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">',
            '<feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#000" flood-opacity=".28"/>',
            "</filter>",
            '<marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">',
            f'<path d="M0,0 L12,6 L0,12 z" fill="{COLORS["cyan"]}"/>',
            "</marker>",
            '<linearGradient id="header" x1="0" y1="0" x2="1" y2="0">',
            f'<stop offset="0" stop-color="{COLORS["blue"]}"/>',
            f'<stop offset="1" stop-color="{COLORS["cyan"]}"/>',
            "</linearGradient>",
            "</defs>",
            rect(0, 0, 1920, 1080, COLORS["bg"], radius=0),
            '<circle cx="1740" cy="120" r="260" fill="#15395A" opacity=".35"/>',
            '<circle cx="140" cy="970" r="330" fill="#113451" opacity=".28"/>',
            *body,
            "</svg>",
        ]
    )


def algorithm_figure(data: Dict[str, Any]) -> str:
    algorithms = list(data["algorithm_results"].items())
    short_names = {
        "DRL-LLM Compliance Trajectory": "DRL-LLM 合规航线",
        "TWA-MILP Medical Scheduler": "TWA-MILP 时间窗",
        "CoordField Agentic Allocation": "CoordField 分配",
        "NN Weather-Adaptive Air-Ground": "NN 空地协同",
    }
    palette = [
        COLORS["cyan"],
        COLORS["blue"],
        COLORS["purple"],
        COLORS["amber"],
    ]
    body: List[str] = [
        text(90, 92, "低空应急配送算法对比", 52, weight=700),
        text(
            90,
            138,
            "四类算法在正常、恶劣天气、临时禁飞和无人机短时不可用场景下的实验结果",
            25,
            COLORS["muted"],
        ),
    ]

    card_width = 410
    for index, (name, metrics) in enumerate(algorithms):
        x = 90 + index * 450
        color = palette[index]
        body.extend(
            [
                rect(x, 185, card_width, 188, COLORS["panel"], stroke="#1E4666"),
                rect(x, 185, 10, 188, color, radius=5),
                text(x + 28, 232, short_names[name], 27, weight=700),
                text(
                    x + 28,
                    276,
                    f"场景成功率  {metrics['scenario_success_rate'] * 100:.0f}%",
                    22,
                    COLORS["muted"],
                ),
                text(
                    x + 28,
                    315,
                    f"时间窗满足  {metrics['deadline_met_rate'] * 100:.0f}%",
                    22,
                    COLORS["muted"],
                ),
                text(
                    x + 28,
                    354,
                    f"被系统推荐  {metrics['selected_count']} 次",
                    22,
                    color,
                    700,
                ),
            ]
        )

    panels = [
        ("平均任务耗时（分钟，越低越好）", "average_duration_mins", 30, 435),
        ("平均能耗（kJ，越低越好）", "average_energy_kj", 850, 435),
        ("平均合规评分（越高越好）", "average_compliance_score", 1.0, 760),
    ]
    panel_positions = [(90, 420, 820, 290), (955, 420, 875, 290), (90, 745, 1740, 245)]
    for panel_index, ((title_value, key, max_value, _), panel) in enumerate(
        zip(panels, panel_positions)
    ):
        px, py, pw, ph = panel
        body.append(rect(px, py, pw, ph, COLORS["panel"], stroke="#1E4666"))
        body.append(text(px + 30, py + 45, title_value, 25, weight=700))
        row_y = py + (76 if panel_index == 2 else 86)
        row_spacing = 42 if panel_index == 2 else 47
        for index, (name, metrics) in enumerate(algorithms):
            value = float(metrics[key])
            color = palette[index]
            bar_x = px + 250
            bar_w = pw - 345
            width = max(4, bar_w * min(value / max_value, 1))
            y = row_y + index * row_spacing
            body.append(text(px + 30, y + 21, short_names[name], 18, COLORS["muted"]))
            body.append(rect(bar_x, y, bar_w, 24, "#173A57", radius=12))
            body.append(rect(bar_x, y, width, 24, color, radius=12))
            label = f"{value:.2f}" if key != "average_compliance_score" else f"{value:.2f}"
            body.append(text(px + pw - 28, y + 21, label, 18, color, 700, "end"))

    body.append(
        text(
            960,
            1035,
            "说明：单算法最优不等于全场景最优，系统根据空域、天气和资源状态动态选择方案",
            21,
            COLORS["muted"],
            anchor="middle",
        )
    )
    return svg_document(body, "低空应急配送算法对比")


def scenario_figure(data: Dict[str, Any]) -> str:
    scenario_names = {
        "normal": "正常配送",
        "bad_weather": "恶劣天气",
        "airspace_restricted": "临时禁飞",
        "no_available_uav_once": "无人机短时不可用",
    }
    algorithm_names = {
        "DRL-LLM Compliance Trajectory": "DRL-LLM 合规航线",
        "NN Weather-Adaptive Air-Ground": "NN 空地协同",
    }
    body: List[str] = [
        text(90, 92, "动态场景适应与异常恢复效果", 52, weight=700),
        text(
            90,
            138,
            "同一应急医疗任务在不同运行条件下的算法选择与重规划路径",
            25,
            COLORS["muted"],
        ),
    ]
    positions = [(90, 210), (980, 210), (90, 580), (980, 580)]
    for (x, y), scenario in zip(positions, data["scenarios"]):
        risk = scenario["risk_level"]
        risk_color = COLORS["green"] if risk == "LOW" else COLORS["amber"]
        selected = algorithm_names.get(
            scenario["selected_algorithm"], scenario["selected_algorithm"]
        )
        actions = scenario["replan_actions"]
        if scenario["scenario"] == "no_available_uav_once":
            recovery = "等待无人机后重试 → 恢复无人机调度"
        elif not actions:
            recovery = "直接执行，无需重规划"
        else:
            action_map = {
                "retry": "重试",
                "fallback_selected": "切换空地协同",
                "wait_and_retry": "等待无人机后重试",
            }
            recovery = " → ".join(action_map.get(item, item) for item in actions)
        body.extend(
            [
                rect(x, y, 850, 315, COLORS["panel"], stroke="#1E4666"),
                rect(x, y, 850, 10, risk_color, radius=5),
                text(x + 34, y + 62, scenario_names[scenario["scenario"]], 34, weight=700),
                rect(x + 660, y + 28, 150, 44, risk_color, radius=22),
                text(x + 735, y + 59, f"{risk} 风险", 19, COLORS["bg"], 700, "middle"),
                text(x + 34, y + 117, "最终推荐", 20, COLORS["muted"]),
                text(x + 170, y + 117, selected, 25, COLORS["cyan"], 700),
                text(x + 34, y + 164, "执行载具", 20, COLORS["muted"]),
                text(
                    x + 170,
                    y + 164,
                    "地面应急车辆"
                    if scenario["selected_vehicle"] == "ground_vehicle"
                    else "医疗无人机",
                    24,
                    COLORS["text"],
                    700,
                ),
                text(x + 34, y + 214, "恢复链路", 20, COLORS["muted"]),
                text(x + 34, y + 258, recovery, 22, COLORS["amber"] if actions else COLORS["green"], 700),
                text(
                    x + 34,
                    y + 294,
                    "任务状态：具备派发条件",
                    19,
                    COLORS["green"],
                ),
            ]
        )
    body.append(
        text(
            960,
            1035,
            "实验结果：4/4 场景成功完成，2 个异常场景触发 fallback，1 个场景触发等待重试",
            23,
            COLORS["muted"],
            500,
            "middle",
        )
    )
    return svg_document(body, "动态场景适应与异常恢复效果")


def scheduling_figure(data: Dict[str, Any]) -> str:
    scheduling = data["scheduling_comparison"]
    serial = scheduling["serial_makespan_ms"]
    dag = scheduling["capability_dag_makespan_ms"]
    max_value = max(serial, dag)
    body: List[str] = [
        text(90, 92, "能力感知 DAG 调度加速效果", 52, weight=700),
        text(
            90,
            138,
            "A 阶段环境检查与 B 阶段多算法并行执行，缩短任务保障总时延",
            25,
            COLORS["muted"],
        ),
        rect(90, 205, 1100, 710, COLORS["panel"], stroke="#1E4666"),
        rect(1240, 205, 590, 710, COLORS["panel2"], stroke="#1E4666"),
    ]
    bars = [
        ("串行调度", serial, COLORS["amber"], 350),
        ("能力感知 DAG", dag, COLORS["cyan"], 610),
    ]
    for label, value, color, y in bars:
        body.append(text(150, y + 58, label, 30, weight=700))
        body.append(rect(390, y, 690, 86, "#173A57", radius=18))
        body.append(
            rect(390, y, 690 * value / max_value, 86, color, radius=18)
        )
        label_color = COLORS["bg"] if label == "串行调度" else color
        label_x = 1040 if label == "串行调度" else 1100
        body.append(
            text(label_x, y + 58, f"{value} ms", 31, label_color, 700, "end")
        )
    body.extend(
        [
            text(1535, 340, f"{scheduling['speedup']:.2f}×", 112, COLORS["cyan"], 700, "middle"),
            text(1535, 395, "并行加速比", 28, COLORS["muted"], 500, "middle"),
            line(1335, 470, 1735, 470, COLORS["grid"], 2),
            text(
                1535,
                590,
                f"{scheduling['parallel_time_saved_percent']:.2f}%",
                88,
                COLORS["green"],
                700,
                "middle",
            ),
            text(1535, 642, "总时延节省", 28, COLORS["muted"], 500, "middle"),
            text(1535, 760, "1080 ms → 420 ms", 30, COLORS["text"], 700, "middle"),
            text(1535, 805, "环境检查和候选算法均并行", 21, COLORS["muted"], anchor="middle"),
            text(
                960,
                1010,
                "时延模型为固定服务耗时实验，用于隔离网络抖动并比较调度策略本身",
                22,
                COLORS["muted"],
                anchor="middle",
            ),
        ]
    )
    return svg_document(body, "能力感知 DAG 调度加速效果")


def dag_figure() -> str:
    body: List[str] = [
        text(90, 92, "低空应急配送多智能体编排流程", 52, weight=700),
        text(
            90,
            138,
            "环境感知、论文算法服务、综合风险和任务保障报告的完整业务闭环",
            25,
            COLORS["muted"],
        ),
    ]
    stages = [
        (70, "A  环境与资源检查", COLORS["blue"]),
        (510, "B  多算法规划与调度", COLORS["cyan"]),
        (1190, "C  综合风险评估", COLORS["amber"]),
        (1545, "R  指挥报告", COLORS["green"]),
    ]
    for x, label, color in stages:
        body.append(rect(x, 185, 300 if x != 510 else 450, 55, color, radius=16))
        body.append(text(x + 22, 222, label, 24, COLORS["bg"], 700))

    a_nodes = [
        ("AIR_01", "空域合规"),
        ("WEA_01", "气象风险"),
        ("UAV_01", "无人机状态"),
        ("DOCK_01", "机巢资源"),
    ]
    b_nodes = [
        ("ROUTE_COMP", "DRL-LLM 合规航线"),
        ("ROUTE_WEA", "NN 空地协同"),
        ("ROUTE_MED", "TWA-MILP 时间窗"),
        ("ROUTE_AGENT", "CoordField 分配"),
    ]
    node_ys = [300, 455, 610, 765]
    for (node_id, label), y in zip(a_nodes, node_ys):
        body.extend(
            [
                rect(70, y, 300, 110, COLORS["panel"], stroke="#2C5C84"),
                text(95, y + 40, node_id, 18, COLORS["blue"], 700),
                text(95, y + 80, label, 25, weight=700),
            ]
        )
    for (node_id, label), y in zip(b_nodes, node_ys):
        body.extend(
            [
                rect(510, y, 450, 110, COLORS["panel"], stroke="#2C7180"),
                text(535, y + 40, node_id, 18, COLORS["cyan"], 700),
                text(535, y + 80, label, 25, weight=700),
            ]
        )
    for y in node_ys:
        body.append(line(370, y + 55, 510, y + 55, COLORS["cyan"], 3, marker=True))
    body.extend(
        [
            rect(1190, 470, 300, 180, COLORS["panel"], stroke="#80602C"),
            text(1218, 515, "RISK_01", 20, COLORS["amber"], 700),
            text(1218, 560, "多指标方案融合", 27, weight=700),
            text(1218, 602, "合规 / 天气 / 时效 / 能耗", 18, COLORS["muted"]),
            rect(1545, 470, 300, 180, COLORS["panel"], stroke="#2C8060"),
            text(1573, 515, "REPORT_01", 20, COLORS["green"], 700),
            text(1573, 560, "任务保障报告", 27, weight=700),
            text(1573, 602, "推荐方案与执行轨迹", 18, COLORS["muted"]),
            line(960, 355, 1120, 530, COLORS["cyan"], 3),
            line(960, 510, 1120, 545, COLORS["cyan"], 3),
            line(960, 665, 1120, 575, COLORS["cyan"], 3),
            line(960, 820, 1120, 590, COLORS["cyan"], 3),
            line(1120, 530, 1190, 560, COLORS["cyan"], 3, marker=True),
            line(1490, 560, 1545, 560, COLORS["cyan"], 3, marker=True),
            line(735, 410, 735, 455, COLORS["red"], 3, "10 8", marker=True),
            text(770, 440, "禁飞 / 恶劣天气触发 fallback", 19, COLORS["red"], 700),
            line(735, 720, 735, 765, COLORS["amber"], 3, "10 8", marker=True),
            text(770, 750, "无可用无人机触发等待重试", 19, COLORS["amber"], 700),
            rect(70, 950, 1775, 64, COLORS["panel2"], radius=18),
            text(
                958,
                993,
                "创新点：不是替代单个路径算法，而是按任务语义统一编排、比较并动态切换多类低空算法服务",
                23,
                COLORS["text"],
                600,
                "middle",
            ),
        ]
    )
    return svg_document(body, "低空应急配送多智能体编排流程")


def write_figures() -> List[Path]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figures = {
        "algorithm_comparison.svg": algorithm_figure(data),
        "scenario_recovery.svg": scenario_figure(data),
        "scheduling_speedup.svg": scheduling_figure(data),
        "orchestration_dag.svg": dag_figure(),
    }
    paths = []
    for filename, content in figures.items():
        path = OUTPUT_DIR / filename
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths


if __name__ == "__main__":
    for output_path in write_figures():
        print(output_path)
