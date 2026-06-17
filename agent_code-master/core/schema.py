from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.enums import TaskStatus


@dataclass
class TaskRequest:
    """A low-altitude emergency delivery request."""

    task_id: str
    requirement_xml_path: str
    mission_type: str = "emergency_medical"
    delivery_points: List[Dict[str, Any]] = field(default_factory=list)
    cargo_weight_kg: float = 0.0
    priority: int = 1
    environmental_constraints: Dict[str, Any] = field(default_factory=dict)
    output_requirements: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubTask:
    """A dependency-aware service invocation in the orchestration DAG."""

    subtask_id: str
    name: str
    tool_name: str
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    stage: str = ""
    capability_id: str = ""
    reason: str = ""
    optional: bool = False
    fallback_tools: List[str] = field(default_factory=list)
    skip_reason: str = ""
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retry: int = 1


@dataclass
class ToolResult:
    """Normalized result returned by a low-altitude algorithm service."""

    subtask_id: str
    tool_name: str
    success: bool
    output: Dict[str, Any]
    message: str = ""
    confidence: Optional[float] = None


@dataclass
class ExecutionContext:
    """Shared state passed through all agents for one mission."""

    request: TaskRequest
    parsed_requirement: Dict[str, Any] = field(default_factory=dict)
    subtasks: List[SubTask] = field(default_factory=list)
    execution_plan: List[str] = field(default_factory=list)
    plan_rationale: List[Dict[str, Any]] = field(default_factory=list)
    execution_trace: List[Dict[str, Any]] = field(default_factory=list)
    replan_events: List[Dict[str, Any]] = field(default_factory=list)
    skipped_tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: Dict[str, ToolResult] = field(default_factory=dict)
    final_report: Dict[str, Any] = field(default_factory=dict)
    quality_report: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
