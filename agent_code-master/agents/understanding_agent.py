import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from core.schema import ExecutionContext


PRIORITY_MAP = {
    "low": 1,
    "normal": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_mission_type(task_type: str) -> str:
    normalized = (task_type or "").strip().lower()
    if "medical" in normalized:
        return "emergency_medical"
    if "emergency" in normalized or "supply" in normalized:
        return "emergency_supply"
    return normalized or "standard_delivery"


def _parse_priority(value: str, default: int = 1) -> int:
    text = (value or "").strip().lower()
    if text in PRIORITY_MAP:
        return PRIORITY_MAP[text]
    try:
        return max(1, min(5, int(text)))
    except ValueError:
        return default


def _parse_delivery_points(root: ET.Element) -> List[Dict[str, Any]]:
    points = []
    for point in root.findall("delivery_points/point"):
        item = {child.tag: (child.text or "").strip() for child in point}
        item["lon"] = _to_float(item.get("lon"))
        item["lat"] = _to_float(item.get("lat"))
        points.append(item)
    return points


def _parse_environmental_constraints(root: ET.Element) -> Dict[str, Any]:
    constraints: Dict[str, Any] = {}
    parent = root.find("environmental_constraints")
    if parent is None:
        return constraints
    for child in parent:
        value = (child.text or "").strip()
        try:
            constraints[child.tag] = float(value)
        except ValueError:
            constraints[child.tag] = value
    return constraints


class UnderstandingAgent:
    """Parse a command-center XML requirement into delivery semantics."""

    def run(self, context: ExecutionContext) -> ExecutionContext:
        tree = ET.parse(context.request.requirement_xml_path)
        root = tree.getroot()

        task_type = root.findtext("task_type", context.request.mission_type)
        xml_points = _parse_delivery_points(root)
        xml_weight = _to_float(
            root.findtext("cargo/weight_kg"), context.request.cargo_weight_kg
        )
        xml_priority = _parse_priority(
            root.findtext("cargo/priority", ""), context.request.priority
        )
        xml_constraints = _parse_environmental_constraints(root)

        constraints = dict(xml_constraints)
        constraints.update(context.request.environmental_constraints)

        context.parsed_requirement = {
            "task_type": task_type,
            "mission_type": context.request.mission_type
            if context.request.mission_type != "emergency_medical"
            else _normalize_mission_type(task_type),
            "dispatch_mode": root.findtext(
                "dispatch_mode", "intelligent_coordination"
            ),
            "cargo": {
                "type": root.findtext("cargo/type", "emergency_supply"),
                "weight_kg": context.request.cargo_weight_kg
                if context.request.cargo_weight_kg > 0
                else xml_weight,
            },
            "cargo_weight_kg": context.request.cargo_weight_kg
            if context.request.cargo_weight_kg > 0
            else xml_weight,
            "priority": context.request.priority
            if context.request.priority != 1
            else xml_priority,
            "delivery_points": context.request.delivery_points or xml_points,
            "environmental_constraints": constraints,
            "output_requirements": context.request.output_requirements,
        }

        issues = list(context.metadata.get("input_validation_issues", []))
        if len(context.parsed_requirement["delivery_points"]) < 2:
            issues.append("at least one pickup and one dropoff point are required")
        if context.parsed_requirement["cargo_weight_kg"] <= 0:
            issues.append("cargo_weight_kg must be greater than zero")
        context.metadata["input_validation_issues"] = issues
        return context
